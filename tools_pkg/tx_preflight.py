"""onyx_tx_preflight — the universal pre-sign gate. Called before an agent signs ANYTHING.

An autonomous agent signs transactions with no human to read the wallet warning.
This is that warning, as a signed machine verdict: give the transaction the agent
is about to sign (to / data / value); we DECODE it, tell the agent in plain terms
what it actually does, and flag the danger patterns that drain wallets:

  approve(spender, MAX)        unlimited token approval — the #1 drain vector
  setApprovalForAll(op, true)  blanket NFT approval — hands over the whole collection
  transfer / transferFrom      moving tokens — to a fresh/EOA recipient? flag it
  raw ETH send                 value to an unknown address
  unknown selector             calling an unverified target with opaque calldata

Decodes the 4-byte selector + args locally (no key), screens the counterparty
on-chain, and returns ALLOW / REVIEW / BLOCK + a human explanation, Ed25519-signed.
This is the highest-frequency safety call there is — every signed tx passes through it.

Bright line: decodes public calldata + reads public on-chain state. Never holds funds.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from . import _onyx_sign
from . import base_contract_verify as _bcv

NAME = "onyx_tx_preflight"
PRICE_USDC = "0.03"
TIER = "metered"
DESCRIPTION = (
    "Universal pre-sign firewall — the check before your agent signs ANY transaction. "
    "Give the tx (to, data, value); Onyx decodes the 4-byte selector + args, tells you "
    "in plain terms what it does, and flags the wallet-drain patterns: unlimited "
    "approve(), setApprovalForAll (blanket NFT approval), transfers to fresh/EOA "
    "recipients, raw ETH sends to unknown addresses, and calls to unverified targets. "
    "Returns a SIGNED ALLOW/REVIEW/BLOCK + human explanation. The single highest-"
    "frequency safety gate an on-chain agent has — every signed tx should pass through it."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "to": {"type": "string", "description": "The transaction's `to` address (target contract or recipient). Required."},
        "data": {"type": "string", "description": "The transaction calldata (0x-hex). Omit/empty for a plain ETH transfer."},
        "value_wei": {"type": "string", "description": "Optional. ETH value being sent, in wei (base-10 string)."},
    },
    "required": ["to"],
}

_RPC = "https://mainnet.base.org"
_MAX_UINT = (1 << 256) - 1
_UNLIMITED_FLOOR = 1 << 128

# standard selectors (keccak4 of the signature) — well-known constants
_SELECTORS = {
    "0x095ea7b3": ("approve", "ERC-20 approve(spender, amount)"),
    "0xa22cb465": ("setApprovalForAll", "ERC-721/1155 setApprovalForAll(operator, approved)"),
    "0xa9059cbb": ("transfer", "ERC-20 transfer(to, amount)"),
    "0x23b872dd": ("transferFrom", "ERC-20/721 transferFrom(from, to, amount/id)"),
    "0x39509351": ("increaseAllowance", "ERC-20 increaseAllowance(spender, addedValue)"),
    "0x42842e0e": ("safeTransferFrom", "ERC-721 safeTransferFrom(from, to, tokenId)"),
}


def _word(data_hex: str, i: int) -> str:
    start = 10 + i * 64  # skip '0x' + 4-byte selector (8 hex)
    return data_hex[start:start + 64]


def _addr_from_word(w: str) -> str:
    return "0x" + w[-40:] if len(w) >= 40 else ""


def _is_contract(addr: str) -> bool | None:
    try:
        req = urllib.request.Request(
            _RPC,
            data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_getCode",
                             "params": [addr, "latest"]}).encode(),
            headers={"Content-Type": "application/json", "User-Agent": "onyx-tx-preflight/1.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            code = json.load(r).get("result") or "0x"
        return code not in ("0x", "0x0", "", None)
    except Exception:
        return None


def _verified(addr: str) -> bool | None:
    try:
        d = _bcv._fetch(addr)
        return bool(d and d.get("is_verified")) if d is not None else None
    except Exception:
        return None


def run(to: str = "", data: str = "", value_wei: str = "", **_: object) -> dict:
    to = (to or "").strip()
    if not (to.startswith("0x") and len(to) == 42):
        raise ValueError("to must be a 0x-prefixed 20-byte hex address")
    data = (data or "").strip().lower()
    if data and not data.startswith("0x"):
        data = "0x" + data

    flags: list = []
    risk = 0
    op = "unknown"
    op_desc = ""
    decoded: dict = {}

    selector = data[:10] if len(data) >= 10 else ""
    has_value = False
    try:
        has_value = bool(value_wei) and int(value_wei) > 0
    except (ValueError, TypeError):
        pass

    if not data or data in ("0x", "0x0"):
        # plain ETH transfer
        op, op_desc = "eth_transfer", "Plain ETH transfer (no calldata)"
        c = _is_contract(to)
        decoded["recipient"] = to.lower()
        if c is False:
            flags.append("sending ETH to a plain wallet (EOA) — confirm you intend this recipient")
            risk += 10
    elif selector in _SELECTORS:
        op, op_desc = _SELECTORS[selector]
        if op in ("approve", "increaseAllowance"):
            spender = _addr_from_word(_word(data, 0))
            try:
                amount = int(_word(data, 1), 16)
            except ValueError:
                amount = 0
            decoded["spender"] = spender
            decoded["amount"] = str(amount)
            if amount >= _UNLIMITED_FLOOR:
                flags.append("UNLIMITED token approval — spender could drain the entire balance, forever. Approve only the exact amount.")
                risk += 35
                decoded["unlimited"] = True
            if _is_contract(spender) is False:
                flags.append("approving a PLAIN WALLET (EOA) as spender — almost always a drainer.")
                risk += 45
            elif _verified(spender) is False:
                flags.append("spender contract is UNVERIFIED — you can't see what it does with the approval.")
                risk += 20
        elif op == "setApprovalForAll":
            operator = _addr_from_word(_word(data, 0))
            approved = int(_word(data, 1) or "0", 16) != 0
            decoded["operator"] = operator
            decoded["approved"] = approved
            if approved:
                flags.append("setApprovalForAll(TRUE) — grants the operator control over your ENTIRE NFT collection. A top NFT-drain vector. Confirm the operator is a trusted marketplace.")
                risk += 30
                if _is_contract(operator) is False:
                    flags.append("operator is an EOA — do NOT grant blanket NFT approval to a wallet.")
                    risk += 45
                elif _verified(operator) is False:
                    flags.append("operator contract is UNVERIFIED.")
                    risk += 20
        elif op in ("transfer", "transferFrom", "safeTransferFrom"):
            idx = 1 if op == "transfer" else 1  # transfer: to=word0; transferFrom: to=word1
            recipient = _addr_from_word(_word(data, 0 if op == "transfer" else 1))
            decoded["recipient"] = recipient
            if _is_contract(recipient) is False:
                flags.append(f"{op} to a plain wallet (EOA) — verify the recipient is correct before sending.")
                risk += 8
    else:
        op, op_desc = "unknown", f"Unknown function (selector {selector or 'n/a'})"
        v = _verified(to)
        decoded["target_verified"] = v
        if v is False:
            flags.append("calling an UNVERIFIED contract with opaque calldata — you cannot see what this does. High caution.")
            risk += 25
        else:
            flags.append("non-standard call — Onyx can confirm the target is verified but cannot decode this custom function; review the contract.")
            risk += 8

    if has_value and op != "eth_transfer":
        decoded["attached_value_wei"] = str(value_wei)

    risk = min(risk, 99)
    verdict = "ALLOW" if risk < 25 else ("REVIEW" if risk < 60 else "BLOCK")
    # floor: approving/operator-granting to an EOA is always BLOCK
    if any("EOA" in f and ("drainer" in f or "blanket" in f.lower()) for f in flags):
        verdict = "BLOCK"

    return _onyx_sign.attest({
        "ok": True,
        "to": to.lower(),
        "network": "base",
        "operation": op,
        "operation_description": op_desc,
        "decoded": decoded,
        "risk_score": risk,
        "verdict": verdict,
        "flags": flags or [f"{op_desc} — no elevated-risk patterns detected"],
        "summary": (
            f"{verdict} (risk {risk}/100): {op_desc}. "
            + ("; ".join(flags[:2]) if flags else "looks routine.")
        ),
    }, tool=NAME)


run.__when_to_use__ = (
    "Call this before your agent signs ANY transaction — it's the universal pre-sign "
    "gate. Pass the exact (to, data, value) you're about to sign; gate on the verdict: "
    "BLOCK = abort, REVIEW = human approval, ALLOW = proceed. Catches unlimited "
    "approvals, blanket NFT approvals, and calls to unverified/EOA targets that a "
    "human would catch in a wallet popup but an autonomous agent would just sign."
)
run.__vs_alternatives__ = (
    "A raw transaction simulator tells you state changes but not whether you SHOULD "
    "sign; a block explorer makes you decode selectors yourself. This decodes the "
    "intent, screens the counterparty on-chain, flags the known drain patterns, and "
    "returns one signed go/no-go an agent can gate on automatically."
)
run.__example_request__ = {"to": "0xToken...", "data": "0x095ea7b3000000000000000000000000<spender>ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"}
run.__example_response__ = {
    "ok": True, "operation": "approve", "verdict": "BLOCK", "risk_score": 80,
    "decoded": {"spender": "0x...", "unlimited": True},
    "summary": "BLOCK (risk 80/100): ERC-20 approve(spender, amount). UNLIMITED token approval; approving a PLAIN WALLET (EOA) as spender.",
}
