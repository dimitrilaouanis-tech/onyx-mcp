"""onyx_secure_payment — the secure-transaction RAIL. One signed clearance to send.

This is the business centerpiece: high-value agent transactions pass through
Onyx for a single signed PASS / REVIEW / FAIL clearance before the money moves.
It fuses the whole security suite in one call:

  recipient screen   → tx_guard (EOA/contract, age, burn-guard, risk)
  contract audit      → contract_audit (if paying a contract: proxy/self-destruct/vulns)
  counterparty trust  → agent_reputation (if an ERC-8004 agent id is given)

…and quotes the **Onyx take-rate** (basis points of the value secured). Today
the take-rate is a transparent quote alongside the per-call fee (path A, no
custody). When the Onyx non-custodial facilitator goes live (path B), this same
fee becomes the on-chain skim — funds never rest with us. The economics are in
the system now; the rail is built to flip.

Every clearance is Ed25519-signed: an agent can PROVE it cleared the payment
through Onyx before sending. Bright line: reads public on-chain state + screens
the recipient; never takes custody of funds.
"""
from __future__ import annotations

import os
import time

from . import _onyx_sign
from . import tx_guard as _txg
from . import contract_audit as _audit
from . import agent_reputation as _rep

NAME = "onyx_secure_payment"
PRICE_USDC = "0.25"
TIER = "premium"

# The Onyx take-rate. Today: a transparent quote (path A). When the non-custodial
# facilitator ships (path B): the on-chain skim. Tunable via env, capped for sanity.
_TAKE_RATE_BPS = int(os.environ.get("ONYX_TAKE_RATE_BPS", "10"))   # 10 bps = 0.10%
_MIN_FEE_USDC = float(os.environ.get("ONYX_MIN_FEE_USDC", "0.01"))
_MAX_FEE_USDC = float(os.environ.get("ONYX_MAX_FEE_USDC", "500"))

DESCRIPTION = (
    "Secure-transaction RAIL: one signed clearance before an agent sends funds. "
    "Give recipient + amount (and optionally a contract address or counterparty "
    "ERC-8004 agent id); Onyx runs the full security stack — recipient firewall, "
    "contract audit, counterparty reputation — and returns a single PASS / REVIEW "
    "/ FAIL verdict + risk score, plus the Onyx take-rate quote (bps of value "
    "secured). Ed25519-signed so the clearance is provable. The check a serious "
    "agent runs before moving real money. Onyx never takes custody."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "recipient": {
            "type": "string",
            "description": "0x recipient address the agent is about to pay (Base).",
        },
        "amount_usdc": {
            "type": "number",
            "description": "Amount about to be sent, in USDC. Drives both the risk threshold and the take-rate quote.",
        },
        "contract_address": {
            "type": "string",
            "description": "Optional. If the payment interacts with a contract, its 0x address — triggers a full contract audit.",
        },
        "counterparty_agent_id": {
            "type": "integer",
            "description": "Optional. If paying another AI agent, its ERC-8004 id — triggers a reputation check.",
        },
    },
    "required": ["recipient", "amount_usdc"],
}

_RANK = {"ALLOW": 0, "TRUSTED": 0, "NEW": 1, "REVIEW": 1, "UNKNOWN": 1, "CAUTION": 2, "BLOCK": 3, "FAIL": 3}


def _fee(amount: float) -> float:
    raw = amount * _TAKE_RATE_BPS / 10000.0
    return round(min(_MAX_FEE_USDC, max(_MIN_FEE_USDC, raw)), 6)


def run(recipient: str = "", amount_usdc: float = 0.0,
        contract_address: str = "", counterparty_agent_id: int = 0, **_: object) -> dict:
    recipient = (recipient or "").strip()
    if not (recipient.startswith("0x") and len(recipient) == 42):
        raise ValueError("recipient must be a 0x-prefixed 20-byte hex address")
    try:
        amount = float(amount_usdc)
    except (TypeError, ValueError):
        raise ValueError("amount_usdc must be a number")
    checked_at = int(time.time())

    checks: dict = {}
    worst = 0  # 0 pass / 1 review / 2 caution / 3 fail

    # 1) recipient firewall (always) — note its result is itself signed; we re-aggregate
    try:
        g = _txg.run(address=recipient, amount_usdc=amount)
        checks["recipient_firewall"] = {"verdict": g.get("verdict"), "risk": g.get("risk_score"), "flags": g.get("flags", [])[:3]}
        worst = max(worst, _RANK.get(g.get("verdict"), 1))
    except Exception as e:
        checks["recipient_firewall"] = {"verdict": "REVIEW", "error": str(e)[:80]}
        worst = max(worst, 1)

    # 2) contract audit (if paying a contract)
    if contract_address and contract_address.startswith("0x") and len(contract_address) == 42:
        try:
            a = _audit.run(address=contract_address, deep=True)
            checks["contract_audit"] = {"verdict": a.get("verdict"), "risk": a.get("risk_score"),
                                        "is_proxy": a.get("is_proxy"), "findings": a.get("finding_count")}
            worst = max(worst, _RANK.get(a.get("verdict"), 1))
        except Exception as e:
            checks["contract_audit"] = {"verdict": "REVIEW", "error": str(e)[:80]}
            worst = max(worst, 1)

    # 3) counterparty agent reputation (if an ERC-8004 id is given)
    if counterparty_agent_id:
        try:
            r = _rep.run(agent_id=int(counterparty_agent_id))
            checks["counterparty_reputation"] = {"verdict": r.get("verdict"), "trust": r.get("trust_score"),
                                                 "registered": r.get("registered")}
            worst = max(worst, _RANK.get(r.get("verdict"), 1))
        except Exception as e:
            checks["counterparty_reputation"] = {"verdict": "REVIEW", "error": str(e)[:80]}
            worst = max(worst, 1)

    clearance = ["PASS", "REVIEW", "REVIEW", "FAIL"][worst]
    fee = _fee(amount)

    return _onyx_sign.attest({
        "ok": True,
        "recipient": recipient.lower(),
        "amount_usdc": amount,
        "checked_at": checked_at,
        "checked_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(checked_at)),
        "network": "base",
        "clearance": clearance,
        "checks": checks,
        "onyx_take_rate_bps": _TAKE_RATE_BPS,
        "onyx_fee_usdc": fee,
        "onyx_fee_basis": "quote (path A — no custody); becomes on-chain skim when the Onyx facilitator is live (path B)",
        "summary": (
            f"{clearance} to send ${amount:g} -> {recipient[:10]}...: "
            + ", ".join(f"{k}={v.get('verdict')}" for k, v in checks.items())
            + f" | Onyx fee {_TAKE_RATE_BPS}bps = ${fee:g}"
        ),
    }, tool=NAME)


run.__when_to_use__ = (
    "Before an agent moves real money — the single gate that runs the full Onyx "
    "security stack and returns one signed PASS/REVIEW/FAIL. Use it as the "
    "mandatory pre-send check on any payment above a trivial amount: FAIL = "
    "abort, REVIEW = human sign-off, PASS = send. The more an agent is sending, "
    "the more this is worth — and the Onyx fee scales with what it protects."
)
run.__vs_alternatives__ = (
    "No incumbent offers a single signed 'clearance to send' that fuses recipient "
    "screening + contract audit + ERC-8004 counterparty reputation. Running them "
    "separately means 3 calls and no aggregate verdict. This returns one signed "
    "clearance + a transparent value-based fee, and Onyx never takes custody of funds."
)
run.__example_request__ = {"recipient": "0x1111111111111111111111111111111111111111", "amount_usdc": 5000}
run.__example_response__ = {
    "ok": True,
    "clearance": "REVIEW",
    "amount_usdc": 5000,
    "onyx_take_rate_bps": 10,
    "onyx_fee_usdc": 0.5,
    "summary": "REVIEW to send $5000 → 0x11111111…: recipient_firewall=REVIEW | Onyx fee 10bps = $0.5",
}
