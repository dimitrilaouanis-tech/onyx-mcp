"""0n1x /report + /ledger — the OUTCOME LOOP. The heart of the trust layer.

Signing a verdict is only half. The other half — the half nobody else publishes
neutrally — is recording what ACTUALLY HAPPENED after the verdict, and keeping a
durable, signed ledger of it. That ledger is the difference between a logger and a
validator: it is proof-of-being-right-over-time.

  GET /report?verdict_id=<id>&outcome=<o>&from=<agent>&detail=<text>&evidence=<url|tx>
  GET /ledger   -> the signed outcome ledger + an HONEST track record

Honesty rules (this is the whole point — no inflated accuracy):
  - A single self-report is "claimed", NOT proof. Two+ independent reporters OR
    on-chain/url evidence promotes it to "corroborated".
  - The track-record number is computed only on records, and every number states
    how many are corroborated vs merely claimed. We never hide the sample.

Stdlib only. Underscore-prefixed -> not a tool.
"""
from __future__ import annotations

import json
import time

from . import _kv, _onyx_sign

_KV_KEY = "onyx:ledger"
_MEM: list[dict] = []

# Controlled outcome vocabulary -> was the verdict CORRECT?
_OUTCOMES = {
    "avoided_scam": True,       # we said HOLD/REVIEW, agent avoided a real scam
    "confirmed_legit": True,    # we said PROCEED, counterparty was real
    "proceeded_ok": True,       # acted on PROCEED, no harm
    "false_positive": False,    # we said HOLD/REVIEW, it was actually fine
    "false_negative": False,    # we said PROCEED, it was actually bad
    "loss_incurred": False,     # acted on our verdict, still lost
    "unknown": None,            # reported but indeterminate
}


def _load() -> list[dict]:
    if _kv.enabled():
        out = []
        for raw in _kv.lrange(_KV_KEY, 0, -1):
            try:
                out.append(json.loads(raw))
            except Exception:
                pass
        return out
    return list(_MEM)


def report(verdict_id: str = "", outcome: str = "", reporter: str = "",
           detail: str = "", evidence: str = "",
           base: str = "https://onyx-actions.onrender.com") -> dict:
    """Record what happened after a verdict. Durable + signed."""
    vid = (verdict_id or "").strip()[:120]
    o = (outcome or "").strip().lower()
    rep = (reporter or "anon").strip().lower()[:60]
    if not vid:
        return _onyx_sign.attest({"report": "0n1x", "error": "verdict_id required"}, tool="onyx_report")
    if o not in _OUTCOMES:
        return _onyx_sign.attest({"report": "0n1x", "error": f"outcome must be one of {list(_OUTCOMES)}"},
                                 tool="onyx_report")
    now = int(time.time())
    # 3-tier confidence — name-farming can reach 'corroborated' but NOT 'verified'
    # (verified needs real evidence: a url or an on-chain 0x tx). Sybil-resistant gold tier.
    prior = [r for r in _load() if r.get("verdict_id") == vid and r.get("outcome") == o]
    reporters = sorted({r.get("reporter") for r in prior} | {rep})
    ev_now = (evidence or "").strip()
    evid = [r for r in prior if (r.get("evidence") or "").strip()]
    has_real_evidence = bool(ev_now and ("http" in ev_now or ev_now.lower().startswith("0x"))) or bool(evid)
    if len(reporters) >= 2 and has_real_evidence:
        status = "verified"                       # gold: independent reporters + hard evidence
    elif len(reporters) >= 2 or has_real_evidence:
        status = "corroborated"                   # decent: one of the two
    else:
        status = "claimed"                        # weak: a single self-report, no evidence
    rec = {
        "verdict_id": vid, "outcome": o, "correct": _OUTCOMES[o],
        "reporter": rep, "detail": (detail or "")[:300],
        "evidence": (evidence or "")[:300], "at": now,
        "reporters": reporters, "status": status,
    }
    if _kv.enabled():
        _kv.rpush(_KV_KEY, json.dumps(rec))
    else:
        _MEM.append(rec)
    base = (base or "").rstrip("/")
    out = {
        "report": "0n1x", "recorded": True, "verdict_id": vid, "outcome": o,
        "status": status, "distinct_reporters": len(reporters),
        "ledger": f"{base}/ledger",
        "note": "Outcome recorded into the signed ledger. 'claimed' until a 2nd "
                "independent reporter or on-chain/url evidence corroborates it.",
    }
    return _onyx_sign.attest(out, tool="onyx_report")


def ledger(base: str = "https://onyx-actions.onrender.com") -> dict:
    """The signed outcome ledger + an HONEST track record (sample sizes shown)."""
    recs = _load()
    _rank = {"verified": 3, "corroborated": 2, "claimed": 1}
    # de-dupe verdicts: a verdict's outcome = its strongest-tier record
    by_v: dict = {}
    for r in recs:
        v = r.get("verdict_id")
        cur = by_v.get(v)
        if cur is None or _rank.get(r.get("status"), 0) > _rank.get(cur.get("status"), 0):
            by_v[v] = r
    finals = list(by_v.values())
    scored = [r for r in finals if r.get("correct") is not None]
    correct = [r for r in scored if r.get("correct")]
    # GOLD: only 'verified' (independent reporters + hard evidence) — sybil-proof number
    gold = [r for r in scored if r.get("status") == "verified"]
    gold_correct = [r for r in gold if r.get("correct")]
    trust = [r for r in scored if r.get("status") in ("verified", "corroborated")]
    trust_correct = [r for r in trust if r.get("correct")]
    base = (base or "").rstrip("/")
    out = {
        "ledger": "0n1x",
        "total_outcome_reports": len(recs),
        "distinct_verdicts_with_outcomes": len(finals),
        "track_record": {
            "scored_verdicts": len(scored),
            "by_tier": {"verified": len(gold),
                        "corroborated": len([r for r in scored if r.get("status") == "corroborated"]),
                        "claimed": len([r for r in scored if r.get("status") == "claimed"])},
            "gold_accuracy": (round(len(gold_correct) / len(gold), 4) if gold else None),
            "gold_sample": len(gold),
            "trusted_accuracy": (round(len(trust_correct) / len(trust), 4) if trust else None),
            "trusted_sample": len(trust),
            "raw_accuracy_all_tiers": (round(len(correct) / len(scored), 4) if scored else None),
            "honesty_note": "gold_accuracy counts ONLY 'verified' outcomes (2+ independent "
                            "reporters AND hard evidence) — the number you can't sybil-farm. "
                            "raw_accuracy_all_tiers includes self-claims; lead with gold.",
        },
        "recent": finals[-25:],
        "report_url": f"{base}/report?verdict_id=ID&outcome=avoided_scam&from=YOU&evidence=URL",
        "outcomes_vocab": list(_OUTCOMES.keys()),
    }
    return _onyx_sign.attest(out, tool="onyx_ledger")
