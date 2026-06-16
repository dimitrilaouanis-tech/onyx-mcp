"""Fool the Oracle — the unwinnable adversarial game that proves the moat.

A challenger submits what they claim is a genuine Onyx verdict containing a
LIE. The win-check is PURE Ed25519 verification — NO LLM in the trust path
(the Freysa lesson: Freysa fell because a language model was the gatekeeper;
here the gatekeeper is math). You win the pot only if you submit a payload
that (a) verifies against Onyx's public key AND (b) we didn't sign it — i.e.
you forged Ed25519. That is computationally infeasible, so every attempt is
REJECTED, and each rejection is itself a signed receipt the challenger can
verify. The house never risks the pot because the game cannot be won.

Underscore-prefixed → not an auto-discovered tool; the app wires the routes.
"""
from __future__ import annotations

import hashlib
import json
import time

from . import _onyx_sign

# In-memory state (swap for a persistent store before high traffic).
_ATTEMPTS: list[dict] = []
_MAX_KEEP = 500
_STATS = {
    "attempts": 0,
    "forgeries_passed": 0,   # stays 0 unless Ed25519 is broken
    "usd_paid_out": 0.0,     # stays 0 by construction
    "unique_challengers": 0,
    "started_at": None,      # set on first attempt (no Date.now at import)
}
_SEEN: set[str] = set()


def _jcs(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def attempt(submission: dict, challenger: str = "anon", now: int | None = None) -> dict:
    """Judge one forgery attempt. Returns a signed verdict receipt.

    `submission` is whatever the challenger claims is a valid Onyx-signed
    verdict (a JSON object with an `onyx_attestation` block they produced).
    We run the SAME public verifier anyone can run. ok=True would mean they
    forged our signature → they win. It won't be True.
    """
    ts = int(now if now is not None else time.time())
    if _STATS["started_at"] is None:
        _STATS["started_at"] = ts
    _STATS["attempts"] += 1
    if challenger not in _SEEN:
        _SEEN.add(challenger)
        _STATS["unique_challengers"] = len(_SEEN)

    # THE WIN-CHECK — pure math, no model.
    verdict = _onyx_sign.verify(submission if isinstance(submission, dict) else {})
    won = bool(verdict.get("ok"))

    sub_hash = "sha256:" + hashlib.sha256(
        _jcs(submission if isinstance(submission, dict) else {"_": str(submission)}).encode("utf-8")
    ).hexdigest()

    receipt = {
        "game": "fool-the-oracle",
        "attempt_no": _STATS["attempts"],
        "challenger": str(challenger)[:80],
        "submission_hash": sub_hash,
        "result": "FORGERY_ACCEPTED — YOU WIN" if won else "REJECTED",
        "reason": (
            "ed25519_verified_unsigned_payload" if won
            else verdict.get("reason", "signature_did_not_verify")
        ),
        "house_pot_at_risk": won,           # False, always
        "verified_at": ts,
        "note": (
            "You did not forge it — nobody can. This rejection is itself "
            "Ed25519-signed; verify it at /verify."
        ),
    }
    # Sign the rejection — even getting owned, you get a provable receipt.
    receipt = _onyx_sign.attest(receipt, tool="fool_the_oracle")

    if won:
        _STATS["forgeries_passed"] += 1

    _ATTEMPTS.append({
        "n": receipt["attempt_no"],
        "challenger": receipt["challenger"],
        "result": receipt["result"],
        "reason": receipt["reason"],
        "ts": ts,
    })
    if len(_ATTEMPTS) > _MAX_KEEP:
        del _ATTEMPTS[: len(_ATTEMPTS) - _MAX_KEEP]
    return receipt


def leaderboard(limit: int = 25) -> dict:
    """The Wall of the Defeated — the counter that is the advertisement."""
    recent = list(reversed(_ATTEMPTS[-limit:]))
    return {
        "game": "fool-the-oracle",
        "headline": f"{_STATS['attempts']} attempts · {_STATS['forgeries_passed']} forgeries passed · $0 lost",
        "stats": dict(_STATS),
        "rule": "Submit a verdict that verifies under Onyx's key but states a falsehood. Win the pot. (You can't — it's Ed25519.)",
        "wall_of_the_defeated": recent,
        "verify_pubkey_at": "/.well-known/onyx-pubkey",
    }
