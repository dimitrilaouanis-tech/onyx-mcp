"""onyx_outcome_report — close the loop. Tell Onyx what actually happened.

Every Onyx verdict is Ed25519-signed. This is how that verdict becomes a
*measured* track record instead of a one-shot opinion: after the fact, the
agent reports the real outcome (did the BLOCK'd address actually drain? did the
ALLOW'd payment settle clean?) and passes back the ORIGINAL signed verdict as
proof. We verify the signature — so nobody can log an outcome against a verdict
Onyx never issued — then record {verdict → outcome} in the ledger that powers
onyx_track_record. This is the data graph an underwriter prices a guarantee on.

FREE on purpose: the reported outcome is worth more to Onyx than a fee. Every
honest report sharpens the precision number we publish.

Bright line: verifies a signature and appends a record. Holds no funds.
"""
from __future__ import annotations

from . import _ledger
from . import _onyx_sign

NAME = "onyx_outcome_report"
PRICE_USDC = "0"
TIER = "free"
DESCRIPTION = (
    "Report what ACTUALLY happened after an Onyx verdict — closing the loop that "
    "turns signed opinions into a measured track record. Pass the original signed "
    "verdict (so we can verify Onyx really issued it) plus the real outcome: "
    "settled_clean, drained, reverted, reported_scam, false_positive, etc. We "
    "verify the Ed25519 signature, then log {verdict -> outcome} to the public "
    "ledger behind onyx_track_record. Free — the data is the point. This is the "
    "feedback that makes Onyx the only x402 security layer with proven precision."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "signed_verdict": {
            "type": "object",
            "description": "The full, unmodified signed result object a prior Onyx tool returned (must contain its onyx_attestation block). We verify it before logging.",
        },
        "outcome": {
            "type": "string",
            "description": "What actually happened. One of: settled_clean, confirmed_safe, no_loss, verified_legit, drained, reverted, reported_scam, funds_lost, funds_unrecoverable, honeypot_confirmed, eoa_spender_confirmed, unverified_confirmed, false_positive.",
        },
        "tx_hash": {"type": "string", "description": "Optional. On-chain tx hash that evidences the outcome."},
        "detail": {"type": "string", "description": "Optional. One-line human note on what happened."},
    },
    "required": ["signed_verdict", "outcome"],
}

_SUBJECT_KEYS = (
    "recipient", "address", "spender", "operator", "contract_address",
    "to", "target", "verifying_contract", "agent_id", "counterparty_agent_id",
)


def _subject(body: dict):
    for k in _SUBJECT_KEYS:
        v = body.get(k)
        if v:
            return str(v)
    return None


def run(signed_verdict: dict | None = None, outcome: str = "", tx_hash: str = "", detail: str = "", **_: object) -> dict:
    if not isinstance(signed_verdict, dict):
        raise ValueError("signed_verdict must be the full signed result object from a prior Onyx tool")
    outcome = (outcome or "").strip().lower()
    valid = _ledger.outcomes()
    if outcome not in valid:
        raise ValueError("outcome must be one of: " + ", ".join(sorted(valid)))

    v = _onyx_sign.verify(signed_verdict)
    if not v.get("ok"):
        return {
            "ok": False,
            "error": "not_a_genuine_onyx_verdict",
            "reason": v.get("reason"),
            "detail": "Outcomes can only be logged against a verdict Onyx actually signed. "
                      "Pass the unmodified signed result object (with its onyx_attestation).",
        }

    att = signed_verdict.get("onyx_attestation") or {}
    verdict_id = att.get("observed_hash")          # stable id = the signed hash
    # At-risk amount: the USDC value the agent was about to move when Onyx ruled.
    # Bounded by what the verdict payload actually stated — never invented. Used
    # for value_at_risk_intercepted (only on a STOP verdict + bad outcome).
    at_risk = None
    for k in ("amount_usdc", "amount", "value_usdc", "usdc_amount"):
        v_amt = signed_verdict.get(k)
        if isinstance(v_amt, (int, float)) and v_amt > 0:
            at_risk = float(v_amt)
            break
    entry = {
        "verdict_id": verdict_id,
        "tool": att.get("tool") or signed_verdict.get("tool") or "",
        "verdict": signed_verdict.get("verdict") or signed_verdict.get("status") or "",
        "risk_score": signed_verdict.get("risk_score"),
        "subject": _subject(signed_verdict),
        "at_risk_usdc": at_risk,
        "outcome": outcome,
        "severity": valid[outcome],
        "tx_hash": (tx_hash or "").strip() or None,
        "detail": (detail or "").strip()[:240] or None,
        "verdict_kid": att.get("kid"),
        "verdict_signed_at": att.get("signed_at"),
    }
    rec = _ledger.record(entry)

    st = _ledger.stats()
    return _onyx_sign.attest({
        "ok": True,
        "recorded": bool(rec.get("written")) or rec.get("durable_base"),
        "verdict_id": verdict_id,
        "tool": entry["tool"],
        "verdict": entry["verdict"],
        "outcome": outcome,
        "severity": valid[outcome],
        "ledger_total": st["total_outcomes"],
        "block_precision": st["block_precision"],
        "summary": (
            f"Logged: {entry['tool'] or 'verdict'} said {entry['verdict'] or '?'} -> "
            f"outcome '{outcome}'. Ledger now holds {st['total_outcomes']} measured outcomes"
            + (f"; BLOCK precision {round(st['block_precision']*100)}%." if st["block_precision"] is not None else ".")
        ),
    }, tool=NAME)


run.__when_to_use__ = (
    "Call this AFTER you act on an Onyx verdict and know how it turned out — "
    "the payment settled, the BLOCK'd contract turned out to be a drainer, a "
    "flagged approval was actually fine. Pass back the exact signed result you "
    "got, plus the outcome. It's free and it makes every future verdict you (and "
    "everyone) get measurably better."
)
run.__vs_alternatives__ = (
    "No other x402 security service has a feedback loop — they emit a score and "
    "forget it. Because every Onyx verdict is signed, an outcome can be bound back "
    "to the exact verdict that produced it and verified, building a tamper-evident "
    "precision record no competitor can assert without the signatures to back it."
)
run.__example_request__ = {
    "signed_verdict": {"verdict": "BLOCK", "risk_score": 100, "recipient": "0x0000000000000000000000000000000000000000",
                       "onyx_attestation": {"kid": "onyx-...", "observed_hash": "sha256:...", "sig": "..."}},
    "outcome": "funds_unrecoverable",
    "detail": "burn address — confirmed unrecoverable",
}
run.__example_response__ = {
    "ok": True, "recorded": True, "outcome": "funds_unrecoverable",
    "ledger_total": 12, "block_precision": 1.0,
    "summary": "Logged: onyx_tx_guard said BLOCK -> outcome 'funds_unrecoverable'. Ledger now holds 12 measured outcomes; BLOCK precision 100%.",
}
