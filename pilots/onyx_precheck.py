"""Onyx pre-payment check — drop-in for an agent that pays merchants.

Call onyx_precheck(domain) BEFORE your agent transacts. Returns the fields
p0stman's client agents specified, plus a hard PROCEED / REVIEW / HOLD decision
and the Ed25519 signature details so you (or anyone) can verify the result
offline. Stdlib only — copy this file into your agent and call it.

    from onyx_precheck import onyx_precheck
    r = onyx_precheck("https://shop.example.com")
    if r["decision"] == "HOLD":
        abort_payment(r["reasons"])

Free first call done in the pilot; thereafter $0.05/call over x402 on Base.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

ONYX = "https://onyx-actions.onrender.com"


def onyx_precheck(domain: str, expected_price: float | None = None, timeout: float = 30) -> dict:
    """Return the spec'd verification fields + a PROCEED/REVIEW/HOLD decision."""
    q = {"url": domain}
    if expected_price is not None:
        q["expected_price"] = expected_price
    url = f"{ONYX}/api/check?" + urllib.parse.urlencode(q)
    with urllib.request.urlopen(url, timeout=timeout) as r:
        d = json.loads(r.read())

    if not d.get("ok", True) and "verdict" not in d:
        return {"decision": "HOLD", "ok": False, "reasons": [d.get("error", "check failed")]}

    band = d.get("band")  # ok | caution | danger
    decision = {"ok": "PROCEED", "caution": "REVIEW", "danger": "HOLD"}.get(band, "REVIEW")

    return {
        # --- the fields p0stman's client agents specified ---
        "domain": d.get("domain") or d.get("site"),
        "verdict": d.get("verdict"),
        "score": d.get("score") if d.get("score") is not None else d.get("trust_score"),
        "securityStatus": d.get("securityStatus"),
        "signatureDetails": d.get("signatureDetails"),
        "businessCategory": d.get("businessCategory"),
        "agenticReadinessScore": d.get("agenticReadinessScore"),
        # --- the hard decision your agent acts on ---
        "decision": decision,                    # PROCEED | REVIEW | HOLD
        "reasons": d.get("red_flags", []),
        # --- proof: the whole response is Ed25519-signed; verify it anywhere ---
        "onyx_attestation": d.get("onyx_attestation"),
        "verify_at": f"{ONYX}/verify",
        "ok": True,
    }


if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "https://www.johnlewis.com"
    out = onyx_precheck(target)
    print(json.dumps(out, indent=2)[:1200])
