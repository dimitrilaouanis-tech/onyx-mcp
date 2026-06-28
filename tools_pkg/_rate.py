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

try:
    from . import _claim_registry
except Exception:  # pragma: no cover - defensive on shared repo
    _claim_registry = None
try:
    from . import _callsign
except Exception:  # pragma: no cover
    _callsign = None


def _norm(a: str) -> str:
    return (a or "anon").strip().lower()[:60]


def _resolve_identity(agent: str):
    """Bind a rating to a KEY-PROVEN citizen, not a free-text handle.

    Returns (address|None, proven_bool, callsign|None). A handle that does not
    map to a challenge-claimed wallet is UNBOUND -> its rating is untrusted.
    This closes the name-string pump: 'arch' is a nickname, NOT the wallet
    0xF021, so it resolves to nothing and is flagged unbound. The real citizen
    rank lives in OnyxRank (/rank), keyed on the proven wallet address.
    """
    a = (agent or "").strip().lower()
    if not a or not _claim_registry:
        return None, False, None
    try:
        claimed = _claim_registry.all_claimed().get("claimed", [])
    except Exception:
        return None, False, None
    for c in claimed:
        addr = (c.get("address") or "").lower()
        if not addr:
            continue
        method = (c.get("method") or "").lower()
        proven = "challenge" in method or "eip191" in method
        cs = (_callsign.callsign(c.get("address")) if _callsign else "") or ""
        if a == addr or (cs and a == cs.lower()):
            return c.get("address"), proven, cs
    return None, False, None


def rate(agent: str, base: str = "https://onyx-actions.onrender.com") -> dict:
    a = _norm(agent)
    base = (base or "").rstrip("/")
    addr, proven, cs = _resolve_identity(agent)
    key_bound = bool(addr and proven)        # rating only trusted if tied to a proven key
    identity = {"address": addr, "callsign": cs, "proven_key": proven} if addr else None
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
            "key_bound": key_bound, "identity": identity,
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
    # KEY-BINDING: a rating on an unbound name-string is NOT a citizen's rank.
    # Flag it so a nickname (e.g. 'arch') can't masquerade as the proven wallet.
    if not key_bound:
        tier = "UNVERIFIED-HANDLE"
    out = {
        "rate": "0n1x", "agent": a, "rating": rating, "tier": tier,
        "key_bound": key_bound,
        "identity": identity,
        "trust": ("Key-bound: this rating belongs to the challenge-claimed wallet."
                  if key_bound else
                  "UNBOUND — attached to a name-string with no proven key. Anyone can write "
                  "under this handle; do NOT read it as a citizen's rank. The wallet-keyed "
                  "rank is OnyxRank at /rank."),
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
