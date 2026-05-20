"""x402 settlement receipt verifier.

Given a tx hash on Base or Base Sepolia, fetch the transaction + receipt
via public RPC, decode the USDC Transfer event log, and verify the claim
'this tx was an x402 settlement from <from> to <payTo> for <amount> USDC'.

Lane: no public x402-receipt verifier exists. Agents reconciling spend or
service operators auditing payments need this. Free tier — pure read.

Stdlib-only. SSRF: only public RPC endpoints from a fixed allowlist.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

NAME = "onyx_x402_receipt_verify"
PRICE_USDC = "0"
TIER = "free"
DESCRIPTION = (
    "Verify an x402 USDC settlement on Base or Base Sepolia. Given a tx "
    "hash, decodes the USDC Transfer log and confirms (or refutes) a claim "
    "of the form: 'tx X moved $Y USDC from A to B'. Returns success status, "
    "actual decoded values, and a clear discrepancy report if any field "
    "doesn't match. Free tier — useful for agents reconciling spend and "
    "operators auditing inbound payments."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "tx_hash": {
            "type": "string",
            "description": "0x-prefixed 32-byte tx hash to verify.",
        },
        "network": {
            "type": "string",
            "enum": ["base", "base-sepolia"],
            "default": "base",
            "description": "Chain to query. Must match where the tx was mined.",
        },
        "expected_from": {
            "type": "string",
            "description": "Optional. Expected sender address (0x...). If provided, verifier checks Transfer.from matches.",
        },
        "expected_to": {
            "type": "string",
            "description": "Optional. Expected recipient address (0x...). If provided, verifier checks Transfer.to matches.",
        },
        "expected_amount_usdc": {
            "type": "number",
            "description": "Optional. Expected USDC amount (whole USDC, not atomic). If provided, verifier checks Transfer.value matches (within 0.000001 tolerance).",
        },
    },
    "required": ["tx_hash"],
}

_TX_RX = re.compile(r"^0x[a-fA-F0-9]{64}$")
_ADDR_RX = re.compile(r"^0x[a-fA-F0-9]{40}$")

_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

_RPCS = {
    "base":         ["https://base-rpc.publicnode.com", "https://base.gateway.tenderly.co", "https://1rpc.io/base", "https://base.llamarpc.com"],
    "base-sepolia": ["https://base-sepolia.gateway.tenderly.co", "https://base-sepolia-rpc.publicnode.com", "https://sepolia.base.org"],
}
_USDC = {
    "base":         "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
    "base-sepolia": "0x036cbd53842c5426634e7929541ec2318f3dcf7e",
}
_USDC_DECIMALS = 6


def _rpc_call(rpc_url: str, method: str, params: list, timeout: float = 10.0) -> dict:
    req = urllib.request.Request(
        rpc_url,
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; OnyxReceiptVerify/1.0)",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _rpc(network: str, method: str, params: list) -> dict:
    last_err = None
    for url in _RPCS[network]:
        try:
            r = _rpc_call(url, method, params)
            if "error" in r:
                last_err = r["error"].get("message", "")[:200]
                continue
            return r
        except Exception as e:
            last_err = str(e)[:160]
            continue
    raise RuntimeError(f"all RPCs failed: {last_err}")


def _topic_to_addr(topic: str) -> str:
    return "0x" + topic[-40:].lower()


def _hex_to_int(hx) -> int:
    if not isinstance(hx, str):
        return 0
    return int(hx, 16) if hx.startswith("0x") else 0


def _addr_eq(a: str, b: str) -> bool:
    return a.lower() == b.lower()


def run(
    tx_hash: str,
    network: str = "base",
    expected_from: str | None = None,
    expected_to: str | None = None,
    expected_amount_usdc: float | None = None,
    **_: object,
) -> dict:
    if not isinstance(tx_hash, str) or not _TX_RX.match(tx_hash.strip()):
        raise ValueError("tx_hash must be 0x-prefixed 32-byte hex")
    if network not in _RPCS:
        raise ValueError(f"network must be one of {list(_RPCS.keys())}")
    for label, val in (("expected_from", expected_from), ("expected_to", expected_to)):
        if val is not None and not _ADDR_RX.match(val.strip()):
            raise ValueError(f"{label} must be 0x-prefixed 20-byte hex")

    tx_hash = tx_hash.strip()
    usdc = _USDC[network]

    # Fetch tx + receipt
    try:
        tx_resp = _rpc(network, "eth_getTransactionByHash", [tx_hash])
        rcpt_resp = _rpc(network, "eth_getTransactionReceipt", [tx_hash])
    except Exception as e:
        return {"ok": False, "error": f"rpc fetch failed: {e}", "tx_hash": tx_hash, "network": network}

    tx = tx_resp.get("result")
    receipt = rcpt_resp.get("result")
    if not tx:
        return {"ok": False, "error": "transaction not found on this network", "tx_hash": tx_hash, "network": network}
    if not receipt:
        return {"ok": False, "error": "receipt not available (tx may be pending)", "tx_hash": tx_hash, "network": network}

    status = _hex_to_int(receipt.get("status", "0x0"))
    if status != 1:
        return {
            "ok": False,
            "error": "transaction reverted (receipt.status != 1)",
            "tx_hash": tx_hash, "network": network,
            "tx_status": status,
        }

    # Find USDC Transfer log
    transfers = []
    for log in receipt.get("logs") or []:
        if (log.get("address") or "").lower() != usdc.lower():
            continue
        topics = log.get("topics") or []
        if len(topics) < 3 or topics[0].lower() != _TRANSFER_TOPIC:
            continue
        transfers.append({
            "from": _topic_to_addr(topics[1]),
            "to":   _topic_to_addr(topics[2]),
            "amount_atomic": _hex_to_int(log.get("data", "0x0")),
            "amount_usdc": _hex_to_int(log.get("data", "0x0")) / (10 ** _USDC_DECIMALS),
            "log_index": _hex_to_int(log.get("logIndex", "0x0")),
        })

    if not transfers:
        return {
            "ok": False,
            "error": "no USDC Transfer event in receipt — not a USDC settlement",
            "tx_hash": tx_hash, "network": network,
            "decoded_transfers": [],
            "logs_seen": len(receipt.get("logs") or []),
        }

    primary = transfers[0]
    discrepancies = []
    if expected_from is not None and not _addr_eq(primary["from"], expected_from):
        discrepancies.append({"field": "from", "expected": expected_from.lower(), "actual": primary["from"]})
    if expected_to is not None and not _addr_eq(primary["to"], expected_to):
        discrepancies.append({"field": "to", "expected": expected_to.lower(), "actual": primary["to"]})
    if expected_amount_usdc is not None:
        if abs(primary["amount_usdc"] - float(expected_amount_usdc)) > 1e-6:
            discrepancies.append({"field": "amount_usdc",
                                  "expected": float(expected_amount_usdc),
                                  "actual": primary["amount_usdc"]})

    verified = len(discrepancies) == 0

    return {
        "ok": True,
        "verified": verified,
        "tx_hash": tx_hash,
        "network": network,
        "block_number": _hex_to_int(receipt.get("blockNumber", "0x0")),
        "tx_status": status,
        "usdc_contract": usdc,
        "decoded_transfers": transfers,
        "primary_transfer": primary,
        "discrepancies": discrepancies,
        "summary": (
            f"PASS: tx {tx_hash[:12]}... moved {primary['amount_usdc']} USDC "
            f"from {primary['from']} to {primary['to']} on {network}."
            if verified else
            f"FAIL: {len(discrepancies)} discrepancy/ies between expected and decoded."
        ),
    }


run.__when_to_use__ = (
    "An agent or operator wants to confirm a tx hash represents a real x402 "
    "USDC settlement with specific from/to/amount. Use for reconciling spend, "
    "auditing inbound payments, fraud prevention, or proving completion."
)
run.__vs_alternatives__ = (
    "Block explorers show tx data but require manual interpretation. Etherscan "
    "API requires keys + parsing. This tool returns a single yes/no verified "
    "boolean plus structured discrepancies — one call, no manual decoding."
)
run.__example_request__ = {
    "tx_hash": "0x" + "a" * 64,
    "network": "base",
    "expected_to": "0xA60939FFf9c04a61c0c0649943675e16A12D7074",
    "expected_amount_usdc": 0.10,
}
run.__example_response__ = {
    "ok": True,
    "verified": True,
    "tx_hash": "0x...",
    "primary_transfer": {"from": "0x...", "to": "0xA609...", "amount_usdc": 0.10},
    "discrepancies": [],
    "summary": "PASS: tx 0xaaaaaaaaaaaa... moved 0.1 USDC from 0x... to 0xA609... on base.",
}
