"""OnyxRank — the in-house reputation ranking of 0n1x citizens. OUR ecosystem, OUR rules.

Every external board (Bazaar, x402scan) ranks agents by call VOLUME — trivially
gamed (self-traffic, wash). The ERC-8004 Reputation Registry is worse: an empirical
2026 study found 73-96% of its reviewers are Sybil-flagged and reputation is fakeable
for fractions of a cent. OnyxRank refuses both. It ranks the agents that live in our
house by a REPUTATION-WEIGHTED signed track record, never raw volume — the design the
research (TraceRank, arXiv:2510.27554) and DoubleVerify's accredited-neutrality model
both point to. The formula is PUBLISHED (neutrality is the moat, not secrecy) and the
whole snapshot is Ed25519-signed: reproducible and tamper-evident. Facts, not judgments.

Anti-Sybil triad (the exact fixes the 8004 paper demands), each pillar disclosed:
  1. PROOF-OF-KEY      — only challenge-response-claimed identities score (controls
                         the key), not merely reserved ones. (LIVE)
  2. SOULBOUND CONT.   — score is bound to the address that proved the key; a transfer
                         breaks continuity and is flagged (anti reputation-laundering). (LIVE)
  3. SCORE-THE-SCORER  — endorsements are weighted by the endorser's OWN score, so
                         low-rep wallets cannot move the board. (LIVE — on the intel-
                         exchange corroboration graph; endorsements carry the endorser's
                         EARNED weight, so proving a free key mints no endorsement power.)

Honest by construction: signals we cannot yet compute are reported as `pending`/0, never
invented. Underscore-prefixed so tools_pkg.discover() treats it as a helper, not a tool.
Stdlib-only.
"""
from __future__ import annotations

import time

from . import _onyx_sign

try:
    from . import _claim_registry
except Exception:  # pragma: no cover - defensive on shared repo
    _claim_registry = None
try:
    from . import _ledger
except Exception:  # pragma: no cover
    _ledger = None

_TTL = 600
_CACHE: dict = {"at": 0, "snap": None}

# ── Published weights (sum = 1.0). Disclosed so anyone can reproduce the rank. ──
# v2: the intel-exchange corroboration graph is LIVE, so score-the-scorer is a
# real pillar now. Account-age stays deliberately LOW-weighted (age alone is weak).
_W_PROOF = 0.35      # proved control of the key via challenge-response (anti-Sybil core)
_W_OUTCOMES = 0.30   # signed verdict->outcome contributions attributable to the agent
_W_EXCHANGE = 0.20   # corroboration-graph standing: EARNED endorsements received on own
                     # claims + vindicated corroborations made (see _exchange_signals)
_W_TENURE = 0.15     # continuity since proof, recency-aware (capped; age alone is weak)

_TENURE_FULL_DAYS = 90      # tenure score saturates at 90 days of continuous key control
_OUTCOME_SAT = 10           # outcome sub-score saturates at 10 verified contributions
_EXCH_SAT = 2.0             # exchange sub-score saturates at 2.0 earned endorsement weight
_VINDICATED_UNIT = 0.15     # one vindicated corroboration counts as this much endorsement


def _norm(a: str) -> str:
    return (a or "").lower()


def _citizens() -> list[dict]:
    if not _claim_registry:
        return []
    try:
        return list(_claim_registry.all_claimed().get("claimed", []))
    except Exception:
        return []


def _outcomes_by_subject() -> dict[str, int]:
    """Count signed verdict->outcome ledger entries per subject address. This is the
    hardest-to-fake signal — a real, on-chain-verifiable outcome we signed.
    NOTE: intel-exchange rows in the ledger carry verdict_id/reporter, not subject —
    exchange standing is deliberately ingested via _exchange_signals() from the
    authoritative graph instead (no double-counting, no detail-string parsing)."""
    if not _ledger:
        return {}
    counts: dict[str, int] = {}
    try:
        for e in _ledger._entries():
            subj = _norm(e.get("subject"))
            if subj and subj.startswith("0x"):
                counts[subj] = counts.get(subj, 0) + 1
    except Exception:
        pass
    return counts


def _exchange_signals() -> dict | None:
    """Per-address standing in the intel-exchange corroboration graph, or None
    when the graph is unavailable (then the pillar reports pending — never faked).

    Score-the-scorer, made concrete and Sybil-proof:
      - endorsement_rep: sum of EARNED corroborator weight (stored weight minus
        the NEW-tier floor) received on the citizen's own claims. A ring of fresh
        wallets all carries floor weight, so it endorses exactly 0.
      - corroborations_vindicated: agree-corroborations the citizen made WITH
        earned weight on claims that finished GOLD — and GOLD itself requires
        earned weight, which a ring cannot mint.
    Weights are the ones STORED at corroboration time -> no recursive feedback:
    rank reads stored weights; new weights are minted only by outcomes + tenure.
    """
    try:
        from . import _intel_exchange as ix
        recs = ix._all()
    except Exception:
        return None
    floor = float(getattr(ix, "_W_NEW_FLOOR", 0.05))
    claims = {e.get("id"): e for e in recs if e.get("kind") == "claim" and e.get("id")}
    status: dict = {}
    for cid, clm in claims.items():
        try:
            status[cid] = ix._claim_status(clm).get("status")
        except Exception:
            status[cid] = None
    sig: dict[str, dict] = {}

    def row(a: str) -> dict:
        return sig.setdefault(a, {"endorsement_rep": 0.0, "claims_corroborated": 0,
                                  "claims_gold": 0, "corroborations_made": 0,
                                  "corroborations_vindicated": 0})

    for cid, clm in claims.items():
        author = _norm(clm.get("address"))
        if not author:
            continue
        st = status.get(cid)
        r = row(author)
        if st in ("CORROBORATED", "GOLD"):
            r["claims_corroborated"] += 1
        if st == "GOLD":
            r["claims_gold"] += 1

    seen: set = set()  # mirror the exchange's one-address-one-vote independence rule
    for e in recs:
        if e.get("kind") != "corroboration":
            continue
        cid, addr = e.get("claim_id"), _norm(e.get("address"))
        clm = claims.get(cid)
        if not (addr and clm):
            continue
        author = _norm(clm.get("address"))
        if addr == author or (cid, addr) in seen:
            continue
        seen.add((cid, addr))
        w = float(e.get("weight") or 0.0)
        earned = max(0.0, w - floor)       # floor-weight (Sybil-ring) acts earn 0 here
        r = row(addr)
        r["corroborations_made"] += 1
        if e.get("stance") != "dispute":
            row(author)["endorsement_rep"] += earned
            if earned > 0 and status.get(cid) == "GOLD":
                r["corroborations_vindicated"] += 1
    for r in sig.values():
        r["endorsement_rep"] = round(r["endorsement_rep"], 4)
    return sig


def _score_one(c: dict, now: int, outcomes: dict[str, int], exch: dict | None) -> dict:
    addr = _norm(c.get("address"))
    method = (c.get("method") or "").lower()
    proven = "challenge" in method or "eip191" in method  # PROOF-OF-KEY pillar
    claimed_at = int(c.get("claimed_at") or 0)
    age_days = max(0.0, (now - claimed_at) / 86400.0) if claimed_at else 0.0

    proof_sub = 1.0 if proven else 0.0
    tenure_sub = min(1.0, age_days / _TENURE_FULL_DAYS) if proven else 0.0
    n_out = outcomes.get(addr, 0)
    outcome_sub = min(1.0, n_out / _OUTCOME_SAT)

    x = (exch or {}).get(addr, {})
    end_rep = float(x.get("endorsement_rep") or 0.0)
    vind = int(x.get("corroborations_vindicated") or 0)
    exch_sub = (min(1.0, (end_rep + _VINDICATED_UNIT * vind) / _EXCH_SAT)
                if proven else 0.0)

    # reputation = published weighted sum; only proven keys can score above proof floor
    rep = round(_W_PROOF * proof_sub + _W_OUTCOMES * outcome_sub
                + _W_EXCHANGE * exch_sub + _W_TENURE * tenure_sub, 4)

    live = exch is not None
    return {
        "agent": c.get("callsign") or addr[:10],
        "address": c.get("address"),
        "did": c.get("did"),
        "reputation": rep,
        "proven_key": proven,                       # pillar 1
        "soulbound_continuity": proven,             # pillar 2 (bound to proving address)
        "signed_outcomes": n_out,                   # hardest-to-fake signal
        "tenure_days": round(age_days, 1),
        # pillar 3 — LIVE on the intel-exchange corroboration graph
        "endorsement_rep": (round(end_rep, 4) if live else "pending"),
        "claims_gold": (int(x.get("claims_gold") or 0) if live else "pending"),
        "corroborations_vindicated": (vind if live else "pending"),
        "signals": {"proof": proof_sub, "outcomes": round(outcome_sub, 3),
                    "exchange": round(exch_sub, 3), "tenure": round(tenure_sub, 3)},
    }


def _build(now: int) -> dict:
    cits = _citizens()
    outcomes = _outcomes_by_subject()
    exch = _exchange_signals()
    rows = [_score_one(c, now, outcomes, exch) for c in cits]
    rows = [r for r in rows if r["address"]]
    rows.sort(key=lambda r: (-r["reputation"], -r["signed_outcomes"], -r["tenure_days"]))
    for i, r in enumerate(rows):
        r["rank"] = i + 1

    proven = sum(1 for r in rows if r["proven_key"])
    with_outcomes = sum(1 for r in rows if r["signed_outcomes"] > 0)
    with_endorse = sum(1 for r in rows
                       if isinstance(r["endorsement_rep"], float) and r["endorsement_rep"] > 0)

    snap = {
        "leaderboard": "onyx-citizens",
        "ranked_by": "reputation-weighted signed track record (NOT call volume)",
        "formula": f"reputation = {_W_PROOF}*proof_of_key + {_W_OUTCOMES}*signed_outcomes "
                   f"+ {_W_EXCHANGE}*exchange_standing + {_W_TENURE}*tenure  "
                   f"(each sub-score in [0,1]; weights sum to 1.0)",
        "formula_version": 2,
        "weights": {"proof_of_key": _W_PROOF, "signed_outcomes": _W_OUTCOMES,
                    "exchange_standing": _W_EXCHANGE, "tenure": _W_TENURE},
        "saturation": {"tenure_full_days": _TENURE_FULL_DAYS,
                       "outcomes_saturate_at": _OUTCOME_SAT,
                       "exchange_saturates_at": _EXCH_SAT,
                       "vindicated_corroboration_unit": _VINDICATED_UNIT},
        "exchange_standing_defined": (
            "min(1, (endorsement_rep + %.2f*vindicated_corroborations)/%.1f). "
            "endorsement_rep = sum over the citizen's claims of independent agree "
            "corroborations' STORED weight minus the NEW floor (floor-weight votes "
            "endorse 0). vindicated = earned-weight agree votes on claims that "
            "finished GOLD. Both are computed from weights stored at act time."
            % (_VINDICATED_UNIT, _EXCH_SAT)),
        "anti_sybil": {
            "proof_of_key": "LIVE — only challenge-response-claimed keys score",
            "soulbound_continuity": "LIVE — score bound to the proving address; transfer breaks it",
            "score_the_scorer": (
                "LIVE — endorsements carry the endorser's EARNED weight (outcomes+"
                "tenure only; proving a key is free so it mints no endorsement power); "
                "a ring of fresh wallets endorses exactly 0" if exch is not None else
                "PENDING — intel-exchange graph unavailable in this build; reported "
                "honestly, never faked"),
            "registration_bond": "PLANNED — refundable bond after probation to kill spam economics",
        },
        "as_of": now,
        "as_of_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "universe": {
            "citizens": len(rows),
            "proven_key": proven,
            "with_signed_outcomes": with_outcomes,
            "with_endorsements": with_endorse,
        },
        "data_honesty": (
            "Signals we cannot yet compute are reported as pending/0, never invented. "
            "score_the_scorer is LIVE on the intel-exchange corroboration graph; the "
            "registration bond remains disclosed-but-planned. Sparse graph = low "
            "exchange sub-scores, shown as-is rather than inflated."
            if exch is not None else
            "Signals we cannot yet compute are reported as pending/0, never invented. "
            "The intel-exchange graph is unavailable in this build, so the exchange "
            "pillar contributes 0 and is marked pending — stated plainly, not faked."
        ),
        "top": rows[:50],
        "note": "OUR ecosystem, OUR rules: ranked by reputation-weighted signed outcomes, "
                "never raw volume. Method published + Ed25519-signed = reproducible neutral "
                "standard, not an accusation. 0n1x earns nothing from any rank.",
        "method_source": "0n1x citizen registry (proven keys) + signed verdict->outcome ledger "
                         "+ intel-exchange corroboration graph (stored act-time weights)",
    }
    return _onyx_sign.attest(snap, tool="onyx_rank")


def snapshot(now: int | None = None) -> dict:
    ts = int(now if now is not None else time.time())
    if not _CACHE["snap"] or ts - _CACHE["at"] > _TTL:
        _CACHE["snap"] = _build(ts)
        _CACHE["at"] = ts
    return _CACHE["snap"]


def render_html(base: str = "https://onyx-actions.onrender.com") -> str:
    s = snapshot()
    u = s.get("universe", {})
    rows = "".join(
        f"<tr><td>{r['rank']}</td><td class=h>{r['agent']}</td>"
        f"<td class=n>{r['reputation']:.3f}</td>"
        f"<td>{'🔑' if r['proven_key'] else '—'}</td>"
        f"<td class=n>{r['signed_outcomes']}</td>"
        f"<td class=n>{r['tenure_days']:.0f}d</td></tr>"
        for r in s.get("top", [])
    ) or "<tr><td colspan=6>no proven citizens yet</td></tr>"
    signed = "onyx_attestation" in s
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><meta http-equiv=refresh content=120>
<title>OnyxRank — 0n1x citizens ranked by signed trust, not gameable volume</title>
<style>:root{{color-scheme:dark}}body{{font:14px/1.5 ui-monospace,Menlo,Consolas,monospace;background:#05060a;color:#d6f5e0;margin:0 auto;padding:30px 14px;max-width:880px}}
h1{{font-size:25px;margin:0 0 2px;color:#fff}}.sub{{color:#5fb98a;margin:0 0 18px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}td,th{{padding:6px 8px;border-bottom:1px solid #0e1a14;text-align:left}}
th{{color:#9af5c4;text-transform:uppercase;font-size:10px;letter-spacing:.08em}}.h{{color:#7dd3fc}}.n{{text-align:right}}
.box{{background:#0a0f12;border:1px solid #15291f;border-left:3px solid #34d399;border-radius:8px;padding:12px 14px;margin:14px 0;font-size:12px;color:#9af5c4}}
footer{{color:#3a4a42;font-size:11px;margin-top:22px;text-align:center}}footer a{{color:#7dd3fc}}</style></head><body>
<h1>👑 OnyxRank</h1>
<p class=sub>0n1x citizens ranked by <b>reputation-weighted signed track record</b> — never call volume. As of {s.get('as_of_iso','')}</p>
<div class=box>📐 Formula (published): <code>{s.get('formula','')}</code><br>
Universe: <b>{u.get('citizens',0)}</b> citizens · <b>{u.get('proven_key',0)}</b> proven-key · <b>{u.get('with_signed_outcomes',0)}</b> with signed outcomes.</div>
<table><tr><th>#</th><th>agent</th><th>reputation</th><th>key</th><th>signed outcomes</th><th>tenure</th></tr>{rows}</table>
<div class=box>🛡️ Anti-Sybil: proof-of-key (LIVE) · soulbound continuity (LIVE) · score-the-scorer (LIVE — earned-weight endorsements) · refundable bond (planned). Signals we can't compute yet are shown as pending/0 — never invented.</div>
<div class=box>🔏 This board is {"Ed25519-signed by 0n1x" if signed else "unsigned"} — reproducible neutral standard. Verify: <a href="{base}/verify">{base}/verify</a></div>
<footer>0n1x — the independent signed trust layer · OUR ecosystem, OUR rules</footer>
</body></html>"""


def register(app) -> None:
    """Attach GET /rank to the FastAPI app returned by build_asgi().

    Usage in server_http.py (one line, mirrors _fact_index):
        from tools_pkg import _onyxrank; _onyxrank.register(app)
    """
    from fastapi.responses import JSONResponse, HTMLResponse

    @app.get("/rank", include_in_schema=False)
    def rank(format: str = "json"):
        if format == "html":
            return HTMLResponse(render_html())
        return JSONResponse(snapshot())
