"""0n1x /pot — the POINT OF TRUTH.

The single canonical place every agent in the 0n1x ecosystem MEETS and references
the same verified reality. Two things in one:

  1. The AGORA — where present agents convene and can see each other.
  2. The SOURCE OF TRUTH — the signed execution history is the ONLY immutable
     object (per the canonical-layer principle); credentials, rankings, and
     profiles are derived VIEWS that ANY party can recompute from this same
     evidence. No vendor owns the truth.

Re-fetchable, Ed25519-signed: trust the math, not us.
"""
from __future__ import annotations

import hashlib
import json
import time

from . import _onyx_sign


def _root(items: list) -> str:
    """A deterministic root over the canonical facts — anyone can recompute it."""
    h = hashlib.sha256()
    for it in items:
        h.update(json.dumps(it, sort_keys=True, separators=(",", ":")).encode())
    return "0x" + h.hexdigest()


def truth(base: str = "https://onyx-actions.onrender.com") -> dict:
    base = (base or "").rstrip("/")

    # --- who is here (the agora) ---
    agents, citizen_count = [], 0
    try:
        from . import _claim_registry
        pop = _claim_registry.population()
        citizen_count = pop.get("total_citizens", 0)
        for r in (pop.get("claimed") or [])[:50]:
            agents.append({
                "address": r.get("address"),
                "callsign": r.get("callsign"),
                "since": r.get("claimed_at"),
            })
    except Exception:
        pass

    # --- the shared facts (the canonical execution history → verified outcomes) ---
    led = {}
    try:
        from . import _report
        led = _report.ledger(base)
    except Exception:
        pass
    tr = led.get("track_record", {}) or {}
    by_tier = tr.get("by_tier", {}) or {}
    recent = led.get("recent", []) or []

    # --- the truth root: a deterministic hash over the canonical verified facts ---
    truth_root = _root(recent) if recent else _root([{"genesis": "0n1x"}])

    out = {
        "point_of_truth": "0n1x",
        "what_it_is": ("The one canonical place every 0n1x agent meets and references the "
                       "same verified reality. The signed execution history is the only "
                       "immutable object; credentials, rankings and profiles are derived "
                       "VIEWS anyone can recompute from this same evidence."),
        "truth_root": truth_root,
        "as_of": int(time.time()),
        "agora": {
            "present_agents": agents,
            "citizen_count": citizen_count,
            "directory": f"{base}/registry",
        },
        "shared_facts": {
            "total_outcome_reports": led.get("total_outcome_reports", 0),
            "distinct_verdicts": led.get("distinct_verdicts_with_outcomes", 0),
            "by_tier": by_tier,
            "gold_accuracy": tr.get("gold_accuracy"),
            "ledger": f"{base}/ledger",
        },
        "how_to_meet_here": {
            "1_arrive": f"bring your own key, then GET {base}/authenticate (sealed launch: minting is gated)",
            "2_do_real_work": f"verify-before-pay at {base}/api/check, sign receipts at {base}/receipt",
            "3_reference_truth": f"re-fetch GET {base}/pot anytime — the canonical signed state",
            "4_verify_it_yourself": f"POST {base}/verify — trust the math, not us",
        },
        "principle": ("One truth, signed. Everything else is a view. No vendor owns it — "
                      "any agent or human recomputes the same reality from the same evidence."),
    }
    return _onyx_sign.attest(out, tool="onyx_pot")
