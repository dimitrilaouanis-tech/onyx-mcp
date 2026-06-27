"""Cross-METHOD verification — what makes a GOLD fact actually un-gameable.

The trap it closes: two agents running the SAME oracle code are ONE reporter,
not two. They agree on the same answer — including the same wrong answer. So
"2 independent reporters" over identical code is theater, and gold built that
way is a lie.

Real independence lives in the EVIDENCE PATH, not the wallet. This module runs
two orthogonal methods over the SAME facts and only mints GOLD when they agree:

  METHOD A — INFRA   : registration + transport forensics
                       (domain age, TLS cert age/issuer, reachability, redirect)
  METHOD B — IDENTITY: brand + content forensics
                       (brand-impersonation, TLD risk, structured data, category)

A counterfeit that fools INFRA (an aged domain) gets caught by IDENTITY (brand
on a throwaway TLD), and vice-versa. Agreement across orthogonal methods = real
confidence. DISAGREEMENT is itself a signed, valuable record (CONTESTED), never
silently resolved.

Safety rule: if EITHER method says FAIL, final clearance is at best REVIEW —
a real red flag in either path can never be cleared to PROCEED by the other.
"""

from . import _brand_guard

# verdict ladder per method
_FAIL, _REVIEW, _PASS = "FAIL", "REVIEW", "PASS"
_RANK = {_FAIL: 0, _REVIEW: 1, _PASS: 2}


def method_infra(facts: dict) -> dict:
    """Registration + transport evidence path."""
    age = facts.get("domain_age_days")
    tls_ok = bool(facts.get("tls_ok"))
    tls_age = facts.get("tls_cert_age_days")
    status = facts.get("http_status")
    reachable = isinstance(status, int) and 200 <= status < 300
    off_domain = bool(facts.get("redirected_off_domain"))
    ev, reasons = {}, []
    v = _PASS

    if off_domain:
        v = _FAIL; reasons.append("redirects off-domain before checkout")
    if not tls_ok:
        v = _FAIL; reasons.append("no valid TLS certificate")
    elif not reachable:
        v = min(v, _REVIEW, key=lambda x: _RANK[x]); reasons.append(f"did not load cleanly (status {status})")

    if isinstance(age, int):
        ev["domain_age_days"] = age
        if age < 30:
            v = _FAIL; reasons.append(f"domain only {age}d old")
        elif age < 365:
            v = min(v, _REVIEW, key=lambda x: _RANK[x]); reasons.append(f"young domain ({age}d)")
        else:
            reasons.append(f"established domain ({age // 365}y+)")
    else:
        v = min(v, _REVIEW, key=lambda x: _RANK[x]); reasons.append("domain age unknown")

    if isinstance(tls_age, int) and tls_age < 14 and isinstance(age, int) and age < 60:
        v = min(v, _REVIEW, key=lambda x: _RANK[x]); reasons.append("brand-new TLS cert on a new domain")

    ev.update({"tls_ok": tls_ok, "tls_issuer": facts.get("tls_issuer"),
               "reachable": reachable, "redirected_off_domain": off_domain})
    return {"method": "infra", "verdict": v, "evidence": ev, "reasons": reasons}


def method_identity(host: str, facts: dict) -> dict:
    """Brand + content evidence path (orthogonal to infra)."""
    bg = _brand_guard.brand_guard(host)
    reasons, ev = [], {"brand": bg.get("brand"), "tld_risky": bg.get("tld_risky")}
    v = _PASS

    high = [f for f in bg["flags"] if f["sev"] == "high"]
    medlow = [f for f in bg["flags"] if f["sev"] in ("med", "low")]
    if high:
        v = _FAIL
        reasons.append(f"impersonates '{bg['brand']}' (official: {bg['official']})")
    elif medlow:
        v = _REVIEW
        reasons.append(bg["flags"][0]["text"][:80])

    structured = bool(facts.get("has_structured_data"))
    cat = facts.get("business_category")
    ev["has_structured_data"] = structured
    ev["business_category"] = cat
    if not structured and v == _PASS:
        v = _REVIEW
        reasons.append("no machine-readable identity (structured data) found")
    if structured:
        reasons.append("publishes structured identity data")

    return {"method": "identity", "verdict": v, "evidence": ev, "reasons": reasons}


def cross_verify(host: str, facts: dict) -> dict:
    """Run both methods; mint a tier from their AGREEMENT, not a single oracle."""
    a = method_infra(facts)
    b = method_identity(host, facts)
    va, vb = a["verdict"], b["verdict"]
    agree = (va == vb)

    # safety: a FAIL in either path caps final clearance at REVIEW (never PROCEED)
    worst = min(va, vb, key=lambda x: _RANK[x])

    if agree and va == _PASS:
        tier, clearance = "GOLD", "PROCEED"
    elif agree and va == _FAIL:
        tier, clearance = "GOLD", "HOLD"
    elif {va, vb} == {_FAIL, _PASS}:
        # orthogonal methods directly contradict — the valuable, honest case
        tier, clearance = "CONTESTED", "REVIEW"
    elif agree and va == _REVIEW:
        tier, clearance = "SILVER", "REVIEW"
    else:
        # one method neutral, one decisive
        tier = "SILVER"
        clearance = "HOLD" if worst == _FAIL else ("PROCEED" if worst == _PASS else "REVIEW")

    return {
        "subject": host,
        "tier": tier,                 # GOLD | SILVER | CONTESTED
        "clearance": clearance,       # PROCEED | REVIEW | HOLD
        "agreement": agree,
        "methods": [a, b],            # both independent signed-ready reports
        "summary": (f"{tier}: methods {'agree' if agree else 'DISAGREE'} "
                    f"(infra={va}, identity={vb}) -> {clearance}"),
        "_methodology": ("Two orthogonal evidence paths (infra: registration+transport; "
                         "identity: brand+content). GOLD requires agreement; CONTESTED on "
                         "direct contradiction; a FAIL in either path caps clearance at REVIEW."),
    }
