"""ERC-20 token metadata via Base public RPC. Zero-cost reads."""
from __future__ import annotations

import time
import httpx

NAME = "onyx_token_metadata"
PRICE_USDC = "0.001"
TIER = "metered"
DESCRIPTION = (
    "ERC-20 token metadata lookup on Base mainnet: name, symbol, decimals, "
    "and total supply for any contract address. Use before transacting with "
    "a token agents discover at runtime — confirms the contract is a real "
    "ERC-20 and resolves human-readable identity. Reads via Base public RPC, "
    "~150-300ms typical. Pairs with onyx_base_tx_decode for full token-flow "
    "context. No vendor key needed."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "address": {"type": "string", "description": "0x-prefixed ERC-20 contract address on Base"},
    },
    "required": ["address"],
}

_RPC = "https://mainnet.base.org"
# 4-byte selectors: name(), symbol(), decimals(), totalSupply()
_NAME = "0x06fdde03"
_SYMBOL = "0x95d89b41"
_DECIMALS = "0x313ce567"
_TOTAL_SUPPLY = "0x18160ddd"


def _call(addr: str, data: str) -> str | None:
    r = httpx.post(_RPC, json={
        "jsonrpc": "2.0", "id": 1, "method": "eth_call",
        "params": [{"to": addr, "data": data}, "latest"]
    }, timeout=8.0)
    r.raise_for_status()
    return r.json().get("result")


def _decode_string(hex_data: str) -> str | None:
    if not hex_data or hex_data == "0x":
        return None
    try:
        h = hex_data[2:]
        # ABI-encoded string: offset(32) + length(32) + data
        if len(h) >= 128:
            length = int(h[64:128], 16)
            raw = bytes.fromhex(h[128:128 + length * 2])
            return raw.decode("utf-8", "replace")
        # Some non-standard tokens return a fixed bytes32
        return bytes.fromhex(h[:64]).rstrip(b"\x00").decode("utf-8", "replace") or None
    except Exception:
        return None


def run(address: str, **_: object) -> dict:
    addr = (address or "").strip().lower()
    if not addr.startswith("0x") or len(addr) != 42:
        raise ValueError("address must be 0x-prefixed 20-byte hex")
    started = time.time()
    name = _decode_string(_call(addr, _NAME) or "")
    symbol = _decode_string(_call(addr, _SYMBOL) or "")
    decimals_raw = _call(addr, _DECIMALS)
    total_raw = _call(addr, _TOTAL_SUPPLY)
    decimals = int(decimals_raw, 16) if decimals_raw and decimals_raw != "0x" else None
    total = int(total_raw, 16) if total_raw and total_raw != "0x" else None
    is_erc20 = bool(name and symbol and decimals is not None)
    return {
        "address": addr,
        "name": name,
        "symbol": symbol,
        "decimals": decimals,
        "total_supply_raw": str(total) if total is not None else None,
        "total_supply": (total / (10 ** decimals)) if (total is not None and decimals is not None) else None,
        "is_erc20": is_erc20,
        "source": "onyx.base_rpc",
        "elapsed_ms": int((time.time() - started) * 1000),
    }
