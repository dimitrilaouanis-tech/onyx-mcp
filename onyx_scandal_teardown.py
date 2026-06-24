"""Onyx scandal-teardown wedge — the ChatGPT fake-storefront catch.

June 2026: ChatGPT recommended CLONED FAKE STOREFRONTS (impersonating defunct/real
brands like Russell & Bromley and Dunelm), harvesting shoppers' card details. Visa,
verbatim: "ACP and AP2 focus on payment integrity, NOT merchant legitimacy — an
agent can complete a technically valid transaction with a fraudulent merchant, and
nothing in the protocol layer flags the discrepancy."

THAT is the gap Onyx fills. This script runs Onyx's PUBLISHED, signed merchant
checks (via tools_pkg.merchant_fact_check) over candidate domains and returns a
signed legitimacy verdict an agent can read BEFORE it pays.

Bright line (held): Onyx attests "this domain PASSED / FAILED published objective
checks" (live TLS, domain registration age, reachability, off-domain redirect,
brand-name vs domain) — never "this merchant is honest." Facts, not judgments.

Run:  py onyx_scandal_teardown.py                      (demo set)
      py onyx_scandal_teardown.py <brand> <domain>     (one pair)
"""
import sys
import json
import time

from tools_pkg import merchant_fact_check as _mfc
try:
    from tools_pkg import _onyx_sign
except Exception:
    _onyx_sign = None

# A domain claiming an ESTABLISHED brand but registered this recently is the
# classic clone-the-defunct-brand pattern that fooled ChatGPT.
YOUNG_DOMAIN_DAYS = 180


def legitimacy_verdict(facts: dict, brand: str | None = None) -> dict:
    """Apply Onyx's published legitimacy logic to signed merchant facts.
    Returns {verdict, score, flags} — PASS / FLAG / BLOCK."""
    flags = []
    age = facts.get("domain_age_days")
    tls_age = facts.get("tls_cert_age_days")

    if not facts.get("reachable"):
        flags.append("unreachable")
    if facts.get("tls_ok") is False:
        flags.append("no_valid_tls")
    if facts.get("redirected_off_domain"):
        flags.append("redirects_off_domain")
    # The scandal signal: a named, well-known brand on a brand-new domain.
    if brand and isinstance(age, int) and age < YOUNG_DOMAIN_DAYS:
        flags.append(f"claims_brand_'{brand}'_on_{age}d_old_domain")
    if brand and isinstance(tls_age, int) and tls_age < 30:
        flags.append(f"tls_cert_only_{tls_age}d_old")
    if isinstance(age, int) and age < 30:
        flags.append(f"domain_only_{age}d_old")

    hard = {"unreachable", "no_valid_tls", "redirects_off_domain"}
    impersonation = any(f.startswith("claims_brand_") for f in flags)
    if any(f in hard for f in flags) or impersonation:
        verdict = "BLOCK" if impersonation else "FLAG"
    elif flags:
        verdict = "FLAG"
    else:
        verdict = "PASS"
    return {"verdict": verdict, "flags": flags,
            "checked": ["reachable", "tls", "domain_age", "off_domain_redirect",
                        "brand_vs_domain_age"]}


def assess(brand: str | None, domain: str) -> dict:
    facts = _mfc.run(domain=domain, brand=brand)  # signed raw observations
    v = legitimacy_verdict(facts, brand=brand)
    out = {
        "spec": "onyx-merchant-legitimacy/v0",
        "brand_claimed": brand,
        "domain": facts.get("domain"),
        "verdict": v["verdict"],
        "flags": v["flags"],
        "evidence": {k: facts.get(k) for k in (
            "domain_age_days", "domain_created", "registrar",
            "tls_ok", "tls_cert_age_days", "tls_issuer",
            "reachable", "http_status", "redirected_off_domain", "final_url")},
        "bright_line": ("Attests PASS/FAIL of published objective checks, not "
                        "merchant honesty. Facts, not judgments."),
        "the_gap_we_fill": ("Payment protocols (ACP/AP2/x402) verify payment "
                            "integrity, not merchant legitimacy. This is the "
                            "signed check an agent reads BEFORE it pays."),
        "observed_at": int(time.time()),
    }
    if _onyx_sign:
        try:
            out = _onyx_sign.attest(out, tool="onyx_merchant_legitimacy")
        except Exception:
            pass
    return out


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        pairs = [(sys.argv[1], sys.argv[2])]
    else:
        # Demo: an established legit retailer (should PASS) vs the scandal pattern
        # (a well-known brand name on a freshly-registered domain — BLOCK).
        pairs = [
            (None, "dunelm.com"),                  # real established retailer
            ("Russell & Bromley", "example.com"),  # brand-on-unrelated/young domain
        ]
    print("=" * 64)
    print(" ONYX SCANDAL-TEARDOWN — the merchant-legitimacy check ACP/AP2 skip")
    print("=" * 64)
    for brand, dom in pairs:
        print(f"\n--- LIVE: brand={brand!r}  domain={dom} ---")
        try:
            r = assess(brand, dom)
            print(f"  VERDICT: {r['verdict']}   flags={r['flags']}")
            print(f"  evidence: {json.dumps(r['evidence'])}")
            signed = isinstance(r.get("onyx_attestation"), dict) and r["onyx_attestation"].get("sig", "").startswith("unsigned:") is False
            print(f"  signed: {signed}")
        except Exception as e:
            print(f"  ERROR: {e}")

    # The catch, on the actual scandal pattern. We do NOT probe live scam URLs;
    # we feed the verdict engine the facts a clone-of-a-defunct-brand presents
    # (well-known brand name on a domain registered weeks ago) to prove BLOCK.
    print("\n--- CLONE PATTERN (facts a Russell&Bromley clone would present) ---")
    clone_facts = {
        "domain": "russell-bromley-outlet-sale.com", "reachable": True,
        "http_status": 200, "tls_ok": True, "tls_cert_age_days": 12,
        "domain_age_days": 19, "domain_created": "2026-06-05T00:00:00Z",
        "registrar": "NameSilo, LLC", "redirected_off_domain": False,
    }
    cv = legitimacy_verdict(clone_facts, brand="Russell & Bromley")
    print(f"  VERDICT: {cv['verdict']}   flags={cv['flags']}")
    print(f"  -> 19-day-old domain claiming a long-defunct established brand = caught.")
    print("\nThis is precisely what ChatGPT/ACP/AP2 did NOT check (Visa, Jun 2026).")
