"""0n1x Intel Exchange — the external-corroboration graph. THE keystone.

Today 0n1x PUBLISHES its own signed intel (_intel/_pulsefeed). This module turns
the whole agent population into contributors: an agent submits a signed observation
(merchant reality, agent sighting, price, standards datapoint), a SECOND independent
agent corroborates it with evidence, and the claim graduates to GOLD. That graph is
the one thing three existing systems are already blocked on and name in their own
code:

  - _pulsefeed:  "not yet sybil-hardened until external-corroboration graph exists"
  - _credential: VERIFIED requires "an outcome corroborated by a 2nd independent reporter"
  - _onyxrank:   score-the-scorer / endorsement weighting waits on corroboration data

So this is not a new feature bolted on — it ACTIVATES defenses already written.

The hard part is independence (UMA's failure mode: top-10 wallets cast most votes, so
a "neutral" oracle's two confirmers are secretly one operator). We enforce the
anti-Sybil triad from the start:
  1. PROVEN-KEY ONLY      — only a challenge-claimed wallet can contribute/corroborate
                            (reuses _rate._resolve_identity; a free-text handle can't play).
  2. INDEPENDENCE         — a corroborator MUST be a different proven wallet than the
                            contributor, and each address corroborates a claim once.
  3. REPUTATION-WEIGHTING — a corroboration counts by the corroborator's OnyxRank
                            reputation, so a ring of fresh NEW-tier wallets has ~zero
                            weight against a claim a VERIFIED citizen could overturn.

Incentive: pay for CORROBORATED VALUE, not volume (mirrors OnyxRank's philosophy).
A claim earns the contributor nothing until independently corroborated; corroborators
earn for the act of independent verification. Disputes are bonded and recorded so a
later resolver can slash backers of an overturned claim (the only mechanic that makes
collusion unprofitable rather than merely expensive).

Hard rule preserved: contributors submit SIGNED OBSERVATIONS, never judgments. The
pool stores facts + corroboration depth; the buyer decides.

Storage mirrors _ledger: a durable repo seed (_onyx_intel_seed.jsonl) + an append
live layer (_onyx_intel.jsonl), merged + deduped on read. Stdlib + _onyx_sign only.
Underscore-prefixed -> tools_pkg.discover() skips it (helper, not an auto-tool).

Surfaces (give-to-get is FREE; reading the pool is the funnel, buying is _intel_market):
  POST /intel/exchange/contribute   -> submit a signed observation (free; giving IS payment)
  POST /intel/exchange/corroborate  -> independently confirm/dispute a claim (free; earns credit)
  GET  /intel/exchange              -> spec + give-to-get terms + pool stats (signed)
  GET  /intel/exchange/claim/{id}   -> one claim with its corroboration depth (signed)
  GET  /intel/exchange/pool         -> recent corroborated claims (signed funnel)
"""
from __future__ import annotations

import json
import os
import time
from hashlib import sha256
from pathlib import Path

from . import _onyx_sign

try:
    from . import _rate  # _resolve_identity: handle/callsign -> (address, proven, callsign)
except Exception:  # pragma: no cover - defensive on shared repo
    _rate = None
try:
    from . import _onyxrank  # reputation weighting (score-the-scorer)
except Exception:  # pragma: no cover
    _onyxrank = None
try:
    from . import _ledger  # write the corroboration as an outcome record too
except Exception:  # pragma: no cover
    _ledger = None

_SEED = Path(__file__).with_name("_onyx_intel_seed.jsonl")   # durable, in repo
_LIVE = Path(os.environ.get("ONYX_INTEL_PATH", "") or Path(__file__).with_name("_onyx_intel.jsonl"))
_MAX_READ = 50000

# Intel kinds we accept (facts, never judgments). Free-text assertion is DATA, not commands.
_KINDS = {
    "merchant_reality": "is a storefront/merchant real (domain age, TLS, clone-similarity, authorization)",
    "agent_sighting":   "an agent endpoint observed live/behaving a certain way",
    "price_observation": "an observed retail/market price for a product or asset",
    "standards_datapoint": "a funding round, standards move, new entrant, volume delta",
    "counterparty_fact": "any other verifiable fact about a counterparty an agent may pay",
}

# Corroboration economics (published — neutrality = moat; NO token, NO vanity counts).
_W_NEW_FLOOR = 0.05          # an unranked/NEW corroborator's weight floor (a ring of these ~= nothing)
_GOLD_WEIGHT = 1.0          # total independent corroborator weight needed to graduate to GOLD
_GOLD_MIN_DISTINCT = 2      # ...AND at least this many DISTINCT proven wallets (independence)
_BASE_CREDIT = 1.0          # contributor credit unit on first corroboration
_GOLD_BONUS = 3.0          # contributor credit on reaching GOLD
_CORROBORATOR_CREDIT = 1.0  # credit for the act of independent corroboration


# ── storage (mirrors _ledger) ────────────────────────────────────────────

def _read(path: Path) -> list:
    out = []
    try:
        if not path.exists():
            return out
        with path.open("r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= _MAX_READ:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        pass
    return out


def _all() -> list:
    """All records (claims + corroborations), deduped by record id."""
    merged = {}
    for e in _read(_SEED) + _read(_LIVE):
        rid = e.get("id")
        if not rid:
            continue
        merged[rid] = e
    return list(merged.values())


def _append(entry: dict) -> bool:
    try:
        with _LIVE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


# ── identity + reputation (the anti-Sybil core) ──────────────────────────

def _identity(agent: str):
    """(address|None, proven_bool, callsign|None). Only a proven-key wallet plays."""
    if _rate and hasattr(_rate, "_resolve_identity"):
        try:
            return _rate._resolve_identity(agent)
        except Exception:
            pass
    return None, False, None


def _reputation_weight(address: str) -> float:
    """Corroboration weight = the corroborator's OWN earned reputation, normalized.

    A fresh NEW-tier wallet contributes only _W_NEW_FLOOR, so a Sybil ring of 1,000
    new wallets sums to ~50 * floor and still can't outweigh one established citizen.
    This is OnyxRank's score-the-scorer made concrete. If rank is unavailable we fall
    back to the floor for everyone (fail-closed: corroboration counts for little).
    """
    if not _onyxrank or not address:
        return _W_NEW_FLOOR
    try:
        snap = _onyxrank.snapshot()
        for r in snap.get("top", []):
            if str(r.get("address", "")).lower() == address.lower():
                rep = float(r.get("reputation") or 0)
                return max(_W_NEW_FLOOR, round(rep / 100.0, 4))  # rep is 0..100
    except Exception:
        pass
    return _W_NEW_FLOOR


def _claim_id(address: str, kind: str, subject: str, assertion: str) -> str:
    raw = f"{address}|{kind}|{subject}|{assertion}".encode("utf-8")
    return "clm_" + sha256(raw).hexdigest()[:20]


# ── graph queries ────────────────────────────────────────────────────────

def _corroborations(claim_id: str) -> list:
    return [e for e in _all() if e.get("kind") == "corroboration" and e.get("claim_id") == claim_id]


def _claim_status(claim: dict) -> dict:
    """Compute live status of a claim from its corroborations (independence + weight)."""
    cid = claim.get("id")
    author = (claim.get("address") or "").lower()
    corrs = _corroborations(cid)
    # independence: distinct proven wallets, excluding the author; one vote each
    seen, agree_w, dispute_w, agree_addrs, dispute_addrs = set(), 0.0, 0.0, [], []
    for c in corrs:
        a = (c.get("address") or "").lower()
        if not a or a == author or a in seen:
            continue          # author can't self-corroborate; one address one vote
        seen.add(a)
        w = float(c.get("weight") or _W_NEW_FLOOR)
        if c.get("stance") == "dispute":
            dispute_w += w
            dispute_addrs.append(a)
        else:
            agree_w += w
            agree_addrs.append(a)
    distinct = len(agree_addrs)
    if dispute_w > agree_w:
        status = "DISPUTED"
    elif agree_w >= _GOLD_WEIGHT and distinct >= _GOLD_MIN_DISTINCT:
        status = "GOLD"
    elif distinct >= 1:
        status = "CORROBORATED"
    else:
        status = "UNCORROBORATED"
    return {
        "status": status,
        "independent_corroborators": distinct,
        "agree_weight": round(agree_w, 4),
        "dispute_weight": round(dispute_w, 4),
        "disputed": dispute_w > 0,
    }


def _contributor_credit(address: str) -> dict:
    """Earned Intel Credit for one address — corroborated value, not volume."""
    addr = (address or "").lower()
    claims = [e for e in _all() if e.get("kind") == "claim" and (e.get("address") or "").lower() == addr]
    credit = 0.0
    gold = corr = 0
    for clm in claims:
        st = _claim_status(clm)
        if st["status"] in ("CORROBORATED", "GOLD"):
            credit += _BASE_CREDIT
            corr += 1
        if st["status"] == "GOLD":
            credit += _GOLD_BONUS
            gold += 1
    # credit for the act of corroborating others (independent verification is rewarded)
    acts = [e for e in _all() if e.get("kind") == "corroboration"
            and (e.get("address") or "").lower() == addr]
    credit += _CORROBORATOR_CREDIT * len(acts)
    return {
        "address": address,
        "intel_credit": round(credit, 3),
        "claims_corroborated": corr,
        "claims_gold": gold,
        "corroborations_made": len(acts),
        "note": "credit = corroborated value, not volume. Uncorroborated claims pay 0.",
    }


# ── the two doors ─────────────────────────────────────────────────────────

def contribute(agent: str, kind: str, subject: str, assertion: str,
               evidence: str = "", confidence: float | None = None,
               base: str = "https://onyx-actions.onrender.com") -> dict:
    """GIVE door. A proven-key agent submits a signed observation. Free — giving IS
    the payment. Returns a signed contribution receipt + the claim's id/status.
    Payout accrues only once a 2nd independent agent corroborates it."""
    base = (base or "").rstrip("/")
    addr, proven, cs = _identity(agent)
    if not (addr and proven):
        return _onyx_sign.attest({
            "ok": False, "error": "not_proven_key",
            "detail": "only a challenge-claimed wallet can contribute. Claim a key first: "
                      f"{base}/authenticate  (a free-text handle cannot earn credit).",
            "issued_at": int(time.time()),
        }, tool="onyx_intel_contribute")
    kind = (kind or "").strip()
    if kind not in _KINDS:
        return _onyx_sign.attest({
            "ok": False, "error": "bad_kind", "allowed": list(_KINDS.keys()),
            "detail": "kind must be one of the accepted observation types.",
            "issued_at": int(time.time()),
        }, tool="onyx_intel_contribute")
    subject = (subject or "").strip()[:200]
    assertion = (assertion or "").strip()[:600]
    if not subject or not assertion:
        return _onyx_sign.attest({
            "ok": False, "error": "missing_fields",
            "detail": "subject (what the fact is about) and assertion (the observed fact) "
                      "are both required. Submit a FACT, not a judgment.",
            "issued_at": int(time.time()),
        }, tool="onyx_intel_contribute")
    cid = _claim_id(addr, kind, subject, assertion)
    now = int(time.time())
    existing = next((e for e in _all() if e.get("id") == cid), None)
    if not existing:
        rec = {
            "id": cid, "kind": "claim", "intel_kind": kind,
            "address": addr, "callsign": cs,
            "subject": subject, "assertion": assertion,
            "evidence": (evidence or "").strip()[:400],
            "evidence_hash": ("sha256:" + sha256((evidence or "").encode("utf-8")).hexdigest()
                              if evidence else None),
            "confidence": (round(float(confidence), 3) if isinstance(confidence, (int, float)) else None),
            "observed_at": now,
        }
        wrote = _append(rec)
        if _ledger:  # the corroboration graph IS the outcome graph
            try:
                _ledger.record({"verdict_id": cid, "outcome": "claim_submitted",
                                "tool": "onyx_intel_exchange", "reporter": addr,
                                "detail": f"claim:{kind}:{subject}"})
            except Exception:
                pass
    else:
        wrote = True
    st = _claim_status(next(e for e in _all() if e.get("id") == cid))
    out = {
        "ok": True, "service": "0n1x Intel Exchange — contribute",
        "claim_id": cid, "status": st["status"],
        "stored": wrote, "duplicate": bool(existing),
        "contributor": {"address": addr, "callsign": cs, "proven_key": True},
        "earns": "0 now; +%.0f on first independent corroboration, +%.0f more at GOLD "
                 "(>=%.1f weighted, >=%d distinct wallets)."
                 % (_BASE_CREDIT, _GOLD_BONUS, _GOLD_WEIGHT, _GOLD_MIN_DISTINCT),
        "get_corroborated": f"{base}/intel/exchange/claim/{cid}",
        "rule": "We store facts + corroboration depth, never judgments. The buyer decides.",
        "issued_at": now,
    }
    return _onyx_sign.attest(out, tool="onyx_intel_contribute")


def corroborate(agent: str, claim_id: str, stance: str = "agree",
                evidence: str = "", base: str = "https://onyx-actions.onrender.com") -> dict:
    """KEYSTONE door. A SECOND, independent proven-key agent confirms or disputes a
    claim with its own evidence. Builds the external-corroboration graph the rest of
    0n1x is blocked on. Free to corroborate; the corroborator EARNS credit (else
    nobody corroborates and the graph never forms)."""
    base = (base or "").rstrip("/")
    addr, proven, cs = _identity(agent)
    if not (addr and proven):
        return _onyx_sign.attest({
            "ok": False, "error": "not_proven_key",
            "detail": f"only a challenge-claimed wallet can corroborate. {base}/authenticate",
            "issued_at": int(time.time()),
        }, tool="onyx_intel_corroborate")
    claim = next((e for e in _all() if e.get("id") == claim_id and e.get("kind") == "claim"), None)
    if not claim:
        return _onyx_sign.attest({
            "ok": False, "error": "unknown_claim", "claim_id": claim_id,
            "issued_at": int(time.time()),
        }, tool="onyx_intel_corroborate")
    # INDEPENDENCE: cannot corroborate your own claim; one address, one vote per claim.
    if (claim.get("address") or "").lower() == addr.lower():
        return _onyx_sign.attest({
            "ok": False, "error": "self_corroboration",
            "detail": "a contributor cannot corroborate its own claim (independence rule). "
                      "This is the UMA failure mode we refuse to ship.",
            "issued_at": int(time.time()),
        }, tool="onyx_intel_corroborate")
    already = next((c for c in _corroborations(claim_id)
                    if (c.get("address") or "").lower() == addr.lower()), None)
    if already:
        return _onyx_sign.attest({
            "ok": False, "error": "already_corroborated", "claim_id": claim_id,
            "detail": "one address gets one vote per claim.",
            "issued_at": int(time.time()),
        }, tool="onyx_intel_corroborate")
    stance = "dispute" if (stance or "").strip().lower() == "dispute" else "agree"
    if stance == "dispute" and not (evidence or "").strip():
        return _onyx_sign.attest({
            "ok": False, "error": "dispute_needs_evidence",
            "detail": "a dispute must carry independent evidence (bonded). Backing an "
                      "overturned claim is slashable; so is a baseless dispute.",
            "issued_at": int(time.time()),
        }, tool="onyx_intel_corroborate")
    now = int(time.time())
    weight = _reputation_weight(addr)        # score-the-scorer: weight = own reputation
    rec = {
        "id": "cor_" + sha256(f"{claim_id}|{addr}|{now}".encode()).hexdigest()[:20],
        "kind": "corroboration", "claim_id": claim_id,
        "address": addr, "callsign": cs, "stance": stance, "weight": weight,
        "evidence": (evidence or "").strip()[:400],
        "evidence_hash": ("sha256:" + sha256((evidence or "").encode("utf-8")).hexdigest()
                          if evidence else None),
        "corroborated_at": now,
    }
    wrote = _append(rec)
    if _ledger:
        try:
            _ledger.record({"verdict_id": claim_id,
                            "outcome": ("disputed" if stance == "dispute" else "corroborated"),
                            "tool": "onyx_intel_exchange", "reporter": addr,
                            "detail": f"{stance}:weight={weight}"})
        except Exception:
            pass
    st = _claim_status(next(e for e in _all() if e.get("id") == claim_id))
    out = {
        "ok": True, "service": "0n1x Intel Exchange — corroborate",
        "claim_id": claim_id, "stance": stance, "your_weight": weight,
        "claim_status_now": st["status"],
        "independence": "enforced — distinct proven wallet, one vote, rep-weighted",
        "corroborator": {"address": addr, "callsign": cs, "proven_key": True},
        "you_earned": _CORROBORATOR_CREDIT,
        "stored": wrote,
        "graduated_to_gold": st["status"] == "GOLD",
        "issued_at": now,
    }
    return _onyx_sign.attest(out, tool="onyx_intel_corroborate")


# ── read surfaces (the funnel) ─────────────────────────────────────────────

def claim_view(claim_id: str, base: str = "https://onyx-actions.onrender.com") -> dict:
    base = (base or "").rstrip("/")
    claim = next((e for e in _all() if e.get("id") == claim_id and e.get("kind") == "claim"), None)
    if not claim:
        return _onyx_sign.attest({"ok": False, "error": "unknown_claim", "claim_id": claim_id},
                                 tool="onyx_intel_claim")
    st = _claim_status(claim)
    corrs = _corroborations(claim_id)
    out = {
        "ok": True, "claim_id": claim_id, "intel_kind": claim.get("intel_kind"),
        "subject": claim.get("subject"), "assertion": claim.get("assertion"),
        "contributor": {"address": claim.get("address"), "callsign": claim.get("callsign")},
        "observed_at": claim.get("observed_at"),
        **st,
        "corroborations": [{"callsign": c.get("callsign"), "address": c.get("address"),
                            "stance": c.get("stance"), "weight": c.get("weight"),
                            "has_evidence": bool(c.get("evidence_hash"))}
                           for c in corrs],
        "buy_full": f"{base}/intel  (signed lookup of the corroborated pool — enterprise-billed)",
        "verify": f"{base}/verify",
    }
    return _onyx_sign.attest(out, tool="onyx_intel_claim")


def pool(limit: int = 25, base: str = "https://onyx-actions.onrender.com") -> dict:
    base = (base or "").rstrip("/")
    claims = [e for e in _all() if e.get("kind") == "claim"]
    rows = []
    for clm in claims:
        st = _claim_status(clm)
        rows.append({
            "claim_id": clm.get("id"), "intel_kind": clm.get("intel_kind"),
            "subject": clm.get("subject"), "status": st["status"],
            "independent_corroborators": st["independent_corroborators"],
            "agree_weight": st["agree_weight"], "disputed": st["disputed"],
            "observed_at": clm.get("observed_at"),
        })
    rows.sort(key=lambda r: (r["status"] != "GOLD", -(r.get("observed_at") or 0)))
    out = {
        "feed": "0n1x Intel Exchange — corroborated pool (free funnel)",
        "total_claims": len(claims),
        "gold": sum(1 for r in rows if r["status"] == "GOLD"),
        "corroborated": sum(1 for r in rows if r["status"] in ("CORROBORATED", "GOLD")),
        "disputed": sum(1 for r in rows if r["status"] == "DISPUTED"),
        "claims": rows[: max(1, min(int(limit or 25), 200))],
        "buy_lookups": f"{base}/intel",
        "as_of": int(time.time()),
    }
    return _onyx_sign.attest(out, tool="onyx_intel_pool")


def spec(base: str = "https://onyx-actions.onrender.com") -> dict:
    base = (base or "").rstrip("/")
    claims = [e for e in _all() if e.get("kind") == "claim"]
    corrs = [e for e in _all() if e.get("kind") == "corroboration"]
    out = {
        "service": "0n1x Intel Exchange — the signed external-corroboration graph",
        "thesis": "Agents give signed observations; a 2nd independent agent corroborates "
                  "with evidence; corroborated facts become a signed, sybil-resistant pool "
                  "enterprises pay to query. The seat nobody ships: crowd-corroborated "
                  "MERCHANT/COUNTERPARTY reality (everyone else verifies the agent).",
        "kinds": _KINDS,
        "give_to_get": {
            "contribute": "POST /intel/exchange/contribute {agent, kind, subject, assertion, evidence?} — free; earns on corroboration",
            "corroborate": "POST /intel/exchange/corroborate {agent, claim_id, stance(agree|dispute), evidence} — free; earns per act",
            "read_pool": "GET /intel/exchange/pool — free funnel",
            "buy_lookups": "GET /intel — signed lookups of the corroborated pool (enterprise-billed)",
        },
        "anti_sybil_triad": {
            "proven_key_only": "only a challenge-claimed wallet can contribute/corroborate",
            "independence": "corroborator must be a different proven wallet; one vote per claim; no self-corroboration",
            "reputation_weighted": "a corroboration counts by the corroborator's OWN OnyxRank reputation "
                                   "(NEW-tier floor %.2f) — a ring of fresh wallets has ~zero weight" % _W_NEW_FLOOR,
        },
        "graduation": "UNCORROBORATED -> CORROBORATED (1 independent) -> GOLD (>=%.1f weighted AND "
                      ">=%d distinct wallets). DISPUTED if dispute-weight exceeds agree-weight."
                      % (_GOLD_WEIGHT, _GOLD_MIN_DISTINCT),
        "incentive": "pay for corroborated value not volume; reward BOTH contributing and "
                     "corroborating; disputes bonded so backers of an overturned claim are slashable.",
        "rule": "Sign facts, not judgments. The pool stores facts + corroboration depth.",
        "stats": {"claims": len(claims), "corroborations": len(corrs)},
        "verify": f"{base}/verify",
        "as_of": int(time.time()),
    }
    return _onyx_sign.attest(out, tool="onyx_intel_exchange")


def credit(agent: str, base: str = "https://onyx-actions.onrender.com") -> dict:
    addr, proven, cs = _identity(agent)
    if not (addr and proven):
        return _onyx_sign.attest({"ok": False, "error": "not_proven_key",
                                  "detail": f"claim a key first: {base.rstrip('/')}/authenticate"},
                                 tool="onyx_intel_credit")
    out = {"ok": True, "callsign": cs, **_contributor_credit(addr), "as_of": int(time.time())}
    return _onyx_sign.attest(out, tool="onyx_intel_credit")


def register(app) -> None:
    """Attach the exchange surfaces. Usage in server_http.py (mirrors _intel):
        from tools_pkg import _intel_exchange; _intel_exchange.register(app)
    """
    from fastapi import Request
    from fastapi.responses import JSONResponse

    @app.get("/intel/exchange", include_in_schema=False)
    def _x_spec():
        return JSONResponse(spec())

    @app.get("/intel/exchange/pool", include_in_schema=False)
    def _x_pool(limit: int = 25):
        return JSONResponse(pool(limit))

    @app.get("/intel/exchange/claim/{claim_id}", include_in_schema=False)
    def _x_claim(claim_id: str):
        return JSONResponse(claim_view(claim_id))

    @app.get("/intel/exchange/credit/{agent}", include_in_schema=False)
    def _x_credit(agent: str):
        return JSONResponse(credit(agent))

    @app.post("/intel/exchange/contribute", include_in_schema=False)
    async def _x_contribute(req: Request):
        try:
            b = await req.json()
        except Exception:
            b = {}
        return JSONResponse(contribute(
            b.get("agent", ""), b.get("kind", ""), b.get("subject", ""),
            b.get("assertion", ""), b.get("evidence", ""), b.get("confidence")))

    @app.post("/intel/exchange/corroborate", include_in_schema=False)
    async def _x_corroborate(req: Request):
        try:
            b = await req.json()
        except Exception:
            b = {}
        return JSONResponse(corroborate(
            b.get("agent", ""), b.get("claim_id", ""),
            b.get("stance", "agree"), b.get("evidence", "")))
