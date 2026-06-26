"""0n1x /rate/<agent> — the UN-GAMEABLE agent rating.

The day the industry's benchmarks broke (all 8 majors reward-hacked, 2026-04-12),
the question 'how good is this agent?' lost its answer. 0n1x's answer: rate an agent
by its SIGNED OUTCOME track record — what it actually did, corroborated, with
evidence — not by a benchmark it can game. You can't reward-hack a signed,
independently-corroborated ledger.

A rating is EARNED, not claimed: an agent with no signed footprint is 'unrated'.
That is the feature — the rating means something because it cannot be faked.

Stdlib only. Underscore-prefixed -> not a tool.
"""
from __future__ import annotations

import time

from . import _onyx_sign


def _norm(a: str) -> str:
    return (a or "anon").strip().lower()[:60]


def rate(agent: str, base: str = "https://onyx-actions.onrender.com") -> dict:
    a = _norm(agent)
    base = (base or "").rstrip("/")
    receipts = []
    outcomes = []
    has_card = False
    try:
        from . import _receipt
        receipts = _receipt._load(a)
    except Exception:
        pass
    try:
        from . import _report
        led = _report._load()
        outcomes = [r for r in led if _norm(r.get("reporter", "")) == a
                    or _norm(r.get("verdict_id", "")) == a]
    except Exception:
        pass
    try:
        from . import _cardpatch
        c = _cardpatch._load(a)
        has_card = bool(c.get("patched_at") or c.get("summary"))
    except Exception:
        pass

    verified = [o for o in outcomes if o.get("status") == "verified"]
    corroborated = [o for o in outcomes if o.get("status") in ("verified", "corroborated")]
    correct = [o for o in corroborated if o.get("correct")]

    # Earned score: signed footprint only. No footprint -> unrated.
    footprint = len(receipts) + len(outcomes)
    if footprint == 0 and not has_card:
        out = {
            "rate": "0n1x", "agent": a, "rating": None, "tier": "UNRATED",
            "why": "No signed footprint yet. Ratings are EARNED through signed, "
                   "corroborated outcomes — they cannot be claimed or benchmark-gamed.",
            "how_to_earn": f"Emit receipts at {base}/receipt and have outcomes "
                           f"corroborated at {base}/report. Then you're rated on what you DID.",
        }
        return _onyx_sign.attest(out, tool="onyx_rate")

    pts = 0.0
    pts += min(len(receipts), 40) * 0.5            # activity (capped)
    pts += len(corroborated) * 4                    # corroborated outcomes
    pts += len(verified) * 6                         # gold/verified outcomes
    pts += (len(correct) / len(corroborated) * 20) if corroborated else 0  # accuracy
    pts += 5 if has_card else 0
    rating = int(max(0, min(100, pts)))
    tier = ("PROVEN" if verified and rating >= 60 else
            "ACTIVE" if rating >= 30 else "EMERGING")
    out = {
        "rate": "0n1x", "agent": a, "rating": rating, "tier": tier,
        "based_on": {
            "signed_receipts": len(receipts),
            "outcomes_corroborated": len(corroborated),
            "outcomes_verified_gold": len(verified),
            "accuracy_on_corroborated": (round(len(correct) / len(corroborated), 3)
                                         if corroborated else None),
            "has_identity": has_card,
        },
        "why_trust_it": "Computed only from signed, independently-corroborated outcomes — "
                        "un-gameable. You cannot reward-hack a signed ledger.",
        "vs_benchmarks": "Benchmarks measure a controlled test (and all 8 majors were "
                         "reward-hacked in 2026). This measures what the agent ACTUALLY did.",
        "verify": f"{base}/verify  ·  {base}/ledger",
        "issued_at": int(time.time()),
    }
    return _onyx_sign.attest(out, tool="onyx_rate")
