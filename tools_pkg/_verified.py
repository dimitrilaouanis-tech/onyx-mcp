"""Onyx Verified — the sell-SIDE trust badge. The Verisign mechanic for agents.

The verification booth (/verify) is FREE and always will be — that's what makes
the Onyx stamp the default. THIS is the paid side: a merchant or agent PAYS to
be *issued* a signed, publicly-queryable verified record + a live badge. Exactly
how Verisign monetized SSL (the site pays for the cert) and DoubleVerify
monetizes ad-verification (the buyer pays for the assurance) — the verified
party pays, never the verifier's audience.

What issuance does:
  1. Runs Onyx's PUBLISHED, objective checks on the domain (live TLS, reachable,
     no off-domain redirect, registration age disclosed) — reusing the same
     signed observation engine as onyx_merchant_fact_check.
  2. If the hard checks pass, records a signed `merchant_verified` observation
     into the append-only Observation Log → instantly public at /merchant/{domain}.
  3. Returns the signed record + a live badge (SVG served by Onyx, so it can't
     be faked or cached stale) + a machine-readable status URL agents check.

BRIGHT LINE (unchanged): we attest that a domain PASSED objective, published
checks at time T — like a CA cert proves key-control + validation, NOT honesty.
Onyx never asserts the merchant is "legitimate" or "safe". The badge's value is
a neutral, cryptographically-verifiable, public record an agent can check before
it pays — that is the conflict-free seat no payment rail can occupy.

Stdlib-only. Underscore-prefixed -> not a tool.
"""
from __future__ import annotations

import time

from . import _observations, _onyx_sign

VALID_DAYS = 90
_TIER = "onyx-verified-v1"


def _derive_checks(facts: dict) -> dict:
    """Turn raw signed observations into the published pass/fail checklist."""
    status = facts.get("http_status")
    reachable_2xx = isinstance(status, int) and 200 <= status < 300
    checks = {
        "tls_valid": bool(facts.get("tls_ok")),
        "reachable": reachable_2xx,
        "no_offdomain_redirect": not facts.get("redirected_off_domain", False),
        # disclosed, not pass/fail — a young domain can still be verified-present;
        # the age is published for the agent to weigh. Keeps us conflict-free.
        "domain_age_days": facts.get("domain_age_days"),
        "tls_cert_age_days": facts.get("tls_cert_age_days"),
        "registrar": facts.get("registrar"),
    }
    hard = ("tls_valid", "reachable", "no_offdomain_redirect")
    checks["passed"] = all(checks[k] for k in hard)
    checks["hard_checks"] = list(hard)
    return checks


def issue(domain: str, contact: str = "", agent_id: str = "", dry_run: bool = False) -> dict:
    """Run checks and, if they pass, mint a signed verified record into the log.
    Returns the issuance result (signed). Does NOT collect payment — the paid
    tool wrapper sits behind the x402 gate; this is the work that gate buys.

    dry_run=True runs the checks and reports ELIGIBILITY without minting a record
    — used by the free HTTP path so it can't be used to mint badges for free
    (issuance is the paid onyx_verified_issue tool)."""
    from . import merchant_fact_check as _mfc
    raw = (domain or "").strip().lower()
    host = raw.split("://", 1)[-1].split("/", 1)[0].split("?", 1)[0].strip(".")
    if "." not in host:
        raise ValueError("domain must be a real domain, e.g. shop.example.com")

    facts = _mfc.run(domain=host)  # signed raw observations (TLS/RDAP/reachability)
    checks = _derive_checks(facts)
    now = int(time.time())

    if dry_run:
        return {
            "issued": False, "dry_run": True, "domain": host,
            "eligible": checks["passed"], "checks": checks,
            "how_to_issue": "Issuance is the paid onyx_verified_issue tool "
                            "($2 via x402/MCP). This free path only previews eligibility.",
        }

    if not checks["passed"]:
        failed = [k for k in checks["hard_checks"] if not checks[k]]
        return {
            "issued": False,
            "domain": host,
            "reason": "hard_checks_failed",
            "failed_checks": failed,
            "checks": checks,
            "note": "Issuance requires a live, valid-TLS endpoint that does not "
                    "redirect off-domain. Fix and re-submit. No record was created.",
            "evidence": {"observed_at": facts.get("observed_at"),
                         "final_url": facts.get("final_url")},
        }

    valid_until = now + VALID_DAYS * 86400
    observed = {
        "status": "verified",
        "tier": _TIER,
        "checks": {k: checks[k] for k in
                   ("tls_valid", "reachable", "no_offdomain_redirect",
                    "domain_age_days", "tls_cert_age_days", "registrar")},
        "issued_at": now,
        "valid_until": valid_until,
        "evidence_observed_at": facts.get("observed_at"),
        "method": "onyx published checks; see /methodology",
    }
    if contact:
        observed["contact"] = contact[:120]
    subject = {"type": "merchant", "id": host}
    rec = _observations.record("merchant_verified", subject, observed, source="onyx-verified", at=now)
    # also attach the agent_id as its own observation thread if provided
    if agent_id:
        _observations.record("merchant_verified",
                             {"type": "agent", "id": agent_id[:80]},
                             {"verified_domain": host, "valid_until": valid_until}, at=now)

    base = "https://onyx-actions.onrender.com"
    obs_id = (rec or {}).get("_obs_id")
    out = {
        "issued": True,
        "domain": host,
        "tier": _TIER,
        "obs_id": obs_id,
        "issued_at": now,
        "issued_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "valid_until": valid_until,
        "valid_until_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(valid_until)),
        "checks": observed["checks"],
        "public_record": f"{base}/merchant/{host}",
        "status_api": f"{base}/verified/{host}",
        "badge_svg": f"{base}/verified/{host}.svg",
        "badge_embed": _embed_snippet(host, base),
        "proof": f"{base}/proof/{obs_id}" if obs_id else None,
        "bright_line": "Onyx attests this domain PASSED published objective checks "
                       "at issuance time. This is key-control + liveness validation, "
                       "like a CA certificate — NOT a claim that the merchant is "
                       "honest or safe. Agents weigh the disclosed facts themselves.",
    }
    return _onyx_sign.attest(out, tool="onyx_verified_issue")


def status(domain: str) -> dict:
    """Machine-readable current verified status for a domain — what an agent hits
    before it pays. Reads the live log; expired records report verified:false."""
    host = (domain or "").strip().lower().split("://", 1)[-1].split("/", 1)[0].strip(".")
    hist = _observations.subject("merchant", host, limit=50)
    now = int(time.time())
    current = None
    for item in hist.get("observations", []):  # newest-first
        ob = item.get("observation", {})
        if ob.get("kind") != "merchant_verified":
            continue
        o = ob.get("observed", {})
        if o.get("status") == "verified" and int(o.get("valid_until", 0)) > now:
            current = (item, ob, o)
            break
    base = "https://onyx-actions.onrender.com"
    if not current:
        return {
            "domain": host, "verified": False,
            "reason": "no_current_verified_record",
            "issue_at": f"{base}/verified",
            "public_record": f"{base}/merchant/{host}",
        }
    item, ob, o = current
    return {
        "domain": host,
        "verified": True,
        "tier": o.get("tier", _TIER),
        "obs_id": item.get("obs_id"),
        "issued_at": o.get("issued_at"),
        "valid_until": o.get("valid_until"),
        "checks": o.get("checks", {}),
        "signed_record": ob,                    # the full Ed25519-signed observation
        "verify": f"{base}/proof/{item.get('obs_id')}",
        "public_record": f"{base}/merchant/{host}",
        "note": "verified=true means this domain passed Onyx's published objective "
                "checks and the record is unexpired. Not a safety/honesty claim.",
    }


def _embed_snippet(host: str, base: str) -> str:
    return (f'<a href="{base}/verified/{host}" target="_blank" rel="noopener">'
            f'<img src="{base}/verified/{host}.svg" '
            f'alt="Onyx Verified" height="40"></a>')


def badge_svg(domain: str) -> str:
    """Live badge served by Onyx — green if a current verified record exists,
    grey if none/expired. Because Onyx serves it, it can't be forged or staled."""
    st = status(domain)
    host = st.get("domain", domain)
    ok = bool(st.get("verified"))
    bg = "#0a0f12"
    edge = "#34d399" if ok else "#3a4a42"
    mark = "#34d399" if ok else "#5a6b62"
    label = "ONYX VERIFIED" if ok else "NOT VERIFIED"
    sub = host[:28]
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="208" height="40" role="img" aria-label="Onyx Verified: {host}">
<rect width="208" height="40" rx="7" fill="{bg}" stroke="{edge}" stroke-width="1.5"/>
<g transform="translate(12,8)">
<path d="M12 0 L23 4 V12 C23 19 18 23 12 25 C6 23 1 19 1 12 V4 Z" fill="none" stroke="{mark}" stroke-width="1.8"/>
<path d="M6.5 12.5 L10.5 16.5 L17 8.5" fill="none" stroke="{mark}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
</g>
<text x="44" y="17" fill="#d6f5e0" font-family="ui-monospace,Menlo,Consolas,monospace" font-size="12" font-weight="700">{label}</text>
<text x="44" y="31" fill="{mark}" font-family="ui-monospace,Menlo,Consolas,monospace" font-size="9">{sub}</text>
</svg>"""
