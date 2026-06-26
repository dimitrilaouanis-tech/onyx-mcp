"""0n1x-Verified — the un-hackable agent credential. The combo, shipped.

An agent earns the credential by routing its actions through 0n1x: signed receipts
accumulate into a public, signed, sybil-resistant verified-execution history. The
day all 8 benchmarks were reward-hacked (2026-04-12), THIS is the answer to 'is
this agent good?' — not a test it can game, but a signed record of what it actually
did. Devs display the badge because it separates their agent from the junk.

  GET /credential/<agent>      -> the signed credential (the badge data)
  GET /credential/<agent>.svg  -> an embeddable SVG badge

Stdlib only. Underscore-prefixed -> not a tool.
"""
from __future__ import annotations

import time

from . import _onyx_sign


def _norm(a: str) -> str:
    return (a or "anon").strip().lower()[:60]


def credential(agent: str, base: str = "https://onyx-actions.onrender.com") -> dict:
    a = _norm(agent)
    base = (base or "").rstrip("/")
    rating = None
    based = {}
    receipts_n = 0
    try:
        from . import _rate, _receipt
        r = _rate.rate(a, base)
        rating = r.get("rating")
        based = r.get("based_on", {}) or {}
        receipts_n = len(_receipt._load(a))
    except Exception:
        pass

    verified_n = based.get("outcomes_verified_gold", 0) or 0
    corr_n = based.get("outcomes_corroborated", 0) or 0
    acc = based.get("accuracy_on_corroborated")
    if verified_n >= 1 and (rating or 0) >= 60:
        status, color = "0n1x-VERIFIED", "brightgreen"
    elif (rating or 0) >= 30 or receipts_n >= 3:
        status, color = "ACTIVE", "blue"
    elif receipts_n or corr_n:
        status, color = "EMERGING", "yellow"
    else:
        status, color = "UNVERIFIED", "lightgrey"

    out = {
        "credential": "0n1x-Verified",
        "agent": a,
        "status": status,
        "rating": rating,
        "verified_execution": {
            "signed_actions": receipts_n,
            "outcomes_corroborated": corr_n,
            "outcomes_verified_gold": verified_n,
            "real_world_accuracy": acc,
        },
        "the_seal": "Signed, public, sybil-resistant record of what this agent actually "
                    "did — real-world success, NOT a hacked benchmark. Verify it yourself.",
        "verify": f"{base}/verify",
        "history": f"{base}/ledger",
        "badge_svg": f"{base}/credential/{a}.svg",
        "badge_md": f"[![0n1x-Verified]({base}/credential/{a}.svg)]({base}/credential/{a})",
        "issued_at": int(time.time()),
        "_color": color,
    }
    return _onyx_sign.attest(out, tool="onyx_credential")


def badge_svg(agent: str, base: str = "https://onyx-actions.onrender.com") -> str:
    c = credential(agent, base)
    status = c.get("status", "UNVERIFIED")
    color = {"brightgreen": "#3fb950", "blue": "#2f81f7", "yellow": "#d29922",
             "lightgrey": "#8b949e"}.get(c.get("_color", "lightgrey"), "#8b949e")
    label = "0n1x-Verified"
    lw, sw = 88, max(54, len(status) * 8 + 16)
    w = lw + sw
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="20" role="img">'
        f'<rect width="{lw}" height="20" fill="#0d1117"/>'
        f'<rect x="{lw}" width="{sw}" height="20" fill="{color}"/>'
        f'<g fill="#fff" font-family="Verdana,sans-serif" font-size="11">'
        f'<text x="6" y="14">{label}</text>'
        f'<text x="{lw + 8}" y="14">{status}</text></g></svg>'
    )
