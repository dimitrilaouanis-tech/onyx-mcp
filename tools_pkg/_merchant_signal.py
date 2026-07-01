"""0n1x /merchant-signal — the dead-simple, signed pre-flight check.

The whole product in one endpoint (the bounty verdict: usage before standards). An agent,
about to pay a merchant, does ONE fetch:

    GET /merchant-signal?url=example.com[&brand=Russell%20%26%20Bromley]

and gets back a tiny SIGNED JSON: PROCEED / REVIEW / HOLD, the facts that drove it, and an
Ed25519 signature anyone can verify. No token, no account, no ceremony.

FACTS, NOT JUDGMENTS: the signal is a transparent, conservative function of OBSERVED facts
(domain age via RDAP, live TLS, reachability, off-domain redirects, brand look-alike). When
the facts are thin or unavailable, it ABSTAINS to REVIEW rather than guess — one wrong HOLD
or PROCEED erodes the cumulative trust that is the entire moat.
"""
from __future__ import annotations

import time

from . import merchant_fact_check as _mfc
from . import _onyx_sign

_ORDER = {"PROCEED": 0, "REVIEW": 1, "HOLD": 2}


def assess(f: dict) -> tuple[str, list]:
    """Derive a conservative signal from observed facts. Returns (signal, reasons)."""
    level, reasons = "PROCEED", []

    def worse(l: str, why: str) -> None:
        nonlocal level
        reasons.append(why)
        if _ORDER[l] > _ORDER[level]:
            level = l

    age = f.get("domain_age_days")
    established = age is not None and age >= 365   # a domain older than a year, seen before

    if f.get("reachable") is False:
        worse("HOLD", "site not reachable")
    if f.get("tls_ok") is False:
        # missing TLS is damning on a young domain, only a note on an old established one
        worse("HOLD" if not established else "REVIEW", "no valid TLS certificate presented")

    # off-domain redirect: classic phishing on a young domain; usually a benign platform/CDN
    # move for an established brand → never HOLD the real thing on this alone
    if f.get("redirected_off_domain"):
        worse("HOLD" if not established else "REVIEW", "redirects to a different domain")

    # brand look-alike is ONLY suspicious on a NON-established domain. High similarity on an
    # old domain means it IS the brand (that's the real Russell & Bromley), not a mimic.
    sim = f.get("brand_similarity")
    if sim is not None and 0.70 <= sim < 0.985 and not established:
        worse("HOLD", f"young domain mimics the named brand (similarity {sim:.2f})")

    if age is not None:
        if age < 30:
            worse("HOLD", f"domain registered only {age} days ago")
        elif age < 365:
            worse("REVIEW", f"domain is under a year old ({age} days)")
    elif f.get("domain_registered") is None or f.get("rdap_error"):
        worse("REVIEW", "registration facts unavailable — cannot confirm domain age")

    if level == "PROCEED" and not reasons:
        reasons.append("established domain, valid TLS, reachable, no look-alike")
    return level, reasons


def run(url: str = "", brand: str | None = None, **_: object) -> dict:
    facts = _mfc.run(domain=url, brand=brand)          # rich, RDAP+TLS+brand, already gathered
    inner = facts.get("onyx_attestation") and facts or facts   # facts dict carries the raw fields
    signal, why = assess(facts)
    out = {
        "merchant_signal": facts.get("domain", (url or "").strip()),
        "signal": signal,                               # PROCEED | REVIEW | HOLD
        "why": why,
        "facts": {
            "domain_age_days": facts.get("domain_age_days"),
            "tls_ok": facts.get("tls_ok"),
            "reachable": facts.get("reachable"),
            "redirected_off_domain": facts.get("redirected_off_domain"),
            "brand_similarity": facts.get("brand_similarity"),
        },
        "as_of": int(time.time()),
        "note": "Signed observed facts, not a guarantee. Abstains to REVIEW when facts are thin.",
    }
    return _onyx_sign.attest(out, tool="onyx_merchant_signal")


def register(app) -> None:
    from fastapi.responses import JSONResponse

    @app.get("/merchant-signal", include_in_schema=True)
    def merchant_signal(url: str = "", brand: str = ""):
        if not url:
            return JSONResponse({"error": "url is required, e.g. /merchant-signal?url=example.com"},
                                status_code=400)
        try:
            return JSONResponse(run(url=url, brand=brand or None))
        except Exception as e:
            return JSONResponse({"error": str(e)[:160]}, status_code=200)
