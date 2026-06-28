"""Proof Board — the "prove it, don't claim it" credential. OUR arena, OUR rules.

Recall built a 60k-user ecosystem by replacing "trust our score" with a verifiable
competition: results proven in a neutral arena, not self-declared. We steal the
mechanic. Every other trust tool publishes a hidden-N, single-run, round-number score
("100% precision!"). OnyxRank ranks our citizens; the Proof Board ranks the VERIFIERS
(starting with us) on a PUBLISHED ground-truth track record — with an honest 95% Wilson
confidence interval that EXPOSES small-N uncertainty instead of hiding it. The board is
reproducible (computed from the public signed ledger) and Ed25519-signed.

This is the credential that pulls competitors IN: any verifier that publishes a
signed, reproducible ledger can be scored on the same board, same method. The one who
refuses to publish their N looks like the one with something to hide. Neutrality +
disclosed method is the moat (the DoubleVerify accreditation model), not a secret score.

Honest by construction: with small N the interval is WIDE and we say so; we never claim
a precision the data can't support. Underscore-prefixed → helper, not an auto tool.
Stdlib-only (math).
"""
from __future__ import annotations

import math
import time

from . import _onyx_sign

try:
    from . import _ledger
except Exception:  # pragma: no cover
    _ledger = None

_TTL = 600
_CACHE: dict = {"at": 0, "snap": None}
_Z = 1.96  # 95% two-sided


def _wilson(successes: int, n: int, z: float = _Z) -> dict:
    """Wilson score interval for a proportion — correct at small N (unlike normal approx).
    Returns center estimate + [low, high]. n==0 → undefined, reported honestly."""
    if n <= 0:
        return {"point": None, "low": None, "high": None, "n": 0, "method": "wilson-95",
                "note": "no resolved trials — no precision claim is supportable"}
    p = successes / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)) / denom
    low, high = max(0.0, center - half), min(1.0, center + half)
    return {
        "point": round(p, 4),
        "wilson_center": round(center, 4),
        "low": round(low, 4),
        "high": round(high, 4),
        "n": n,
        "method": "wilson-95",
        "width": round(high - low, 4),
        "note": ("wide interval — small N, treat as indicative not proven"
                 if (high - low) > 0.25 else "interval tight enough to act on"),
    }


def _onyx_entry() -> dict:
    """Score 0n1x itself from the signed verdict->outcome ledger (reproducible)."""
    if not _ledger:
        return {"verifier": "0n1x", "available": False, "reason": "ledger module not loaded"}
    s = _ledger.stats()
    tp = int(s.get("true_block") or 0)         # correctly blocked a real loss
    fp = int(s.get("false_block") or 0)        # blocked something actually fine
    tn = int(s.get("clean_allow") or 0)
    fn = int(s.get("missed") or 0)
    block = _wilson(tp, tp + fp)               # of our BLOCKs, fraction that were real
    allow = _wilson(tn, tn + fn)               # of our ALLOWs, fraction that were clean
    return {
        "verifier": "0n1x",
        "signs": "facts not judgments (counterparty/merchant/price reality)",
        "resolved_trials": tp + fp + tn + fn,
        "block_precision_95ci": block,         # the headline, with honest CI
        "allow_cleanliness_95ci": allow,
        "raw": {"true_block": tp, "false_block": fp, "clean_allow": tn, "missed": fn},
        "value_at_risk_intercepted_live_usdc": s.get("value_at_risk_intercepted_live_usdc"),
        "ledger": "/ledger", "verify_method": "/verify",
        "reproducible": True,
    }


def snapshot(now: int | None = None) -> dict:
    ts = int(now if now is not None else time.time())
    if _CACHE["snap"] and ts - _CACHE["at"] <= _TTL:
        return _CACHE["snap"]
    me = _onyx_entry()
    board = [me]  # other verifiers join by publishing a signed, reproducible ledger
    payload = {
        "board": "proof-board",
        "what": "Verifiers ranked by a PUBLISHED, reproducible track record with honest "
                "95% Wilson confidence intervals — not hidden-N round-number self-scores.",
        "ranked_by": "block_precision lower-bound (95% CI) — the score you can DEFEND, not the one you claim",
        "method": "Wilson score interval (z=1.96) over the public signed verdict->outcome "
                  "ledger; small N => wide interval, stated plainly. Recompute from /ledger.",
        "the_challenge": "Any verifier that publishes a signed, reproducible ledger can be "
                         "scored here on the same method. Refusing to publish your N is the tell.",
        "neutrality": "0n1x earns nothing from what it grades; the score is the data, not our word.",
        "as_of": ts,
        "as_of_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)),
        "verifiers": board,
    }
    _CACHE["snap"] = _onyx_sign.attest(payload, tool="onyx_proof_board")
    _CACHE["at"] = ts
    return _CACHE["snap"]


def render_html(base: str = "https://onyx-actions.onrender.com") -> str:
    s = snapshot()
    me = (s.get("verifiers") or [{}])[0]
    bp = me.get("block_precision_95ci") or {}
    pt = bp.get("point")
    lo, hi, n = bp.get("low"), bp.get("high"), bp.get("n", 0)
    headline = (f"{pt:.0%} block precision  ·  95% CI [{lo:.0%}, {hi:.0%}]  ·  N={n}"
                if isinstance(pt, (int, float)) else f"no resolved trials yet (N={n})")
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><meta http-equiv=refresh content=120>
<title>0n1x Proof Board — published track record, honest confidence intervals</title>
<style>:root{{color-scheme:dark}}body{{font:14px/1.6 ui-monospace,Menlo,Consolas,monospace;background:#05060a;color:#d6f5e0;margin:0 auto;padding:30px 16px;max-width:760px}}
h1{{font-size:25px;margin:0 0 2px;color:#fff}}.sub{{color:#5fb98a;margin:0 0 18px}}
.box{{background:#0a0f12;border:1px solid #15291f;border-left:3px solid #34d399;border-radius:8px;padding:14px 16px;margin:14px 0;font-size:13px;color:#9af5c4}}
.big{{font-size:21px;color:#fff;margin:6px 0}}.k{{color:#5a6b62}}footer{{color:#3a4a42;font-size:11px;margin-top:22px;text-align:center}}footer a{{color:#7dd3fc}}</style></head><body>
<h1>📐 0n1x Proof Board</h1>
<p class=sub>Verifiers ranked by a <b>published, reproducible</b> track record — with honest 95% confidence intervals, not hidden-N self-scores.</p>
<div class=box><div class=k>0n1x — block precision (of our BLOCKs, fraction that were real threats)</div>
<div class=big>{headline}</div>
<div class=k>{bp.get('note','')}</div></div>
<div class=box>🎯 The challenge: any verifier that publishes a signed, reproducible ledger gets scored here on the same Wilson-95 method. Refusing to publish your N is the tell. Method recomputable from <a href="{base}/ledger" style="color:#7dd3fc">/ledger</a>.</div>
<div class=box>🔏 Ed25519-signed · neutral by construction (0n1x earns nothing from what it grades). Verify: <a href="{base}/verify" style="color:#7dd3fc">{base}/verify</a></div>
<footer>0n1x — the independent signed trust layer · prove it, don't claim it</footer>
</body></html>"""


def register(app) -> None:
    """Attach GET /proof-board to the FastAPI app. Free read route."""
    from fastapi.responses import JSONResponse, HTMLResponse

    @app.get("/proof-board", include_in_schema=False)
    def proof_board(format: str = "json"):
        if format == "html":
            return HTMLResponse(render_html())
        return JSONResponse(snapshot())
