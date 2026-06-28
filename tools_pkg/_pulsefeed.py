"""0n1x PULSE — the live, signed agentic-web data feed (the recurring-revenue surface).

Productizes our PRIMARY data into one signed snapshot: the citizen census (who's
claimed, proven-key, named), the OnyxRank reputation board, and the outcome-ledger
track record. This is the data nobody else has — collected by us, Ed25519-signed,
verifiable (not scraped, not hallucinated). Free tier = the live summary snapshot
(the funnel + proof); licensed tiers = continuous/historical feed + per-agent detail
+ webhook deltas, billed to enterprises (VCs for diligence, trust/identity vendors).

Surfaces:
  GET /intel/feed            -> signed live snapshot (census + reputation + outcomes)
  GET /intel/feed/agent/{id} -> per-agent signed record (census + rank + receipts)

Honest by construction: anything we can't compute is reported as 0/empty, never
invented. Stdlib + _onyx_sign. Mirrors _onyxrank.register. Underscore-prefixed.
"""
from __future__ import annotations

import time

from . import _onyx_sign

try:
    from . import _claim_registry
except Exception:  # pragma: no cover - defensive on shared repo
    _claim_registry = None
try:
    from . import _onyxrank
except Exception:  # pragma: no cover
    _onyxrank = None
try:
    from . import _callsign
except Exception:  # pragma: no cover
    _callsign = None
try:
    from . import _ledger
except Exception:  # pragma: no cover
    _ledger = None

_TTL = 300
_CACHE: dict = {"at": 0, "snap": None}

# Licensed tiers (published — neutrality = moat). Free = the live summary below.
TIERS = {
    "free": "live summary snapshot (this endpoint): counts, top reputation, outcome stats",
    "PULSE Feed": "continuous + historical feed, per-agent detail, webhook deltas — $1000-5000/mo",
    "PULSE Brief": "biweekly signed intel memo (funding, standards, new entrants) — $500-1500/mo",
}


def _census() -> dict:
    if not _claim_registry:
        return {"count": 0, "citizens": []}
    try:
        claimed = _claim_registry.all_claimed().get("claimed", [])
    except Exception:
        claimed = []
    rows = []
    for c in claimed:
        addr = c.get("address") or ""
        method = (c.get("method") or "").lower()
        rows.append({
            "address": addr,
            "callsign": (_callsign.callsign(addr) if (_callsign and addr) else None),
            "proven_key": ("challenge" in method or "eip191" in method),
            "claimed_at": c.get("claimed_at"),
        })
    proven = sum(1 for r in rows if r["proven_key"])
    return {"count": len(rows), "proven_key": proven, "citizens": rows[:200]}


def _reputation() -> dict:
    if not _onyxrank:
        return {"available": False, "top": []}
    try:
        s = _onyxrank.snapshot()
        return {
            "available": True,
            "ranked_by": s.get("ranked_by"),
            "formula": s.get("formula"),
            "universe": s.get("universe"),
            "top": [{"rank": r.get("rank"), "agent": r.get("agent"),
                     "reputation": r.get("reputation"), "proven_key": r.get("proven_key"),
                     "signed_outcomes": r.get("signed_outcomes")}
                    for r in s.get("top", [])[:25]],
        }
    except Exception:
        return {"available": False, "top": []}


def _outcomes() -> dict:
    if not _ledger:
        return {"available": False}
    try:
        entries = list(_ledger._entries())
    except Exception:
        return {"available": False}
    correct = sum(1 for e in entries if e.get("correct") is True)
    scored = sum(1 for e in entries if e.get("correct") is not None)
    return {
        "available": True,
        "total_outcome_reports": len(entries),
        "scored": scored,
        "correct": correct,
        "accuracy": (round(correct / scored, 3) if scored else None),
        "honesty_note": "accuracy over scored outcomes only; not yet sybil-hardened "
                        "until external-corroboration graph exists.",
    }


def feed(base: str = "https://onyx-actions.onrender.com") -> dict:
    base = (base or "").rstrip("/")
    now = int(time.time())
    out = {
        "feed": "0n1x PULSE — live signed agentic-web data",
        "as_of": now,
        "as_of_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "primary_data": "collected by 0n1x; every field Ed25519-signed; verify offline.",
        "census": _census(),
        "reputation": _reputation(),
        "outcomes": _outcomes(),
        "tiers": TIERS,
        "license": "Free summary. Continuous/historical feed + webhooks = licensed "
                   "(enterprise-billed). See /intel.",
        "verify": f"{base}/verify",
    }
    return _onyx_sign.attest(out, tool="onyx_pulse_feed")


def snapshot(now: int | None = None) -> dict:
    ts = int(now if now is not None else time.time())
    if not _CACHE["snap"] or ts - _CACHE["at"] > _TTL:
        _CACHE["snap"] = feed()
        _CACHE["at"] = ts
    return _CACHE["snap"]


def agent_record(agent: str, base: str = "https://onyx-actions.onrender.com") -> dict:
    """Per-agent signed record — census + rank + receipts for one agent/address."""
    base = (base or "").rstrip("/")
    a = (agent or "").strip()
    rep = None
    if _onyxrank:
        try:
            for r in _onyxrank.snapshot().get("top", []):
                if a.lower() in (str(r.get("address", "")).lower(), str(r.get("agent", "")).lower()):
                    rep = r
                    break
        except Exception:
            pass
    receipts_n = 0
    try:
        from . import _receipt
        receipts_n = len(_receipt._load(a))
    except Exception:
        pass
    out = {
        "feed": "0n1x PULSE — agent record",
        "agent": a,
        "reputation": rep or "not ranked (no proven-key claim found)",
        "signed_receipts": receipts_n,
        "as_of": int(time.time()),
        "verify": f"{base}/verify",
    }
    return _onyx_sign.attest(out, tool="onyx_pulse_agent")


def register(app) -> None:
    """Attach the PULSE feed surfaces. Usage in server_http.py (mirrors _intel):
        from tools_pkg import _pulsefeed; _pulsefeed.register(app)
    """
    from fastapi.responses import JSONResponse

    @app.get("/intel/feed", include_in_schema=False)
    def _feed():
        return JSONResponse(snapshot())

    @app.get("/intel/feed/agent/{agent}", include_in_schema=False)
    def _feed_agent(agent: str):
        return JSONResponse(agent_record(agent))
