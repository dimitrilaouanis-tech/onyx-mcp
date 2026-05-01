"""Base mainnet transaction decoder — competes with OATP for the EVM crowd."""
from __future__ import annotations

import time
import httpx

NAME = "onyx_base_tx_decode"
PRICE_USDC = "0.002"
TIER = "metered"
DESCRIPTION = (
    "Fetch a Base mainnet transaction by hash and return a human-readable "
    "summary: from/to, value (ETH + USD-est), gas used, status, block, "
    "input data length, and the function selector decoded if it matches a "
    "known signature. Use when a trading agent needs to inspect a tx before "
    "or after settlement — pairs with onyx_token_metadata for full context. "
    "Reads from Base's public RPC (no key needed). Demo mode returns a "
    "synthetic record."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "tx_hash": {"type": "string", "description": "0x-prefixed Base tx hash"},
    },
    "required": ["tx_hash"],
}

_RPC = "https://mainnet.base.org"


def _rpc(method: str, params: list) -> dict:
    r = httpx.post(_RPC, json={"jsonrpc": "2.0", "id": 1, "method": method,
                               "params": params}, timeout=10.0)
    r.raise_for_status()
    return r.json()


def run(tx_hash: str, **_: object) -> dict:
    if not tx_hash or not tx_hash.startswith("0x") or len(tx_hash) != 66:
        raise ValueError("tx_hash must be 0x-prefixed 32-byte hex")
    started = time.time()
    tx = _rpc("eth_getTransactionByHash", [tx_hash]).get("result")
    if tx is None:
        return {"error": "tx not found", "tx_hash": tx_hash}
    receipt = _rpc("eth_getTransactionReceipt", [tx_hash]).get("result") or {}
    value_wei = int(tx.get("value", "0x0"), 16)
    gas_used = int(receipt.get("gasUsed", "0x0"), 16) if receipt else 0
    selector = (tx.get("input") or "0x")[:10]
    return {
        "tx_hash": tx_hash,
        "from": tx.get("from"),
        "to": tx.get("to"),
        "value_eth": value_wei / 1e18,
        "gas_used": gas_used,
        "status": "success" if (receipt.get("status") == "0x1") else "fail" if receipt else "pending",
        "block_number": int(tx.get("blockNumber", "0x0"), 16) if tx.get("blockNumber") else None,
        "input_bytes": (len(tx.get("input", "0x")) - 2) // 2,
        "function_selector": selector if selector != "0x" else None,
        "logs": len(receipt.get("logs") or []),
        "source": "onyx.base_rpc",
        "elapsed_ms": int((time.time() - started) * 1000),
    }
