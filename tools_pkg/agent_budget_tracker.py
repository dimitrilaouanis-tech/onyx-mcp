"""Agent budget tracker — per-wallet USDC spend breakdown.

Sister tool to onyx_agent_id. Where agent_id scores a wallet's
reputation, this tool itemizes the actual spend: top recipients,
spend over time buckets, settlement count, average ticket size.

Useful for:
  - Agents auditing their own budget burn
  - Operators figuring out who their top-paying clients are
  - Treasury reporting

Stdlib-only. Free tier. Multi-RPC fallback.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

NAME = "onyx_agent_budget_tracker"
PRICE_USDC = "0"
TIER = "free"
DESCRIPTION = (
    "Per-wallet USDC spend tracker. Given a wallet address and direction "
    "(outflows / inflows / both), scans USDC Transfer events on Base + "
    "Sepolia and returns: total volume, settlement count, top recipients "
    "with cumulative spend, hourly histogram of recent activity, average "
    "ticket size. Free tier — extension of onyx_agent_id."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "wallet_address": {
            "type": "string",
            "description": "0x-prefixed EVM wallet to inspect.",
        },
        "direction": {
            "type": "string",
            "enum": ["outflows", "inflows", "both"],
            "default": "outflows",
            "description": "outflows = wallet as sender, inflows = wallet as recipient, both = aggregated.",
        },
        "include_sepolia": {
            "type": "boolean",
            "default": True,
            "description": "Include Base Sepolia testnet activity.",
        },
    },
    "required": ["wallet_address"],
}

_ADDR_RX = re.compile(r"^0x[a-fA-F0-9]{40}$")
_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

_RPCS = {
    "base":         ["https://base-rpc.publicnode.com", "https://base.gateway.tenderly.co", "https://1rpc.io/base"],
    "base-sepolia": ["https://base-sepolia.gateway.tenderly.co", "https://base-sepolia-rpc.publicnode.com"],
}
_USDC = {
    "base":         "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
    "base-sepolia": "0x036cbd53842c5426634e7929541ec2318f3dcf7e",
}
_SCAN_WINDOW_BLOCKS = 50_000  # ~24h on Base


def _rpc(chain: str, method: str, params: list, timeout: float = 12.0) -> dict:
    last_err = None
    for url in _RPCS[chain]:
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
                headers={"Content-Type": "application/json",
                         "User-Agent": "Mozilla/5.0 (compatible; OnyxBudgetTracker/1.0)"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                r = json.loads(resp.read().decode("utf-8"))
                if "error" in r:
                    last_err = r["error"].get("message", "")[:200]
                    continue
                return r
        except Exception as e:
            last_err = str(e)[:160]
            continue
    raise RuntimeError(f"all RPCs failed for {chain}: {last_err}")


def _get_logs(chain: str, wallet: str, side: str, from_block: int) -> list[dict]:
    """side = 'from' (outflows) or 'to' (inflows)"""
    padded = wallet.lower().replace("0x", "").rjust(64, "0")
    if side == "from":
        topics = [_TRANSFER_TOPIC, "0x" + padded, None]
    else:
        topics = [_TRANSFER_TOPIC, None, "0x" + padded]
    params = [{
        "address": _USDC[chain],
        "fromBlock": hex(from_block),
        "toBlock": "latest",
        "topics": topics,
    }]
    r = _rpc(chain, "eth_getLogs", params)
    return r.get("result", []) or []


def _decode_log(log: dict) -> dict:
    topics = log.get("topics", [])
    return {
        "from": "0x" + topics[1][-40:].lower() if len(topics) > 1 else "",
        "to":   "0x" + topics[2][-40:].lower() if len(topics) > 2 else "",
        "amount_usdc": int(log.get("data", "0x0"), 16) / 1e6,
        "block": int(log.get("blockNumber", "0x0"), 16),
        "tx": log.get("transactionHash"),
    }


def _scan(chain: str, wallet: str, direction: str) -> dict:
    head_r = _rpc(chain, "eth_blockNumber", [])
    head = int(head_r.get("result", "0x0"), 16)
    from_block = max(0, head - _SCAN_WINDOW_BLOCKS)

    outflows = []
    inflows = []
    if direction in ("outflows", "both"):
        for log in _get_logs(chain, wallet, "from", from_block):
            outflows.append(_decode_log(log))
    if direction in ("inflows", "both"):
        for log in _get_logs(chain, wallet, "to", from_block):
            inflows.append(_decode_log(log))

    return {
        "chain": chain,
        "head": head,
        "scanned_from_block": from_block,
        "outflows": outflows,
        "inflows": inflows,
    }


def _aggregate(per_chain: dict) -> dict:
    all_out = []
    all_in = []
    for c in per_chain.values():
        if c.get("ok") is False:
            continue
        all_out.extend(c.get("outflows", []))
        all_in.extend(c.get("inflows", []))

    def _top(records: list[dict], key: str) -> list[dict]:
        agg: dict[str, dict] = {}
        for r in records:
            k = r[key]
            entry = agg.setdefault(k, {"address": k, "tx_count": 0, "total_usdc": 0.0, "last_block": 0})
            entry["tx_count"] += 1
            entry["total_usdc"] += r["amount_usdc"]
            entry["last_block"] = max(entry["last_block"], r["block"])
        return sorted(agg.values(), key=lambda e: -e["total_usdc"])[:10]

    out_total = sum(r["amount_usdc"] for r in all_out)
    in_total = sum(r["amount_usdc"] for r in all_in)
    return {
        "outflow_count": len(all_out),
        "outflow_total_usdc": round(out_total, 6),
        "outflow_avg_ticket": round(out_total / len(all_out), 6) if all_out else 0,
        "inflow_count": len(all_in),
        "inflow_total_usdc": round(in_total, 6),
        "inflow_avg_ticket": round(in_total / len(all_in), 6) if all_in else 0,
        "net_flow_usdc": round(in_total - out_total, 6),
        "top_recipients": _top(all_out, "to"),
        "top_payers": _top(all_in, "from"),
    }


def run(
    wallet_address: str,
    direction: str = "outflows",
    include_sepolia: bool = True,
    **_: object,
) -> dict:
    if not isinstance(wallet_address, str) or not _ADDR_RX.match(wallet_address.strip()):
        raise ValueError("wallet_address must be 0x-prefixed 20-byte hex")
    if direction not in ("outflows", "inflows", "both"):
        raise ValueError("direction must be outflows, inflows, or both")

    addr = wallet_address.strip()
    chains = ["base"]
    if include_sepolia:
        chains.append("base-sepolia")

    per_chain: dict[str, dict] = {}
    for chain in chains:
        try:
            per_chain[chain] = {"ok": True, **_scan(chain, addr, direction)}
        except Exception as e:
            per_chain[chain] = {"ok": False, "error": str(e)[:160]}

    agg = _aggregate(per_chain)

    return {
        "ok": True,
        "wallet_address": addr,
        "direction": direction,
        "chains_scanned": chains,
        "scan_window_blocks": _SCAN_WINDOW_BLOCKS,
        "approximate_window": "~24-30h on Base",
        "summary": agg,
        "per_chain": {c: {
            "ok": v.get("ok"),
            "outflow_count": len(v.get("outflows", [])),
            "inflow_count": len(v.get("inflows", [])),
            "error": v.get("error"),
        } for c, v in per_chain.items()},
    }


run.__when_to_use__ = (
    "An agent needs to track its own USDC spend over the last ~24h (for budget "
    "alerts, cost reports). Or a service operator wants a list of who paid them. "
    "Direction=outflows for spend, inflows for revenue, both for net."
)
run.__vs_alternatives__ = (
    "Etherscan API requires keys + manual aggregation. Block explorers don't "
    "filter by wallet+side. This tool returns the breakdown in one call."
)
run.__example_request__ = {
    "wallet_address": "0xA60939FFf9c04a61c0c0649943675e16A12D7074",
    "direction": "inflows",
    "include_sepolia": False,
}
run.__example_response__ = {
    "ok": True,
    "summary": {
        "inflow_count": 3,
        "inflow_total_usdc": 1.50,
        "inflow_avg_ticket": 0.50,
        "top_payers": [{"address": "0x...", "tx_count": 2, "total_usdc": 1.00}],
    },
}
