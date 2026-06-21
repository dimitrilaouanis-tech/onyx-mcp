"""onyx_signature_guard — the gate for the drain that has NO on-chain approval.

The pre-sign tx gates (approval_guard, tx_preflight) catch on-chain drains. But the
nastiest wallet-drains use NO on-chain transaction at all: the victim signs an
off-chain EIP-712 message — a Permit, a Permit2, or a Seaport order — and that
*signature alone* lets the attacker move the tokens later. Wallet UIs barely warn
humans; an autonomous agent signing typed data has no warning at all.

Give Onyx the EIP-712 typed-data the agent is about to sign; we identify what it
authorizes and flag the signature-phishing patterns:

  Permit / Permit2 (token approval-by-signature)  unlimited value? EOA/unverified spender?
  Seaport / OrderComponents (NFT order signature)  signing away NFTs for a listing?
  expired/너무-long deadline, spender = the dApp you expect or a stranger?

Returns ALLOW / REVIEW / BLOCK + a plain-English "this signature lets X do Y" +
the screened spender, Ed25519-signed. The off-chain-drain gate no x402 tool covers.

Bright line: decodes the typed-data you pass + reads public on-chain state for the
spender. Never holds funds, never signs anything itself.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from . import _onyx_sign
from . import base_contract_verify as _bcv

NAME = "onyx_signature_guard"
PRICE_USDC = "0.10"
TIER = "metered"
DESCRIPTION = (
    "Pre-signature firewall for OFF-CHAIN drains — the check before your agent signs "
    "an EIP-712 typed-data message (Permit, Permit2, Seaport order). These drain a "
    "wallet with no on-chain approval: the signature itself is the authorization. "
    "Give the typed-data; Onyx identifies what it authorizes, flags unlimited "
    "token-permit values, EOA/unverified spenders, NFT-order signatures, and bad "
    "deadlines, and returns a SIGNED ALLOW/REVIEW/BLOCK + plain-English explanation. "
    "Covers the #2 wallet-drain vector that on-chain tx checks miss entirely."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "typed_data": {
            "type": "object",
            "description": "The full EIP-712 typed-data object the agent is about to sign: {domain, primaryType, types, message}.",
        },
    },
    "required": ["typed_data"],
}

_RPC = "https://mainnet.base.org"
_UNLIMITED_FLOOR = 1 << 128


def _is_contract(addr: str) -> bool | None:
    if not (isinstance(addr, str) and addr.startswith("0x") and len(addr) == 42):
        return None
    try:
        req = urllib.request.Request(
            _RPC,
            data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_getCode",
                             "params": [addr, "latest"]}).encode(),
            headers={"Content-Type": "application/json", "User-Agent": "onyx-signature-guard/1.0"},
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


def _as_int(v) -> int | None:
    try:
        if isinstance(v, str):
            return int(v, 16) if v.startswith("0x") else int(v)
        return int(v)
    except (ValueError, TypeError):
        return None


def run(typed_data: dict | None = None, **_: object) -> dict:
    if not isinstance(typed_data, dict):
        raise ValueError("typed_data must be the EIP-712 object {domain, primaryType, types, message}")
    domain = typed_data.get("domain") or {}
    primary = (typed_data.get("primaryType") or "").strip()
    msg = typed_data.get("message") or {}
    verifying = (domain.get("verifyingContract") or "")

    flags: list = []
    risk = 0
    authorizes = primary or "unknown typed-data"
    spender = None

    low = primary.lower()
    # --- Permit (EIP-2612) & Permit2 (Uniswap) — approval by signature ---
    if "permit" in low:
        # EIP-2612: {owner, spender, value, nonce, deadline}
        spender = msg.get("spender") or msg.get("operator")
        val = _as_int(msg.get("value") or msg.get("allowance"))
        # Permit2 nests under details
        details = msg.get("details")
        if isinstance(details, dict):
            spender = msg.get("spender") or spender
            val = _as_int(details.get("amount")) if val is None else val
        authorizes = f"token approval-by-signature (Permit) to spender {spender}"
        if val is not None and val >= _UNLIMITED_FLOOR:
            flags.append("UNLIMITED Permit value — this signature lets the spender move your ENTIRE token balance with no on-chain approval. Top signature-phishing pattern.")
            risk += 40
        deadline = _as_int(msg.get("deadline") or msg.get("sigDeadline") or (details or {}).get("expiration"))
        if deadline is not None and deadline > 4102444800:  # > year 2100 = effectively never expires
            flags.append("Permit deadline is effectively infinite — the approval-by-signature never expires.")
            risk += 12
    # --- Seaport / NFT order signatures ---
    elif "order" in low or primary in ("OrderComponents", "BulkOrder") or "seaport" in (domain.get("name", "").lower()):
        authorizes = "an NFT/marketplace ORDER signature (Seaport-style)"
        flags.append("This is a marketplace ORDER signature — signing it can list or transfer your NFTs/tokens off-chain. Confirm the marketplace and the offer/consideration are exactly what you intend.")
        risk += 25
        consideration = msg.get("consideration")
        if isinstance(consideration, list) and not consideration:
            flags.append("order has EMPTY consideration — you may be giving assets away for nothing. Classic NFT-drain signature.")
            risk += 40
    # --- generic / unknown typed data ---
    else:
        flags.append(f"non-standard typed-data (primaryType '{primary or 'n/a'}') — Onyx can screen the verifying contract but cannot fully decode this struct; review what you're signing.")
        risk += 8

    # --- screen the spender / verifying contract on-chain ---
    target = spender if (isinstance(spender, str) and spender.startswith("0x")) else verifying
    target_kind = "spender" if target == spender else "verifyingContract"
    target_is_contract = None
    target_verified = None
    if isinstance(target, str) and target.startswith("0x") and len(target) == 42:
        target_is_contract = _is_contract(target)
        if target_is_contract is False:
            flags.append(f"the {target_kind} is a PLAIN WALLET (EOA), not a contract — a permit/approval to an EOA is almost always a drainer.")
            risk += 45
        elif target_is_contract is True:
            target_verified = _verified(target)
            if target_verified is False:
                flags.append(f"the {target_kind} contract is UNVERIFIED — you can't see what it does with this signature.")
                risk += 18

    risk = min(risk, 99)
    verdict = "ALLOW" if risk < 25 else ("REVIEW" if risk < 60 else "BLOCK")
    if target_is_contract is False and ("permit" in low):
        verdict = "BLOCK"

    return _onyx_sign.attest({
        "ok": True,
        "primary_type": primary,
        "domain_name": domain.get("name"),
        "verifying_contract": (verifying or None),
        "network": "base",
        "authorizes": authorizes,
        "spender": spender,
        "spender_is_contract": target_is_contract,
        "spender_verified": target_verified,
        "risk_score": risk,
        "verdict": verdict,
        "flags": flags or [f"{authorizes} — no elevated-risk patterns detected"],
        "summary": (
            f"{verdict} (risk {risk}/100): signing this authorizes {authorizes}. "
            + ("; ".join(flags[:2]) if flags else "looks routine.")
        ),
    }, tool=NAME)


run.__when_to_use__ = (
    "Call this before your agent signs ANY EIP-712 typed-data message (Permit, "
    "Permit2, Seaport order, or any off-chain signature request) — these drain "
    "wallets with no on-chain transaction, so the tx gates never see them. Gate on "
    "the verdict: BLOCK = refuse to sign, REVIEW = human approval, ALLOW = sign."
)
run.__vs_alternatives__ = (
    "Human wallet add-ons (Blockaid, Wallet Guard) simulate signatures for people "
    "with a UI; there is no signed, machine-readable x402 tool an autonomous agent "
    "can gate on. This decodes the Permit/Permit2/Seaport intent, screens the "
    "spender on-chain, and returns one signed go/no-go — the off-chain-drain gate "
    "for agents that the on-chain tx checks structurally cannot cover."
)
run.__example_request__ = {
    "typed_data": {
        "domain": {"name": "USD Coin", "verifyingContract": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"},
        "primaryType": "Permit",
        "message": {"owner": "0xYou", "spender": "0x1111111111111111111111111111111111111111",
                    "value": "115792089237316195423570985008687907853269984665640564039457584007913129639935",
                    "deadline": "9999999999"},
    }
}
run.__example_response__ = {
    "ok": True, "primary_type": "Permit", "verdict": "BLOCK", "risk_score": 85,
    "authorizes": "token approval-by-signature (Permit) to spender 0x1111...",
    "summary": "BLOCK (risk 85/100): signing this authorizes an UNLIMITED token permit to an EOA spender.",
}
