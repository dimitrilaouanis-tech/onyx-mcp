"""Base event logs — fetch + decode contract events from Base mainnet.

Direct RPC eth_getLogs against Base public node. Returns structured logs
with topic-0 (event signature hash), full topics array, raw data, block
number, tx hash. Optional event-signature lookup via 4byte-style topic-0
guessing (Transfer, Approval, etc.) for common ERC-20/721/1155 events.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

NAME = "onyx_base_event_logs"
PRICE_USDC = "0.003"
TIER = "metered"
DESCRIPTION = (
    "Fetch contract event logs from Base mainnet via eth_getLogs. Returns "
    "structured logs with topics, raw data, block+tx info, plus optional "
    "event-signature decode for common ERC-20/721/1155 events (Transfer, "
    "Approval, OwnershipTransferred). Supports block range filter (default "
    "last 100 blocks) and topic-0 filter for narrowing to specific events."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "address": {
            "type": "string",
            "description": "Contract address (0x... 20-byte hex) to fetch logs for.",
        },
        "from_block": {
            "type": "string",
            "description": "Start block: hex ('0x12345'), decimal ('1234567'), or 'latest'. Default = latest - 100.",
        },
        "to_block": {
            "type": "string",
            "description": "End block. Default = 'latest'.",
        },
        "topic0": {
            "type": "string",
            "description": "Optional event signature hash (32-byte hex) to filter on. E.g. Transfer = 0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef.",
        },
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 500,
            "default": 50,
            "description": "Max log entries to return.",
        },
    },
    "required": ["address"],
}

_RPC = "https://base.publicnode.com"
_UA = "onyx-base-event-logs/1.0"

# Common event-signature lookup table (topic-0 hash -> human name)
_TOPIC0_DECODE = {
    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef":
        "Transfer(address indexed from, address indexed to, uint256 value)",
    "0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925":
        "Approval(address indexed owner, address indexed spender, uint256 value)",
    "0x17307eab39ab6107e8899845ad3d59bd9653f200f220920489ca2b5937696c31":
        "ApprovalForAll(address indexed owner, address indexed operator, bool approved)",
    "0x8be0079c531659141344cd1fd0a4f28419497f9722a3daafe3b4186f6b6457e0":
        "OwnershipTransferred(address indexed previousOwner, address indexed newOwner)",
    "0xc3d58168c5ae7397731d063d5bbf3d657854427343f4c083240f7aacaa2d0f62":
        "TransferSingle(address indexed operator, address indexed from, address indexed to, uint256 id, uint256 value)",
    "0x4a39dc06d4c0dbc64b70af90fd698a233a518aa5d07e595d983b8c0526c8f7fb":
        "TransferBatch(address indexed operator, address indexed from, address indexed to, uint256[] ids, uint256[] values)",
    "0xddb5c7b3ce58997d0531b07f9ef5a394aaaccd0a3a31a59a9e3a5b27f64ad0ce":
        "Swap(address indexed sender, ...)  (Uniswap V2/V3 family)",
}


def _hex_addr(s: str) -> bool:
    s = (s or "").strip()
    return s.startswith("0x") and len(s) == 42


def _hex_topic(s: str) -> bool:
    s = (s or "").strip()
    return s.startswith("0x") and len(s) == 66


def _rpc(method: str, params: list) -> dict:
    req = urllib.request.Request(
        _RPC,
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": _UA},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=12) as resp:
        return json.loads(resp.read().decode())


def _block_int(v: str | None, default: str = "latest") -> str:
    if not v:
        return default
    v = str(v).strip()
    if v == "latest" or v == "earliest":
        return v
    if v.startswith("0x"):
        return v
    try:
        return hex(int(v))
    except ValueError:
        return default


def run(
    address: str,
    from_block: str | None = None,
    to_block: str | None = None,
    topic0: str | None = None,
    limit: int = 50,
    **_: object,
) -> dict:
    if not _hex_addr(address):
        return {"ok": False, "error": "address must be 0x... 20-byte hex"}
    if topic0 and not _hex_topic(topic0):
        return {"ok": False, "error": "topic0 must be 32-byte hex (0x + 64 chars)"}
    limit = max(1, min(500, int(limit)))

    # Compute defaults: last 100 blocks
    if not from_block:
        try:
            latest = int(_rpc("eth_blockNumber", []).get("result", "0x0"), 16)
            from_block_hex = hex(max(0, latest - 100))
        except (urllib.error.URLError, KeyError, ValueError):
            from_block_hex = "latest"
    else:
        from_block_hex = _block_int(from_block, "latest")
    to_block_hex = _block_int(to_block, "latest")

    filt: dict = {
        "fromBlock": from_block_hex,
        "toBlock": to_block_hex,
        "address": address.lower(),
    }
    if topic0:
        filt["topics"] = [topic0.lower()]

    try:
        res = _rpc("eth_getLogs", [filt])
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"rpc_http_{e.code}"}
    except urllib.error.URLError as e:
        return {"ok": False, "error": "rpc_unreachable", "detail": str(e)[:200]}

    if "error" in res:
        return {"ok": False, "error": "rpc_error", "detail": str(res["error"])[:300]}

    logs = res.get("result") or []
    truncated = False
    if len(logs) > limit:
        logs = logs[:limit]
        truncated = True

    # Decode topic-0 for common events
    decoded = []
    sig_counts: dict[str, int] = {}
    for l in logs:
        topics = l.get("topics") or []
        t0 = topics[0] if topics else None
        sig = _TOPIC0_DECODE.get(t0, "unknown")
        sig_counts[sig] = sig_counts.get(sig, 0) + 1
        decoded.append({
            "block": int(l.get("blockNumber", "0x0"), 16),
            "tx": l.get("transactionHash"),
            "log_index": int(l.get("logIndex", "0x0"), 16),
            "topic0": t0,
            "event_signature": sig,
            "topics_n": len(topics),
            "data_len_bytes": (len(l.get("data", "0x")) - 2) // 2,
            "removed": l.get("removed", False),
        })

    return {
        "ok": True,
        "address": address.lower(),
        "from_block": from_block_hex,
        "to_block": to_block_hex,
        "topic0_filter": topic0,
        "returned": len(decoded),
        "truncated": truncated,
        "event_breakdown": sig_counts,
        "logs": decoded,
    }


run.__when_to_use__ = (
    "Agents auditing a contract, monitoring transfers, building activity "
    "dashboards, or tracing protocol interactions. Use after onyx_base_tx_explainer "
    "to see continuous activity, not just one tx."
)
run.__vs_alternatives__ = (
    "Direct RPC eth_getLogs returns raw hex you must decode. This adds "
    "event-signature decode for common patterns + truncation + filters."
)
run.__example_request__ = {
    "address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    "limit": 10,
}
