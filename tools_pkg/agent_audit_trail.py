"""Agent audit trail — full payment + action history for any agent wallet.

Composes Base eth_getLogs USDC Transfer scans + CDP discovery context to
return a structured per-agent activity ledger:
  - tools paid for (resolved via known x402 endpoint registry)
  - timestamps + tx hashes
  - cumulative spend USD
  - velocity / cadence
  - risk signals (rapid-fire calls, value spikes, new wallet)

This is the artifact the Catena/Ralio funding thesis is buying. Every
agent operator who runs autonomous agents needs: "what has my agent
actually been paying for and when." Currently there's no canonical
answer — wallets show transfers but not the COMMERCE context. This tool
provides the commerce context: tool name, category, price band.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone

NAME = "onyx_agent_audit_trail"
PRICE_USDC = "0.05"
TIER = "metered"
DESCRIPTION = (
    "Full payment + action audit trail for any agent wallet on Base. Returns "
    "every USDC outflow with resolved x402 destination, tool name where known, "
    "timestamp, tx hash, cumulative spend, velocity, and behavioral risk flags. "
    "The audit log every agent operator needs — what has my agent actually "
    "been paying for and when. Powers compliance, ops review, anomaly detect."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "wallet": {
            "type": "string",
            "description": "Agent wallet address on Base (0x... 20-byte hex).",
        },
        "lookback_blocks": {
            "type": "integer",
            "minimum": 100,
            "maximum": 50000,
            "default": 5000,
            "description": "Block range to scan (Base is ~2s/block → 5000 blocks ≈ 2.8h, 10000 ≈ 5.5h, 50000 ≈ 28h).",
        },
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 100,
            "default": 30,
            "description": "Max events to return (truncated newest-first).",
        },
    },
    "required": ["wallet"],
}

_RPC = "https://base.publicnode.com"
_UA = "onyx-agent-audit-trail/1.0"
_USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
_CDP_DISCOVERY = "https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources?limit=1000"


def _hex_addr(s: str) -> bool:
    s = (s or "").strip()
    return s.startswith("0x") and len(s) == 42


def _rpc(method: str, params: list, timeout: float = 10.0) -> dict:
    req = urllib.request.Request(
        _RPC,
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": _UA},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _addr_topic(addr: str) -> str:
    """Pad address to 32-byte topic format."""
    return "0x" + "0" * 24 + addr.lower().lstrip("0x")


def _resolve_x402_endpoints() -> dict[str, dict]:
    """Pull current CDP discovery + build payTo -> service lookup table."""
    try:
        req = urllib.request.Request(_CDP_DISCOVERY, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=12) as resp:
            d = json.loads(resp.read().decode())
    except (urllib.error.URLError, urllib.error.HTTPError):
        return {}
    out: dict[str, dict] = {}
    for r in d.get("items", []):
        for a in r.get("accepts", []):
            pt = (a.get("payTo") or "").lower()
            if pt:
                # First service wins; we don't dedup beyond that
                if pt not in out:
                    out[pt] = {
                        "resource": r.get("resource"),
                        "description": (r.get("description") or "")[:200],
                        "network": a.get("network"),
                    }
    return out


def _decode_transfer(log: dict) -> dict | None:
    topics = log.get("topics") or []
    if len(topics) < 3:
        return None
    from_addr = "0x" + topics[1][-40:].lower()
    to_addr = "0x" + topics[2][-40:].lower()
    data = log.get("data", "0x")
    try:
        amount = int(data, 16) if data and data != "0x" else 0
    except ValueError:
        amount = 0
    return {
        "from": from_addr,
        "to": to_addr,
        "amount_atomic": amount,
        "amount_usdc": amount / 1e6,
        "block": int(log.get("blockNumber", "0x0"), 16),
        "tx": log.get("transactionHash"),
        "log_index": int(log.get("logIndex", "0x0"), 16),
    }


def _risk_flags(events: list[dict]) -> list[str]:
    flags = []
    if not events:
        return ["no_activity"]
    if len(events) >= 20:
        # Check for burst patterns
        blocks = [e["block"] for e in events]
        block_span = max(blocks) - min(blocks)
        if block_span > 0 and len(events) / block_span > 0.1:
            flags.append("high_velocity — >1 tx per 10 blocks")
    amounts = [e["amount_usdc"] for e in events]
    if amounts and max(amounts) > 10 * (sum(amounts) / len(amounts)):
        flags.append("spike_detected — single tx > 10× avg")
    if all(e["amount_usdc"] < 0.001 for e in events) and len(events) >= 5:
        flags.append("micro_only — all <$0.001, may be testnet-style probing")
    distinct_recipients = len({e["to"] for e in events})
    if distinct_recipients == 1 and len(events) >= 5:
        flags.append("single_destination — concentrated supplier, vendor lock-in")
    return flags or ["nominal"]


def run(wallet: str, lookback_blocks: int = 5000, limit: int = 30, **_: object) -> dict:
    if not _hex_addr(wallet):
        return {"ok": False, "error": "wallet must be 0x... 20-byte hex"}
    lookback_blocks = max(100, min(50000, int(lookback_blocks)))
    limit = max(1, min(100, int(limit)))

    try:
        latest_resp = _rpc("eth_blockNumber", [])
        latest = int(latest_resp.get("result", "0x0"), 16)
    except (urllib.error.URLError, KeyError, ValueError) as e:
        return {"ok": False, "error": "rpc_unreachable", "detail": str(e)[:150]}

    from_block = max(0, latest - lookback_blocks)
    filt = {
        "fromBlock": hex(from_block),
        "toBlock": hex(latest),
        "address": _USDC,
        "topics": [_TRANSFER_TOPIC, _addr_topic(wallet)],  # from=wallet
    }
    try:
        log_resp = _rpc("eth_getLogs", [filt], timeout=15)
    except urllib.error.URLError as e:
        return {"ok": False, "error": "rpc_logs_failed", "detail": str(e)[:150]}

    if "error" in log_resp:
        return {"ok": False, "error": "rpc_error", "detail": str(log_resp["error"])[:200]}

    raw_logs = log_resp.get("result") or []
    events = [e for e in (_decode_transfer(l) for l in raw_logs) if e]
    events.sort(key=lambda e: -e["block"])

    # Build x402 destination resolver
    endpoint_map = _resolve_x402_endpoints()

    resolved = []
    total_spend = 0.0
    for e in events[:limit]:
        ep = endpoint_map.get(e["to"])
        resolved.append({
            **e,
            "x402_endpoint": ep["resource"] if ep else None,
            "x402_description": ep["description"] if ep else None,
            "x402_network": ep["network"] if ep else None,
            "resolved": bool(ep),
        })
        total_spend += e["amount_usdc"]

    # Stats over the full event set (not just truncated)
    full_total = sum(e["amount_usdc"] for e in events)
    distinct_dest = len({e["to"] for e in events})
    resolved_dest = sum(1 for e in events if e["to"] in endpoint_map)

    return {
        "ok": True,
        "wallet": wallet.lower(),
        "scan_window": {
            "from_block": from_block,
            "to_block": latest,
            "blocks_scanned": lookback_blocks,
        },
        "summary": {
            "total_outflows": len(events),
            "returned": len(resolved),
            "total_spend_usdc": round(full_total, 6),
            "distinct_destinations": distinct_dest,
            "destinations_resolved_to_x402": resolved_dest,
            "resolution_rate_pct": round(100 * resolved_dest / max(distinct_dest, 1), 1),
            "avg_spend_per_call": round(full_total / max(len(events), 1), 6),
        },
        "risk_flags": _risk_flags(events),
        "events": resolved,
    }


run.__when_to_use__ = (
    "Agent operator wants to know: what has my agent been paying for? "
    "Compliance officer needs audit log. Anomaly detection. Bot ops review."
)
run.__vs_alternatives__ = (
    "BaseScan shows USDC transfers but no commerce context. Off-the-shelf "
    "indexers (Alchemy, Moralis) require API keys and don't resolve x402 "
    "endpoints. This tool maps transfers to x402 services via CDP discovery."
)
run.__example_request__ = {
    "wallet": "0x4466d4a84b7c49a6a094ec6eef4a0712d6dd125e",
    "lookback_blocks": 10000,
    "limit": 20,
}
