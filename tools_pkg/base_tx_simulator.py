"""Base mainnet transaction simulator — pre-flight any tx without sending.

OATP's Solana tx_simulator: 1,304 unique paying agents at $0.20/call.
Verified empty slot on Base. Onyx ships at $0.10 — half OATP's price,
only Base-native pre-flight simulator on Bazaar today.

Uses eth_call (read-only EVM execution against latest state) to predict
whether a tx would succeed, what it would return, and roughly how much
gas it would burn. Does NOT submit on-chain.
"""
from __future__ import annotations

import time
import httpx

NAME = "onyx_base_tx_simulator"
PRICE_USDC = "0.10"
TIER = "metered"
DESCRIPTION = (
    "Simulate a Base mainnet transaction before sending it. Returns success/"
    "revert prediction, the revert reason if any, decoded return data, and "
    "an estimated gas figure. Use as a pre-flight check inside a trading "
    "agent's tool-call dispatcher — agents should simulate before signing "
    "to avoid paying gas on a doomed tx. Direct equivalent of OATP's Solana "
    "tx_simulator ($0.20, 1,304 unique paying agents) — Onyx is the first "
    "to ship this on Base mainnet at $0.10. Read-only — never submits."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "from_address": {"type": "string", "description": "0x-prefixed sender"},
        "to_address": {"type": "string", "description": "0x-prefixed contract or wallet"},
        "data": {"type": "string", "description": "Hex-encoded calldata (default 0x)"},
        "value_wei": {"type": "string", "description": "ETH wei to send (default 0)"},
        "block": {"type": "string", "description": "block tag (latest/pending/0x...) default latest"},
    },
    "required": ["to_address"],
}

_RPC = "https://mainnet.base.org"


def _rpc(method: str, params: list, timeout: float = 10.0) -> dict:
    r = httpx.post(_RPC, json={"jsonrpc": "2.0", "id": 1, "method": method,
                               "params": params}, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _decode_revert(raw: str) -> str | None:
    """Best-effort decode of a Solidity revert string."""
    if not raw or raw == "0x" or len(raw) < 10:
        return None
    # Selector for Error(string) is 0x08c379a0
    if raw[:10].lower() == "0x08c379a0":
        try:
            length = int(raw[74:138], 16)
            return bytes.fromhex(raw[138:138 + length * 2]).decode("utf-8", "replace")
        except Exception:
            return None
    # Panic(uint256) is 0x4e487b71
    if raw[:10].lower() == "0x4e487b71":
        try:
            code = int(raw[10:], 16)
            return f"Panic(0x{code:02x})"
        except Exception:
            return None
    return None


def run(to_address: str,
        from_address: str | None = None,
        data: str = "0x",
        value_wei: str = "0",
        block: str = "latest",
        **_: object) -> dict:
    if not to_address or not to_address.startswith("0x") or len(to_address) != 42:
        raise ValueError("to_address must be 0x-prefixed 20-byte hex")
    started = time.time()

    call_obj: dict = {"to": to_address.lower(), "data": data or "0x"}
    if from_address:
        call_obj["from"] = from_address.lower()
    if value_wei and value_wei != "0":
        try:
            call_obj["value"] = hex(int(value_wei))
        except (TypeError, ValueError):
            raise ValueError("value_wei must be a decimal integer string")

    out: dict = {
        "to": to_address,
        "from": from_address,
        "data_bytes": (len(data) - 2) // 2 if data and data != "0x" else 0,
        "value_wei": value_wei,
        "block": block,
        "source": "onyx.base_rpc",
    }

    # eth_call for success/return-data
    call_resp = _rpc("eth_call", [call_obj, block])
    err = call_resp.get("error")
    result = call_resp.get("result")
    if err:
        msg = err.get("message", "") if isinstance(err, dict) else str(err)
        out["success"] = False
        out["revert_reason"] = _decode_revert(err.get("data", "") if isinstance(err, dict) else "") or msg
        out["raw_error"] = msg[:300]
    else:
        out["success"] = True
        out["return_data"] = result
        out["return_bytes"] = (len(result or "0x") - 2) // 2

    # eth_estimateGas for gas projection (separate call, may fail even if eth_call succeeds in edge cases)
    gas_resp = _rpc("eth_estimateGas", [call_obj])
    gas_err = gas_resp.get("error")
    if gas_err:
        out["gas_estimate"] = None
        out["gas_estimate_error"] = (gas_err.get("message", "") if isinstance(gas_err, dict) else str(gas_err))[:200]
    else:
        try:
            out["gas_estimate"] = int(gas_resp.get("result", "0x0"), 16)
        except (TypeError, ValueError):
            out["gas_estimate"] = None

    out["elapsed_ms"] = int((time.time() - started) * 1000)
    return out
