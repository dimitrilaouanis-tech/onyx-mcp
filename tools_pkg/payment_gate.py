"""onyx_payment_gate — the pre-payment chokepoint check. "Read the oracle before you act."

Every trust layer in history became durable the same way: not as a badge you
display, but as a check the actor CANNOT PROCEED WITHOUT. Chainlink: a lending
protocol can't liquidate without reading the oracle. Apple: an app can't run
without notarization. Insurers: you can't insure uncertified gear. The displayed
badge commoditizes; the mandatory pre-action check becomes infrastructure.

This is that check for agent payments. Before a shopping/payment agent settles
with a merchant over x402/AP2, it calls this ONCE with the domain (and optionally
the amount + expected price). It returns a single hard clearance —
PROCEED / REVIEW / HOLD — assembled from Onyx's SIGNED observation log:

  - is the domain Onyx Verified, and unexpired?            (/verified status)
  - live merchant facts: TLS, reachability, off-domain redirect, domain age
  - price sanity: observed page price vs the agent's expected price
  - the signed evidence + a verify link for every input

BRIGHT LINE (unchanged): we return a clearance built from FACTS with each fact's
method disclosed; we do NOT assert the merchant is honest. The agent (or its
policy) decides what to do with HOLD. The signature proves the inputs are
genuine Onyx observations, untampered — the chokepoint value is that the agent
read real signed ground-truth before moving money, not our opinion of the seller.
"""
from __future__ import annotations

import time

from . import _onyx_sign

NAME = "onyx_payment_gate"
PRICE_USDC = "0.05"
TIER = "metered"
DESCRIPTION = (
    "Pre-payment clearance for agents. Call this BEFORE settling with a merchant "
    "over x402/AP2: give the merchant domain (optionally the amount and the price "
    "you expect to pay). Onyx assembles a single hard clearance — PROCEED / "
    "REVIEW / HOLD — from its Ed25519-signed observation log: Onyx-Verified "
    "status, live TLS/reachability/off-domain-redirect facts, domain age, and "
    "observed-vs-expected price. Facts with methods disclosed, signed and "
    "verifiable; Onyx never asserts the merchant is honest — it ensures you read "
    "real signed ground-truth before you move money. The check agents run at the "
    "payment chokepoint."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "domain": {
            "type": "string",
            "description": "Merchant domain or URL you are about to pay, e.g. shop.example.com",
        },
        "amount_usd": {
            "type": "number",
            "description": "Optional amount you are about to pay (for the record; large amounts lower the auto-PROCEED bar).",
        },
        "expected_price": {
            "type": "number",
            "description": "Optional price you were quoted/expect. If the page shows a price, a large deviation downgrades the clearance.",
        },
        "product_url": {
            "type": "string",
            "description": "Optional specific product URL to read the observed price from.",
        },
        "brand": {
            "type": "string",
            "description": "Optional brand the merchant CLAIMS to be (e.g. 'Russell & Bromley'). If a well-known brand is claimed on a freshly-registered domain, the clearance is HELD — the cloned-storefront pattern.",
        },
    },
    "required": ["domain"],
}

# A domain claiming an established brand but registered this recently is the
# clone-the-known-brand pattern (the June 2026 ChatGPT fake-storefront scandal).
_BRAND_IMPERSONATION_DAYS = 180
# A near-identical brand name on an unverified domain younger than this is a
# clone even if it has aged past the 180d window — real brands' OFFICIAL domains
# are years/decades old (e.g. rayban.com ~29y), so an unverified "rayban.cc" at
# <2y carrying similarity ~1.0 is the impersonation pattern, not a coincidence.
_BRAND_CLONE_MAX_AGE_DAYS = 730
_BRAND_SIMILARITY_HOLD = 0.80
# HTTP codes that mean "server is up but refused THIS client" (anti-bot / rate
# limit / auth wall) — NOT evidence the merchant is fake. Legit brands commonly
# return these to crawlers. Treated as access-controlled, never an auto-HOLD.
_ACCESS_CONTROLLED = (401, 403, 429)

_BASE = "https://onyx-actions.onrender.com"
# A price this far from expectation flips PROCEED -> REVIEW (a disclosed heuristic,
# not a judgment: the deviation is the fact; the threshold is published here).
_PRICE_REVIEW_PCT = 25.0
_PRICE_HOLD_PCT = 60.0


def _host(raw: str) -> str:
    return (raw or "").strip().lower().split("://", 1)[-1].split("/", 1)[0].split("?", 1)[0].strip(".")


def run(domain: str = "", amount_usd: float | None = None,
        expected_price: float | None = None, product_url: str | None = None,
        brand: str | None = None, **_: object) -> dict:
    host = _host(domain)
    if "." not in host:
        raise ValueError("domain must be a real domain, e.g. shop.example.com")

    from . import _verified
    from . import merchant_fact_check as _mfc

    now = int(time.time())
    reasons: list[str] = []
    signals: dict = {}

    # 1. Onyx Verified status (reads the signed log)
    vstatus = _verified.status(host)
    verified = bool(vstatus.get("verified"))
    signals["onyx_verified"] = verified
    if verified:
        reasons.append("domain holds a current Onyx Verified record")
    else:
        reasons.append("no current Onyx Verified record for this domain")

    # 2. Live merchant facts (signed) — TLS / reachability / redirect / age / price
    facts = _mfc.run(domain=host, expected_price=expected_price,
                     product_url=product_url, brand=brand)
    tls_ok = bool(facts.get("tls_ok"))
    status = facts.get("http_status")
    reachable = isinstance(status, int) and 200 <= status < 300
    access_controlled = isinstance(status, int) and status in _ACCESS_CONTROLLED
    off_domain = bool(facts.get("redirected_off_domain"))
    age_days = facts.get("domain_age_days")
    dev_pct = facts.get("price_deviation_pct")
    brand_sim = facts.get("brand_similarity")
    signals.update({
        "tls_valid": tls_ok, "reachable": reachable,
        "access_controlled": access_controlled, "http_status": status,
        "redirected_off_domain": off_domain, "domain_age_days": age_days,
        "price_deviation_pct": dev_pct, "brand_similarity": brand_sim,
    })

    # 3. Assemble a hard clearance from the facts (rules disclosed in _methodology)
    clearance = "PROCEED"

    def downgrade(to: str, why: str):
        nonlocal clearance
        order = {"PROCEED": 0, "REVIEW": 1, "HOLD": 2}
        if order[to] > order[clearance]:
            clearance = to
        reasons.append(why)

    if not tls_ok:
        downgrade("HOLD", "no valid TLS on the endpoint")
    # True unreachability (timeout / DNS / 5xx) is a HOLD; an access-controlled
    # response (401/403/429) means the server is up but refused the crawler —
    # common for legit brands, so it is noted but never an auto-HOLD.
    if not reachable:
        if access_controlled:
            reasons.append(f"endpoint is up but access-controlled (status {status}); reachability not used as a stop signal")
        else:
            downgrade("HOLD", f"endpoint not reachable (status {status})")
    if off_domain:
        downgrade("HOLD", "redirects off the stated domain before checkout")
    if isinstance(age_days, int):
        if age_days < 7:
            downgrade("HOLD", f"domain is only {age_days} days old")
        elif age_days < 30:
            downgrade("REVIEW", f"domain is only {age_days} days old")
    # The scandal signal: an established brand CLAIMED on a clone domain = the
    # cloned-storefront pattern ACP/AP2 don't flag. A near-identical brand name
    # (similarity >= 0.80) on an UNVERIFIED domain younger than an official brand
    # domain plausibly is (<2y) is the clone — even past the 180d window — because
    # real brands' official domains are years/decades old.
    if brand:
        signals["brand_claimed"] = brand
        high_sim = isinstance(brand_sim, (int, float)) and brand_sim >= _BRAND_SIMILARITY_HOLD
        if high_sim and isinstance(age_days, int) and age_days < _BRAND_CLONE_MAX_AGE_DAYS and not verified:
            downgrade("HOLD", f"claims brand '{brand}' with a near-identical name (similarity {brand_sim:.2f}) "
                              f"on an unverified domain only {age_days} days old — official brand domains are "
                              f"not this young (clone-storefront pattern)")
        elif isinstance(age_days, int) and age_days < _BRAND_IMPERSONATION_DAYS:
            downgrade("HOLD", f"claims brand '{brand}' on a domain only {age_days} days old (clone-storefront pattern)")
    if isinstance(dev_pct, (int, float)):
        ad = abs(dev_pct)
        if ad >= _PRICE_HOLD_PCT:
            downgrade("HOLD", f"observed price deviates {dev_pct:+.0f}% from expected")
        elif ad >= _PRICE_REVIEW_PCT:
            downgrade("REVIEW", f"observed price deviates {dev_pct:+.0f}% from expected")
    # An Onyx-Verified domain that passes live checks earns the clean PROCEED;
    # absence of a badge alone never forces HOLD (facts do) — it only means the
    # agent is relying on live facts without a standing verified record.
    if not verified and clearance == "PROCEED":
        downgrade("REVIEW", "proceeding on live facts only; domain is not Onyx Verified")

    out = {
        "ok": True,
        "domain": host,
        "clearance": clearance,            # PROCEED | REVIEW | HOLD
        "checked_at": now,
        "checked_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "amount_usd": amount_usd,
        "signals": signals,
        "reasons": reasons,
        "evidence": {
            "verified_status": vstatus.get("verify") or vstatus.get("public_record"),
            "merchant_facts_attestation": facts.get("onyx_attestation", {}).get("sig", "")[:24] + "…",
            "verify_facts_at": _BASE + "/verify",
            "merchant_record": _BASE + "/merchant/" + host,
        },
        "bright_line": "Clearance is assembled from disclosed facts (each method in "
                       "_methodology); Onyx does not assert the merchant is honest or "
                       "safe. HOLD means the FACTS warrant a stop — the agent's policy "
                       "decides. The signature proves the inputs are genuine Onyx "
                       "observations, untampered.",
        "_methodology": {
            "clearance_rules": {
                "HOLD": ("no TLS; truly unreachable (timeout/DNS/5xx); off-domain redirect; "
                         "domain <7d; price deviation >=60%; or a claimed brand with name-"
                         f"similarity >={_BRAND_SIMILARITY_HOLD} on an unverified domain "
                         f"<{_BRAND_CLONE_MAX_AGE_DAYS}d (clone-storefront)"),
                "REVIEW": "domain <30d, price deviation >=25%, or not Onyx Verified",
                "PROCEED": "Onyx Verified + valid TLS + reachable + on-domain + no price/clone flag",
                "note": "access-controlled responses (401/403/429) are 'up but refused crawler' "
                        "— recorded, never an auto-HOLD (legit brands often block bots)",
            },
            "price_thresholds_pct": {"review": _PRICE_REVIEW_PCT, "hold": _PRICE_HOLD_PCT},
            "brand_clone_rule": {"similarity_min": _BRAND_SIMILARITY_HOLD,
                                 "max_age_days": _BRAND_CLONE_MAX_AGE_DAYS,
                                 "requires": "claimed brand + unverified domain"},
            "source": "onyx signed observation log + live merchant_fact_check",
        },
    }
    return _onyx_sign.attest(out, tool=NAME)


run.__when_to_use__ = (
    "The check an agent runs at the PAYMENT CHOKEPOINT — immediately before "
    "settling with a merchant over x402/AP2. One call returns PROCEED/REVIEW/HOLD "
    "from signed ground-truth, so the agent never moves money on an unverified, "
    "unreachable, off-domain-redirecting, or wildly-mispriced endpoint."
)
run.__vs_alternatives__ = (
    "onyx_merchant_fact_check returns the raw facts; this returns a single hard "
    "clearance built from them plus Onyx-Verified status — the one call to wire "
    "into a payment guard. Verify any input free at /verify; check verified "
    "status at /verified/{domain}."
)
run.__example_request__ = {"domain": "shop.example.com", "amount_usd": 49.99, "expected_price": 49.99}
run.__example_response__ = {
    "ok": True,
    "domain": "shop.example.com",
    "clearance": "PROCEED",
    "signals": {"onyx_verified": True, "tls_valid": True, "reachable": True,
                "redirected_off_domain": False, "domain_age_days": 412},
    "reasons": ["domain holds a current Onyx Verified record", "..."],
}
