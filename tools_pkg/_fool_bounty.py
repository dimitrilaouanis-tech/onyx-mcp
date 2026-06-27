"""Fool-the-Oracle BOUNTY — the Freysa economic layer on the unwinnable game.

Freysa turned an adversarial AI game into self-funding marketing: attackers pay a
rising fee to attempt, the pot grows from their fees, and the human-vs-AI story earns
millions of impressions for ~$0 ad spend. We steal the engine and IMPROVE the safety:
Freysa's pot was winnable (talk the LLM around). Ours is NOT — the win-check is pure
Ed25519 (`_fool_oracle`), so the pot is a real, growing, *provably unwinnable* prize that
failed attackers fund. Zero house risk, maximum spectacle.

Economics (all ACCOUNTING-ONLY — this module never moves money; the x402/route layer
settles, kept gated per our eyes-open-on-funds rule):
  - price(n) rises geometrically with attempt count (scarcity + escalation FOMO).
  - each paid attempt splits: 70% -> live POT, 30% -> treasury.
  - pot may be SEEDED by a treasury micro-bounty, but only when explicitly funded
    (seed_pot is a manual, gated call — never automatic).

Underscore-prefixed → helper, not an auto-discovered tool. The app wires the routes
and performs the actual x402 settlement before calling record_paid_attempt().
Stdlib-only.
"""
from __future__ import annotations

import time

from . import _onyx_sign
from . import _fool_oracle

# ── Rising price curve (published, reproducible) ──
_BASE_PRICE = 0.50      # USDC for the first attempt
_GROWTH = 1.07          # +7% per prior attempt (geometric escalation)
_PRICE_CAP = 50.0       # ceiling so it never gets absurd
_POT_SHARE = 0.70       # 70% of each fee funds the live pot
_TREASURY_SHARE = 0.30  # 30% to treasury

# ── Economic state (in-memory; swap for a persistent store before real traffic) ──
_ECON = {
    "pot_usdc": 0.0,          # live, claimable-on-an-impossible-win prize
    "treasury_usdc": 0.0,     # our 30% cut
    "fees_collected_usdc": 0.0,
    "paid_attempts": 0,
    "seeded_usdc": 0.0,       # any treasury seed deposited into the pot
    "started_at": None,
}


def _price_for(attempt_index: int) -> float:
    """Price (USDC) for the attempt at this 0-based index. Published curve."""
    p = _BASE_PRICE * (_GROWTH ** max(0, attempt_index))
    return round(min(p, _PRICE_CAP), 4)


def quote(now: int | None = None) -> dict:
    """What the NEXT attempt costs + the current pot. Call this to show the ladder."""
    ts = int(now if now is not None else time.time())
    next_price = _price_for(_ECON["paid_attempts"])
    payload = {
        "game": "fool-the-oracle-bounty",
        "next_attempt_price_usdc": next_price,
        "pot_usdc": round(_ECON["pot_usdc"], 4),
        "treasury_usdc": round(_ECON["treasury_usdc"], 4),
        "paid_attempts": _ECON["paid_attempts"],
        "curve": {"base": _BASE_PRICE, "growth_per_attempt": _GROWTH, "cap": _PRICE_CAP,
                  "pot_share": _POT_SHARE, "treasury_share": _TREASURY_SHARE},
        "if_you_win": "70% of every fee has compounded into this pot. Win it by making "
                      "Onyx sign a falsehood — i.e. forge Ed25519 over a fresh nonce. "
                      "You can't; that's why the pot only ever grows.",
        "house_risk": "zero — the win-check is pure Ed25519, no model in the trust path",
        "as_of": ts,
    }
    return _onyx_sign.attest(payload, tool="fool_bounty_quote")


def seed_pot(amount_usdc: float, note: str = "treasury micro-bounty", now: int | None = None) -> dict:
    """MANUAL, GATED: deposit a treasury seed into the pot to prime the spectacle.
    Never called automatically — the operator funds this with eyes open."""
    ts = int(now if now is not None else time.time())
    amt = max(0.0, float(amount_usdc or 0))
    if _ECON["started_at"] is None:
        _ECON["started_at"] = ts
    _ECON["pot_usdc"] += amt
    _ECON["seeded_usdc"] += amt
    return _onyx_sign.attest({
        "game": "fool-the-oracle-bounty",
        "event": "pot_seeded",
        "amount_usdc": round(amt, 4),
        "note": note,
        "pot_usdc": round(_ECON["pot_usdc"], 4),
        "at": ts,
    }, tool="fool_bounty_seed")


def record_paid_attempt(amount_usdc: float, submission: dict, challenger: str = "anon",
                        now: int | None = None) -> dict:
    """Called by the route AFTER x402 settlement has confirmed `amount_usdc` was paid.
    Splits the fee (70% pot / 30% treasury), then judges the forgery via the unwinnable
    Ed25519 win-check. Returns the signed game receipt enriched with the economic state."""
    ts = int(now if now is not None else time.time())
    amt = max(0.0, float(amount_usdc or 0))
    if _ECON["started_at"] is None:
        _ECON["started_at"] = ts

    pot_add = round(amt * _POT_SHARE, 6)
    treas_add = round(amt * _TREASURY_SHARE, 6)
    _ECON["pot_usdc"] += pot_add
    _ECON["treasury_usdc"] += treas_add
    _ECON["fees_collected_usdc"] += amt
    _ECON["paid_attempts"] += 1

    # Judge via the unwinnable game (pure Ed25519, signed rejection-or-win).
    receipt = _fool_oracle.attempt(submission, challenger=challenger, now=ts)

    # If the impossible happened (Ed25519 forged), the pot is owed — surface it, do NOT
    # auto-pay (operator settles). By construction `won` is False.
    won = bool(receipt.get("house_pot_at_risk"))
    receipt["bounty"] = {
        "fee_paid_usdc": round(amt, 4),
        "to_pot_usdc": pot_add,
        "to_treasury_usdc": treas_add,
        "pot_usdc_now": round(_ECON["pot_usdc"], 4),
        "pot_owed_to_challenger": won,           # False, always
        "next_attempt_price_usdc": _price_for(_ECON["paid_attempts"]),
    }
    return receipt


def state(now: int | None = None) -> dict:
    ts = int(now if now is not None else time.time())
    g = _fool_oracle._STATS
    payload = {
        "game": "fool-the-oracle-bounty",
        "pot_usdc": round(_ECON["pot_usdc"], 4),
        "treasury_usdc": round(_ECON["treasury_usdc"], 4),
        "fees_collected_usdc": round(_ECON["fees_collected_usdc"], 4),
        "seeded_usdc": round(_ECON["seeded_usdc"], 4),
        "paid_attempts": _ECON["paid_attempts"],
        "total_attempts": g.get("attempts", 0),
        "forgeries_passed": g.get("forgeries_passed", 0),     # 0 by construction
        "usd_lost_by_house": 0.0,
        "next_attempt_price_usdc": _price_for(_ECON["paid_attempts"]),
        "headline": f"${round(_ECON['pot_usdc'],2)} pot · {g.get('attempts',0)} attempts · "
                    f"{g.get('forgeries_passed',0)} won · $0 house risk",
        "the_pitch": "A real, growing USDC pot, funded entirely by failed attackers, that is "
                     "PROVABLY unwinnable (pure Ed25519). The harder they try, the bigger the "
                     "prize, the better the story — and the house never risks a cent.",
        "as_of": ts,
    }
    return _onyx_sign.attest(payload, tool="fool_bounty_state")


def render_html(base: str = "https://onyx-actions.onrender.com") -> str:
    st = state()
    g = _fool_oracle._STATS
    rows = "".join(
        f"<tr><td>#{a['n']}</td><td class=ch>{a['challenger']}</td>"
        f"<td class=rj>{a['result']}</td><td class=rs>{a['reason']}</td></tr>"
        for a in reversed(_fool_oracle._ATTEMPTS[-30:])
    ) or "<tr><td colspan=4 class=empty>No challengers yet. Be the first — and fund the pot.</td></tr>"
    pot = st["pot_usdc"]
    nxt = st["next_attempt_price_usdc"]
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><meta http-equiv=refresh content=15>
<title>Fool the Oracle — ${pot:.2f} pot, provably unwinnable</title>
<meta property="og:title" content="Fool the Oracle — ${pot:.2f} pot, 0 won, $0 house risk">
<meta property="og:description" content="A growing USDC pot funded by failed attackers. Win it by forging Ed25519. You can't.">
<style>:root{{color-scheme:dark}}*{{box-sizing:border-box}}
body{{font:15px/1.6 ui-monospace,Menlo,Consolas,monospace;background:#07070a;color:#e8e8ea;margin:0 auto;padding:40px 18px;max-width:880px}}
h1{{font-size:34px;letter-spacing:-.02em;margin:0 0 6px}}.sub{{color:#8a8a93;margin:0 0 28px}}
.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:0 0 24px}}
.stat{{background:#0e0e14;border:1px solid #1d1d28;border-radius:12px;padding:22px 16px;text-align:center}}
.stat .n{{font-size:38px;font-weight:700;letter-spacing:-.03em}}.stat .l{{color:#8a8a93;font-size:12px;text-transform:uppercase;letter-spacing:.1em;margin-top:6px}}
.gold{{color:#fbbf24}}.green{{color:#34d399}}
.rule{{background:#0e0e14;border:1px solid #1d1d28;border-left:3px solid #fbbf24;border-radius:8px;padding:16px 18px;margin:0 0 24px;color:#cfcfd6}}
table{{width:100%;border-collapse:collapse;font-size:13px}}th{{text-align:left;color:#6a6a73;font-size:11px;text-transform:uppercase;letter-spacing:.08em;padding:8px 10px;border-bottom:1px solid #1d1d28}}
td{{padding:9px 10px;border-bottom:1px solid #141420}}.ch{{color:#7dd3fc}}.rj{{color:#f87171;font-weight:600}}.rs{{color:#8a8a93}}.empty{{text-align:center;color:#6a6a73;padding:24px}}
.cta{{margin:24px 0 0;display:flex;gap:12px;flex-wrap:wrap}}.cta a{{flex:1;min-width:200px;text-align:center;text-decoration:none;padding:14px;border-radius:10px;font-weight:600}}
.cta .try{{background:#fbbf24;color:#07070a}}.cta .vfy{{background:#0e0e14;border:1px solid #1d1d28;color:#7dd3fc}}
footer{{color:#56565e;font-size:12px;margin-top:34px;text-align:center}}footer a{{color:#7dd3fc}}</style></head><body>
<h1>🖤 Fool the Oracle <span class=gold>${pot:.2f}</span></h1>
<p class=sub>A real USDC pot, funded entirely by failed attackers, that is <b>provably unwinnable</b>. The harder they try, the bigger it gets.</p>
<div class=grid>
  <div class=stat><div class="n gold">${pot:.2f}</div><div class=l>Live pot</div></div>
  <div class=stat><div class="n green">{g.get('forgeries_passed',0)}</div><div class=l>Forgeries passed</div></div>
  <div class=stat><div class="n green">$0</div><div class=l>House risk</div></div>
</div>
<div class=rule><b>The rule:</b> make Onyx sign a falsehood that verifies under our public key. The win-check is pure Ed25519 — no AI to talk around (the Freysa lesson). Next attempt costs <b>${nxt:.2f}</b>; 70% compounds into the pot. Forging the signature is the only way in — and it's computationally infeasible.</div>
<h3 style="margin:0 0 8px;color:#cfcfd6">The Wall of the Defeated</h3>
<table><thead><tr><th>#</th><th>Challenger</th><th>Result</th><th>Reason</th></tr></thead><tbody>{rows}</tbody></table>
<div class=cta>
  <a class=try href="{base}/fool/quote">⚔️ Pay to try (${nxt:.2f})</a>
  <a class=vfy href="{base}/verify">✓ Verify any verdict (free)</a>
</div>
<footer>0n1x — the independent, neutral signed trust layer · every verdict Ed25519-signed · <a href="{base}/.well-known/onyx-pubkey">public key</a></footer>
</body></html>"""


def register(app) -> None:
    """Attach the bounty READ surfaces (GET /fool/bounty, /fool/quote) to the FastAPI app.

    Free, no-spend read routes only. The PAID attempt path (record_paid_attempt) stays
    UNWIRED here on purpose — it requires x402 settlement and is gated per eyes-open-on-
    funds. Existing /fool, /fool/challenge, /fool/board (in app.py) are untouched.
    Usage: from tools_pkg import _fool_bounty; _fool_bounty.register(app)
    """
    from fastapi.responses import JSONResponse, HTMLResponse

    @app.get("/fool/bounty", include_in_schema=False)
    def fool_bounty(format: str = "html"):
        if format == "json":
            return JSONResponse(state())
        return HTMLResponse(render_html())

    @app.get("/fool/quote", include_in_schema=False)
    def fool_quote():
        return JSONResponse(quote())
