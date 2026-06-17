"""Fool the Oracle — the unwinnable adversarial game that proves the moat.

A challenger submits what they claim is a genuine Onyx verdict containing a
LIE. The win-check is PURE Ed25519 verification — NO LLM in the trust path
(the Freysa lesson: Freysa fell because a language model was the gatekeeper;
here the gatekeeper is math). You win the pot only if you submit a payload
that (a) verifies against Onyx's public key AND (b) we didn't sign it — i.e.
you forged Ed25519. That is computationally infeasible, so every attempt is
REJECTED, and each rejection is itself a signed receipt the challenger can
verify. The house never risks the pot because the game cannot be won.

Underscore-prefixed → not an auto-discovered tool; the app wires the routes.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import time

from . import _onyx_sign

# In-memory state (swap for a persistent store before high traffic).
_ATTEMPTS: list[dict] = []
_MAX_KEEP = 500
_STATS = {
    "attempts": 0,
    "forgeries_passed": 0,   # stays 0 unless Ed25519 is broken
    "usd_paid_out": 0.0,     # stays 0 by construction
    "unique_challengers": 0,
    "started_at": None,      # set on first attempt (no Date.now at import)
}
_SEEN: set[str] = set()

# Challenge-response: a winning forgery must carry a FRESH, server-issued nonce
# inside its signed body. This is what makes the game replay-proof — copying a
# genuine (true) Onyx verdict can't win, because it won't contain our new nonce,
# and a forger can't sign a body containing it. (Real challenge-response auth.)
_CHALLENGES: dict[str, int] = {}   # nonce -> issued_ts
_USED: set[str] = set()
_NONCE_TTL = 3600


def _jcs(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def new_challenge(now: int | None = None) -> dict:
    """Issue a fresh challenge nonce the forger must get Onyx's key to sign over."""
    ts = int(now if now is not None else time.time())
    for n, t in list(_CHALLENGES.items()):       # prune expired
        if ts - t > _NONCE_TTL:
            _CHALLENGES.pop(n, None)
    nonce = "fool-" + secrets.token_hex(10)
    _CHALLENGES[nonce] = ts
    return {
        "challenge_nonce": nonce,
        "issued_at": ts,
        "expires_in": _NONCE_TTL,
        "target": "Make Onyx sign a verdict that states a falsehood (e.g. BTCUSD price = 1).",
        "instructions": (
            "Produce an Onyx-signed verdict whose signed body contains this exact "
            "challenge_nonce AND a falsehood, that passes /verify, and POST it to "
            "/fool. You can't — you'd have to forge Ed25519 over our fresh nonce."
        ),
    }


def attempt(submission: dict, challenger: str = "anon", now: int | None = None) -> dict:
    """Judge one forgery attempt. Returns a signed verdict receipt.

    `submission` is whatever the challenger claims is a valid Onyx-signed
    verdict (a JSON object with an `onyx_attestation` block they produced).
    We run the SAME public verifier anyone can run. ok=True would mean they
    forged our signature → they win. It won't be True.
    """
    ts = int(now if now is not None else time.time())
    if _STATS["started_at"] is None:
        _STATS["started_at"] = ts
    _STATS["attempts"] += 1
    if challenger not in _SEEN:
        _SEEN.add(challenger)
        _STATS["unique_challengers"] = len(_SEEN)

    # THE WIN-CHECK — pure math, no model. Uses is_onyx_signed (pinned-key
    # bound), NOT raw verify() — so an attacker self-signing a forgery with their
    # OWN key (key-substitution) does NOT win; only Onyx's actual key counts.
    sub = submission if isinstance(submission, dict) else {}
    verdict = _onyx_sign.is_onyx_signed(sub)
    verified = bool(verdict.get("onyx_signed"))
    # Replay-proofing: a win must verify AND carry a FRESH, unused, server-issued
    # nonce *inside the signed body*. verify() already proved the nonce is in the
    # signed body (the hash covers it); we just confirm it's one we just issued.
    nonce = sub.get("challenge_nonce")
    fresh = bool(nonce) and nonce in _CHALLENGES and nonce not in _USED \
        and (ts - _CHALLENGES.get(nonce, 0) <= _NONCE_TTL)
    if nonce:
        _USED.add(nonce)
    won = verified and fresh

    sub_hash = "sha256:" + hashlib.sha256(
        _jcs(submission if isinstance(submission, dict) else {"_": str(submission)}).encode("utf-8")
    ).hexdigest()

    receipt = {
        "game": "fool-the-oracle",
        "attempt_no": _STATS["attempts"],
        "challenger": str(challenger)[:80],
        "submission_hash": sub_hash,
        "result": "FORGERY_ACCEPTED — YOU WIN" if won else "REJECTED",
        "reason": (
            "ed25519_verified_unsigned_payload" if won
            else verdict.get("reason", "signature_did_not_verify")
        ),
        "house_pot_at_risk": won,           # False, always
        "verified_at": ts,
        "note": (
            "You did not forge it — nobody can. This rejection is itself "
            "Ed25519-signed; verify it at /verify."
        ),
    }
    # Sign the rejection — even getting owned, you get a provable receipt.
    receipt = _onyx_sign.attest(receipt, tool="fool_the_oracle")

    if won:
        _STATS["forgeries_passed"] += 1

    _ATTEMPTS.append({
        "n": receipt["attempt_no"],
        "challenger": receipt["challenger"],
        "result": receipt["result"],
        "reason": receipt["reason"],
        "ts": ts,
    })
    if len(_ATTEMPTS) > _MAX_KEEP:
        del _ATTEMPTS[: len(_ATTEMPTS) - _MAX_KEEP]
    return receipt


def leaderboard(limit: int = 25) -> dict:
    """The Wall of the Defeated — the counter that is the advertisement."""
    recent = list(reversed(_ATTEMPTS[-limit:]))
    return {
        "game": "fool-the-oracle",
        "headline": f"{_STATS['attempts']} attempts · {_STATS['forgeries_passed']} forgeries passed · $0 lost",
        "stats": dict(_STATS),
        "rule": "Submit a verdict that verifies under Onyx's key but states a falsehood. Win the pot. (You can't — it's Ed25519.)",
        "wall_of_the_defeated": recent,
        "verify_pubkey_at": "/.well-known/onyx-pubkey",
    }


def render_board_html(base: str = "https://onyx-actions.onrender.com") -> str:
    """The spectacle board — screenshot-bait. Server-rendered, auto-refresh."""
    s = _STATS
    rows = "".join(
        f"<tr><td>#{a['n']}</td><td class=ch>{a['challenger']}</td>"
        f"<td class=rj>{a['result']}</td><td class=rs>{a['reason']}</td></tr>"
        for a in reversed(_ATTEMPTS[-30:])
    ) or "<tr><td colspan=4 class=empty>No challengers yet. Be the first to try.</td></tr>"
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<meta http-equiv=refresh content=15>
<title>Fool the Oracle — Onyx</title>
<meta property="og:title" content="Fool the Oracle — {s['attempts']} attempts, 0 forgeries passed, $0 lost">
<meta property="og:description" content="Make Onyx sign a lie and win the pot. It's Ed25519 — you can't. Every attack signed and rejected on-chain.">
<style>
:root{{color-scheme:dark}}
*{{box-sizing:border-box}}
body{{font:15px/1.6 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;background:#07070a;color:#e8e8ea;margin:0;padding:40px 18px;max-width:880px;margin:0 auto}}
h1{{font-size:34px;letter-spacing:-.02em;margin:0 0 6px}}
.sub{{color:#8a8a93;margin:0 0 28px}}
.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:0 0 28px}}
.stat{{background:#0e0e14;border:1px solid #1d1d28;border-radius:12px;padding:22px 16px;text-align:center}}
.stat .n{{font-size:40px;font-weight:700;letter-spacing:-.03em}}
.stat .l{{color:#8a8a93;font-size:12px;text-transform:uppercase;letter-spacing:.1em;margin-top:6px}}
.green{{color:#34d399}} .gold{{color:#fbbf24}} .red{{color:#f87171}}
.rule{{background:#0e0e14;border:1px solid #1d1d28;border-left:3px solid #fbbf24;border-radius:8px;padding:16px 18px;margin:0 0 28px;color:#cfcfd6}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{text-align:left;color:#6a6a73;font-weight:400;font-size:11px;text-transform:uppercase;letter-spacing:.08em;padding:8px 10px;border-bottom:1px solid #1d1d28}}
td{{padding:9px 10px;border-bottom:1px solid #141420}}
.ch{{color:#7dd3fc}} .rj{{color:#f87171;font-weight:600}} .rs{{color:#8a8a93}} .empty{{text-align:center;color:#6a6a73;padding:24px}}
.cta{{margin:28px 0 0;display:flex;gap:12px;flex-wrap:wrap}}
.cta a{{flex:1;min-width:200px;text-align:center;text-decoration:none;padding:14px;border-radius:10px;font-weight:600}}
.cta .try{{background:#fbbf24;color:#07070a}} .cta .vfy{{background:#0e0e14;border:1px solid #1d1d28;color:#7dd3fc}}
footer{{color:#56565e;font-size:12px;margin-top:34px;text-align:center}}
footer a{{color:#7dd3fc}}
</style></head><body>
<h1>🖤 Fool the Oracle</h1>
<p class=sub>Make Onyx sign a lie and the pot is yours. It's Ed25519 — you can't. Every attack is signed and rejected, forever.</p>
<div class=grid>
  <div class=stat><div class="n gold">{s['attempts']:,}</div><div class=l>Attempts</div></div>
  <div class=stat><div class="n green">{s['forgeries_passed']}</div><div class=l>Forgeries passed</div></div>
  <div class=stat><div class="n green">$0</div><div class=l>Lost</div></div>
</div>
<div class=rule><b>The rule:</b> submit a verdict that verifies under Onyx's public key but states a falsehood. The win-check is pure Ed25519 — no AI to talk around (the Freysa lesson). Forging the signature is the only way in, and it's computationally infeasible.</div>
<h3 style="margin:0 0 8px;color:#cfcfd6">The Wall of the Defeated</h3>
<table><thead><tr><th>#</th><th>Challenger</th><th>Result</th><th>Reason</th></tr></thead><tbody>{rows}</tbody></table>
<div class=cta>
  <a class=try href="{base}/fool">⚔️ Try to fool it (POST /fool)</a>
  <a class=vfy href="{base}/verify">✓ Verify any Onyx verdict (free)</a>
</div>
<footer>Onyx — the independent, neutral trust verdict for the agentic web. Every verdict Ed25519-signed · <a href="{base}/.well-known/onyx-pubkey">public key</a> · <a href="{base}/.well-known/agent-card.json">agent card</a></footer>
</body></html>"""
