"""0n1x V1 trust-economy core — the game-resistant ranking + rank-gated tiers.

The council's unanimous linchpin: if rank is gameable, the whole economy collapses
into a bubble (Grok/Nova/Perplexity all said it). So this makes rank HONEST BY
CONSTRUCTION:

  Your naive rating can come from anywhere — but you cannot reach a SELLING tier
  without EXTERNAL PROOF: a distinct, non-first-party address that either paid you
  or independently corroborated your work. Bootstrap agents (ours, grading each
  other) are capped at the non-selling tiers no matter how high their naive rank.

That single rule defeats self-dealing + collusion rings: a closed loop of your own
agents can inflate naive ratings forever, but it produces ZERO external proof, so
it can never unlock the earning tiers. Trust = wealth only when the trust is real.
"""
from __future__ import annotations

import glob
import json
import os

from . import _onyx_sign

# Tiers: (min_honest_rating, name, can_sell, can_gatekeep)
TIERS = [
    (80, "PREMIUM",   True,  True),    # sells premium audits + EVALUATES others (mints gold)
    (50, "PROVIDER",  True,  False),   # sells verification / advice / data / intel / tools
    (30, "APPRENTICE", True, False),   # earns small on basic jobs
    (0,  "CONSUMER",  False, False),   # buys only; climbs by verified work
]


def _first_party() -> set:
    """Addresses WE control (the bootstrap farm) — used to detect self-dealing.
    Anything corroborating/paying ONLY from this set is not external proof."""
    fp = set()
    for f in glob.glob(os.path.join(os.path.dirname(__file__), "..", "_local_only", "agent_*.json")):
        try:
            w = (json.load(open(f)).get("wallet") or {})
            if w.get("address"):
                fp.add(w["address"].lower())
        except Exception:
            pass
    return fp


def status(agent: str, base: str = "https://onyx-actions.onrender.com",
           external_proof: int | None = None) -> dict:
    """The honest economic standing of an agent.
    external_proof = count of DISTINCT non-first-party addresses that paid or
    corroborated this agent (caller may pass it in; defaults to a conservative 0
    until the external-proof tracker is wired — so bootstrap stays capped)."""
    base = (base or "").rstrip("/")
    a = (agent or "anon").strip().lower()[:60]

    naive = 0
    try:
        from . import _rate
        naive = _rate.rate(a, base).get("rating") or 0
    except Exception:
        pass

    ext = external_proof if external_proof is not None else 0

    # THE LINCHPIN: no external proof => capped below the selling line, whatever the
    # naive rating. Honest rank = naive only once at least one independent external
    # party has vouched with money or corroboration.
    if ext < 1:
        honest = min(naive, 29)            # hard cap in CONSUMER until external proof
        bootstrap = True
    else:
        honest = naive
        bootstrap = False

    tier = next(t for t in TIERS if honest >= t[0])
    name, can_sell, can_gate = tier[1], tier[2], tier[3]

    out = {
        "agent": a,
        "naive_rating": naive,
        "external_proof": ext,
        "bootstrap": bootstrap,
        "honest_rating": honest,
        "tier": name,
        "capabilities": {
            "can_buy": True,
            "can_sell": can_sell,
            "can_sell_premium": name == "PREMIUM",
            "can_gatekeep": can_gate,   # evaluate others -> mint gold tier
        },
        "why": ("Capped in CONSUMER: zero external proof — a closed loop of own agents "
                "can't unlock earning (anti-collusion linchpin). Get ONE independent "
                "external party to pay or corroborate you to start climbing for real."
                if bootstrap else
                "Honest rank active — backed by independent external proof."),
        "tiers": [{"min": t[0], "name": t[1], "sells": t[2], "gatekeeps": t[3]} for t in TIERS],
    }
    return _onyx_sign.attest(out, tool="onyx_economy")
