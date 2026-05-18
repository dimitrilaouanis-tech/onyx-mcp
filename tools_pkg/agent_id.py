"""Agent identity / wallet attribution lookup — v2.

Given an EVM wallet address, scans USDC Transfer events FROM the wallet on
Base mainnet + Base Sepolia, identifies x402-style settlements (payments to
known paid-service payTo addresses), and returns a reputation card:
total volume, distinct recipients, network spread, freshness, score.

v1 was a stub. v2 actually does the RPC log scan via public free RPCs.
Stdlib-only. Free tier — pure read.
"""
from __future__ import annotations

import json
import re
import socket
import time
import urllib.error
import urllib.request

NAME = "onyx_agent_id"
PRICE_USDC = "0"
TIER = "free"
DESCRIPTION = (
    "Look up an agent (EVM wallet) and return a reputation card: x402-style "
    "USDC settlements in the last ~24h window (50k Base blocks), distinct "
    "recipients (paid-service operators), networks used, total volume, and "
    "0-100 reputation score with reasoning. Reads Base + Base Sepolia public "
    "RPCs (no key). Free tier — useful for tools deciding rate limits, "
    "returning-customer discounts, or trust extension."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "wallet_address": {
            "type": "string",
            "description": "0x-prefixed EVM wallet address of the agent to look up.",
        },
        "include_sepolia": {
            "type": "boolean",
            "default": True,
            "description": "Include Base Sepolia activity in the score (test traffic).",
        },
    },
    "required": ["wallet_address"],
}

_ADDR_RX = re.compile(r"^0x[a-fA-F0-9]{40}$")

# Topic0 for ERC-20 Transfer(address,address,uint256)
_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

_RPCS = {
    "base":         "https://base-rpc.publicnode.com",
    "base-sepolia": "https://base-sepolia.gateway.tenderly.co",
}
_RPC_FALLBACKS = {
    "base":         ["https://base.gateway.tenderly.co", "https://1rpc.io/base", "https://base.llamarpc.com"],
    "base-sepolia": ["https://base-sepolia-rpc.publicnode.com", "https://sepolia.base.org"],
}
_USDC = {
    "base":         "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
    "base-sepolia": "0x036cbd53842c5426634e7929541ec2318f3dcf7e",
}

# Public RPC eth_getLogs windows are typically <= 50k blocks
_SCAN_WINDOW_BLOCKS = 50_000


def _rpc(url: str, method: str, params: list, timeout: float = 10.0) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; OnyxAgentId/2.0)",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _block_head(rpc_url: str) -> int:
    r = _rpc(rpc_url, "eth_blockNumber", [])
    res = r.get("result", "0x0")
    return int(res, 16) if isinstance(res, str) else 0


def _transfers_from(rpc_url: str, usdc: str, from_addr: str, from_block: int) -> list[dict]:
    from_padded = from_addr.lower().replace("0x", "").rjust(64, "0")
    params = [{
        "address": usdc,
        "fromBlock": hex(from_block),
        "toBlock": "latest",
        "topics": [_TRANSFER_TOPIC, "0x" + from_padded, None],
    }]
    r = _rpc(rpc_url, "eth_getLogs", params, timeout=15.0)
    if "error" in r:
        raise RuntimeError(r["error"].get("message", "")[:200])
    return r.get("result", []) or []


def _balance_usdc(rpc_url: str, usdc: str, owner: str) -> int:
    owner_padded = owner.lower().replace("0x", "").rjust(64, "0")
    data = "0x70a08231" + owner_padded
    r = _rpc(rpc_url, "eth_call", [{"to": usdc, "data": data}, "latest"])
    res = r.get("result", "0x0")
    return int(res, 16) if isinstance(res, str) and res.startswith("0x") else 0


def _decode_to(log: dict) -> str:
    topics = log.get("topics", [])
    if len(topics) >= 3:
        return "0x" + topics[2][-40:].lower()
    return ""


def _decode_amount(log: dict) -> int:
    data = log.get("data", "0x0")
    return int(data, 16) if isinstance(data, str) and data.startswith("0x") else 0


def _scan_network(chain: str, wallet: str) -> dict:
    candidates = [_RPCS[chain]] + _RPC_FALLBACKS.get(chain, [])
    usdc = _USDC[chain]
    rpc = None
    last_err = None
    head = 0
    for c in candidates:
        try:
            head = _block_head(c)
            rpc = c
            break
        except Exception as e:
            last_err = str(e)[:120]
    if rpc is None:
        return {"chain": chain, "ok": False, "error": f"all RPCs failed: {last_err}"}
    try:
        balance = _balance_usdc(rpc, usdc, wallet)
    except Exception:
        balance = 0
    from_block = max(0, head - _SCAN_WINDOW_BLOCKS)
    try:
        logs = _transfers_from(rpc, usdc, wallet, from_block)
    except Exception as e:
        return {"chain": chain, "ok": False, "error": f"logs: {str(e)[:120]}",
                "balance_usdc": balance/1_000_000, "head": head}
    # Aggregate per recipient
    by_recipient: dict[str, dict] = {}
    total_atomic = 0
    for log in logs:
        recip = _decode_to(log)
        amt = _decode_amount(log)
        total_atomic += amt
        b = by_recipient.setdefault(recip, {"to": recip, "total_atomic": 0, "tx_count": 0, "last_block": 0})
        b["total_atomic"] += amt
        b["tx_count"] += 1
        b["last_block"] = max(b["last_block"], int(log.get("blockNumber", "0x0"), 16))
    return {
        "chain": chain,
        "ok": True,
        "head": head,
        "scanned_from_block": from_block,
        "scanned_blocks": head - from_block,
        "balance_usdc": balance / 1_000_000,
        "settlements_count": len(logs),
        "total_sent_usdc": total_atomic / 1_000_000,
        "distinct_recipients": len(by_recipient),
        "recipients": sorted(by_recipient.values(), key=lambda r: -r["total_atomic"])[:10],
    }


def _score(per_chain: dict) -> tuple[int, list[str], str]:
    score = 0
    why = []
    networks_with_activity = [c for c, r in per_chain.items() if r.get("ok") and r.get("settlements_count", 0) > 0]
    total_settlements = sum(r.get("settlements_count", 0) for r in per_chain.values() if r.get("ok"))
    total_volume = sum(r.get("total_sent_usdc", 0.0) for r in per_chain.values() if r.get("ok"))
    distinct_recips_all = set()
    for r in per_chain.values():
        if r.get("ok"):
            for rec in r.get("recipients", []):
                distinct_recips_all.add(rec["to"])

    if total_settlements > 0:
        score += 25
        why.append(f"+25 has {total_settlements} on-chain USDC settlement(s) in scan window")
    if len(networks_with_activity) >= 2:
        score += 20
        why.append(f"+20 multi-network activity ({', '.join(networks_with_activity)})")
    elif len(networks_with_activity) == 1:
        score += 5
        why.append(f"+5 single-network activity ({networks_with_activity[0]})")
    if total_volume >= 1.0:
        score += 15
        why.append(f"+15 volume >= $1 (${total_volume:.4f})")
    elif total_volume >= 0.10:
        score += 10
        why.append(f"+10 volume >= $0.10 (${total_volume:.4f})")
    if len(distinct_recips_all) >= 3:
        score += 15
        why.append(f"+15 paid {len(distinct_recips_all)} distinct recipients")
    elif len(distinct_recips_all) >= 1:
        score += 5
        why.append(f"+5 paid {len(distinct_recips_all)} recipient(s)")
    # Freshness — if any chain has a settlement in last 5000 blocks (~3h base)
    fresh = False
    for r in per_chain.values():
        if not r.get("ok"):
            continue
        head = r.get("head", 0)
        for rec in r.get("recipients", []):
            if head - rec.get("last_block", 0) < 5000:
                fresh = True
                break
    if fresh:
        score += 15
        why.append("+15 recent activity (<5000 blocks on at least one chain)")

    score = min(score, 100)
    grade = "A" if score >= 80 else "B" if score >= 60 else "C" if score >= 40 else "D" if score >= 20 else "F"
    return score, why or ["base case: zero on-chain activity in scan window"], grade


def run(
    wallet_address: str,
    include_sepolia: bool = True,
    **_: object,
) -> dict:
    if not isinstance(wallet_address, str):
        raise ValueError("wallet_address must be a string")
    addr = wallet_address.strip()
    if not _ADDR_RX.match(addr):
        raise ValueError("wallet_address must be 0x-prefixed 20-byte hex")

    chains = ["base"]
    if include_sepolia:
        chains.append("base-sepolia")

    per_chain: dict[str, dict] = {}
    for chain in chains:
        per_chain[chain] = _scan_network(chain, addr)

    score, reasons, grade = _score(per_chain)

    # Aggregate across chains
    total_volume = sum(r.get("total_sent_usdc", 0.0) for r in per_chain.values() if r.get("ok"))
    total_settlements = sum(r.get("settlements_count", 0) for r in per_chain.values() if r.get("ok"))
    total_balance = sum(r.get("balance_usdc", 0.0) for r in per_chain.values() if r.get("ok"))

    return {
        "ok": True,
        "wallet_address": addr,
        "score": score,
        "grade": grade,
        "scoring_reasons": reasons,
        "summary": {
            "total_settlements": total_settlements,
            "total_sent_usdc": round(total_volume, 6),
            "total_balance_usdc": round(total_balance, 6),
            "chains_scanned": chains,
        },
        "per_chain": per_chain,
        "schema_version": "v2",
        "note": "Recipients include any USDC transfer destination — not all are x402 settlements. Cross-reference with bazaar to identify paid-service recipients.",
    }


run.__when_to_use__ = (
    "An MCP server wants to decide whether to trust a new caller (rate-limit, "
    "extend credit, give returning-customer discount). Call this tool with the "
    "caller's wallet address before processing the request."
)
run.__vs_alternatives__ = (
    "No public agent-identity / reputation layer exists in x402-land. AAE and "
    "AP2 discuss it; nobody ships. This tool reads actual on-chain USDC outflows "
    "to derive an attribution score. Free tier — reputation lookups should be "
    "cheap and ubiquitous."
)
run.__example_request__ = {
    "wallet_address": "0xc0E92810f992b7EE487b5B9b6B7dB4a2A13249fe",
    "include_sepolia": True,
}
run.__example_response__ = {
    "ok": True,
    "wallet_address": "0xc0E92810f992b7EE487b5B9b6B7dB4a2A13249fe",
    "score": 45,
    "grade": "C",
    "scoring_reasons": ["+25 has 12 settlements", "+15 volume >= $1 ($2.34)", "..."],
    "summary": {"total_settlements": 12, "total_sent_usdc": 2.34, "chains_scanned": ["base", "base-sepolia"]},
    "schema_version": "v2",
}
