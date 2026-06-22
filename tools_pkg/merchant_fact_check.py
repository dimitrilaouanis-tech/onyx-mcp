"""Merchant fact oracle — signed raw observations about a storefront domain.

The why-now: the 2026 wave of AI-recommended cloned storefronts (data-poisoned
fake shops surfacing inside assistant shopping results, documented by consumer
scam-checkers and threat-intel teams) showed that no assistant platform runs an
independent merchant-fact check before recommending a checkout. Shopping agents
act on whatever the page claims about itself.

This tool returns the observable facts an agent needs BEFORE checkout, signed:

  - domain_created / domain_age_days / registrar / rdap status   (RDAP)
  - tls_cert_issued / tls_cert_age_days / tls_issuer             (live TLS)
  - reachable / http_status / final_url / redirected_off_domain  (live fetch)
  - brand_similarity 0..1 + lookalike_tokens                     (vs caller's brand)
  - observed_price + deviation_pct vs caller's expected_price    (page extraction)

Bright line — SIGN FACTS, NOT JUDGMENTS: every field is a raw observation with
its method disclosed. Onyx does NOT assert whether the merchant is legitimate,
safe, or fraudulent. A 9-day-old domain is a fact; what it means is the
caller's decision. The signature proves the observation is ours and untampered,
not that the merchant is good or bad.
"""
from __future__ import annotations

import difflib
import re
import socket
import ssl
import time
import urllib.error

from . import retail_price_check as _rpc
from . import whois_lookup as _whois
from . import _onyx_sign

NAME = "onyx_merchant_fact_check"
PRICE_USDC = "0.25"
TIER = "premium"
DESCRIPTION = (
    "Pre-checkout merchant fact oracle. Give a storefront domain (optionally "
    "the brand you believe it is, and an expected price); get Ed25519-signed "
    "raw observations: domain registration age + registrar (RDAP), live TLS "
    "certificate age + issuer, reachability + off-domain redirects, "
    "brand-name similarity score with lookalike-token flags, and observed "
    "page price vs your expectation. Facts only, method disclosed per field — "
    "Onyx never asserts 'legit' or 'scam'; the signature proves the "
    "observation is genuine and untampered."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "domain": {
            "type": "string",
            "description": "Storefront domain or URL, e.g. brand-outlet-sale.com or https://shop.example.com/p/1",
        },
        "brand": {
            "type": "string",
            "description": "Optional brand name you believe this storefront represents (e.g. 'Russell & Bromley'). Enables the brand-similarity observation.",
        },
        "expected_price": {
            "type": "number",
            "description": "Optional price you were quoted/expect. If the page shows a price, the deviation percentage is reported as a fact.",
        },
        "product_url": {
            "type": "string",
            "description": "Optional specific product URL to extract the observed price from (defaults to the domain root).",
        },
    },
    "required": ["domain"],
}

_TIMEOUT = _rpc._TIMEOUT
_VANTAGE = "onyx-observer"

# Tokens that frequently appear in lookalike storefront registrations when
# combined with a third-party brand string. Reported as observations, never
# as a verdict.
_LOOKALIKE_TOKENS = (
    "outlet", "sale", "sales", "discount", "clearance", "official", "store",
    "shop", "online", "cheap", "factory", "uk", "usa", "deals",
)

_METHODOLOGY = {
    "domain_facts": "RDAP via rdap.org public mirror (registration/expiry events, registrar entity).",
    "tls_facts": "Live TLS handshake to port 443; leaf certificate notBefore/issuer as presented.",
    "reachability": "HTTPS GET from the Onyx cloud vantage, redirects followed, final URL compared to input host.",
    "brand_similarity": "difflib.SequenceMatcher ratio between the registrable label and the normalized brand string; token flags are substring matches.",
    "price_observation": "Same JSON-LD -> meta -> text extraction chain as onyx_retail_price_check.",
    "bright_line": "Raw observations only. Onyx does not assert merchant legitimacy; interpretation is the caller's.",
}


def _registrable_label(host: str) -> str:
    """'shop.brand-outlet.co.uk' -> 'brand-outlet' (best-effort, no PSL dep)."""
    parts = host.split(".")
    if len(parts) >= 3 and parts[-2] in ("co", "com", "org", "net", "ac", "gov") and len(parts[-1]) == 2:
        return parts[-3]
    return parts[-2] if len(parts) >= 2 else parts[0]


def _norm_brand(brand: str) -> str:
    return re.sub(r"[^a-z0-9]", "", brand.lower())


def _tls_facts(host: str) -> dict:
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=_TIMEOUT) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as tls:
                cert = tls.getpeercert()
        not_before = cert.get("notBefore")
        issued_ts = ssl.cert_time_to_seconds(not_before) if not_before else None
        issuer = dict(x[0] for x in cert.get("issuer", ()) if x)
        return {
            "tls_ok": True,
            "tls_cert_issued": not_before,
            "tls_cert_age_days": (int((time.time() - issued_ts) / 86400) if issued_ts else None),
            "tls_issuer": issuer.get("organizationName") or issuer.get("commonName"),
        }
    except (OSError, ssl.SSLError, ValueError) as e:
        return {"tls_ok": False, "tls_error": str(e)[:120]}


def _age_days(iso: str | None) -> int | None:
    if not iso:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", iso)
    if not m:
        return None
    created = time.mktime((int(m.group(1)), int(m.group(2)), int(m.group(3)), 0, 0, 0, 0, 0, -1))
    return max(0, int((time.time() - created) / 86400))


_CATEGORY_KEYWORDS = {
    "retail/ecommerce": ["add to cart", "checkout", "shop", "store", "product", "buy now", "shipping", "basket"],
    "finance/payments": ["bank", "invest", "trading", "loan", "payment", "wallet", "crypto", "insurance"],
    "data/api": ["api", "endpoint", "developer", "documentation", "rate limit", "json", "sdk"],
    "media/content": ["article", "news", "blog", "watch", "stream", "podcast", "video"],
    "travel/hospitality": ["hotel", "flight", "booking", "rental", "trip", "reservation"],
    "food/delivery": ["menu", "restaurant", "delivery", "order food", "takeaway"],
    "software/saas": ["pricing", "free trial", "dashboard", "sign up", "platform", "subscription"],
    "health/wellness": ["health", "clinic", "medical", "pharmacy", "wellness", "doctor"],
}


def _classify_category(doc: str, host: str) -> str:
    """Best-effort business category from JSON-LD @type + page-text keywords.
    An observation (disclosed method), not a judgment."""
    low = (doc or "")[:8000].lower()
    # JSON-LD @type is the strongest signal when present
    if '"@type"' in low:
        for t, c in (("store", "retail/ecommerce"), ("product", "retail/ecommerce"),
                     ("financialservice", "finance/payments"), ("restaurant", "food/delivery"),
                     ("hotel", "travel/hospitality"), ("newsarticle", "media/content"),
                     ("medicalorganization", "health/wellness"), ("softwareapplication", "software/saas")):
            if f'"@type":"{t}"' in low.replace(" ", "") or f'"@type": "{t}"' in low:
                return c
    scores = {c: sum(1 for k in ks if k in low) for c, ks in _CATEGORY_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "unclassified"


def run(domain: str = "", brand: str | None = None,
        expected_price: float | None = None, product_url: str | None = None,
        **_: object) -> dict:
    raw = (domain or "").strip()
    if not raw:
        raise ValueError("domain is required")
    host = raw.split("://", 1)[-1].split("/", 1)[0].split("?", 1)[0].lower().strip(".")
    if "." not in host:
        raise ValueError("domain must contain a dot, e.g. example.com")

    observed_at = int(time.time())
    facts: dict = {
        "ok": True,
        "domain": host,
        "observed_at": observed_at,
        "observed_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(observed_at)),
        "vantage": _VANTAGE,
    }

    # 1. Domain registration facts (RDAP)
    try:
        rd = _whois.run(host)
        if not rd.get("registered", False):
            # try the registrable apex if a subdomain was given
            apex = ".".join(host.split(".")[-2:])
            if apex != host:
                rd = _whois.run(apex)
                facts["rdap_queried"] = apex
        facts.update({
            "domain_registered": rd.get("registered"),
            "domain_created": rd.get("created"),
            "domain_age_days": _age_days(rd.get("created")),
            "domain_expires": rd.get("expires"),
            "registrar": rd.get("registrar"),
            "rdap_status": rd.get("status", []),
        })
    except Exception as e:  # RDAP outage is an observation gap, not a tool failure
        facts["rdap_error"] = str(e)[:120]

    # 2. Live TLS certificate facts
    facts.update(_tls_facts(host))

    # 3. Reachability + redirect facts
    fetch_url = (product_url or f"https://{host}/").strip()
    # SSRF-guarded + provenance-recording fetch (shared _provenance) — no
    # unguarded fallback path. The provenance (content sha256, fetched_at,
    # final URL) is signed with the rest, so the verdict commits to its source.
    from . import _provenance
    doc, prov = "", {}
    try:
        status, doc, prov = _provenance.safe_fetch(fetch_url, timeout=_TIMEOUT, max_bytes=_rpc._MAX_BYTES)
        final_url = prov.get("final_url", fetch_url)
    except _provenance.SSRFBlocked as e:
        facts["fetch_error"] = "ssrf_blocked:" + str(e)[:80]
        status, final_url = None, fetch_url
    except Exception as e:
        facts["fetch_error"] = str(e)[:120]
        status, final_url = None, fetch_url
    final_host = final_url.split("://", 1)[-1].split("/", 1)[0].lower()
    facts.update({
        "reachable": status is not None,
        "http_status": status,
        "final_url": final_url,
        "redirected_off_domain": bool(final_host and final_host != host and not final_host.endswith("." + host) and not host.endswith("." + final_host)),
        "provenance": prov,
    })

    # 4. Brand-similarity observation (only if the caller names a brand)
    if brand:
        label = _registrable_label(host)
        nb, nl = _norm_brand(brand), _norm_brand(label)
        ratio = difflib.SequenceMatcher(None, nb, nl).ratio() if nb and nl else 0.0
        tokens = [t for t in _LOOKALIKE_TOKENS if t in host.replace(nb, "")] if nb else []
        facts.update({
            "brand_input": brand,
            "registrable_label": label,
            "brand_similarity": round(ratio, 3),
            "brand_contained_in_domain": bool(nb and nb in _norm_brand(host)),
            "lookalike_tokens_present": tokens,
        })

    # 5. Observed price + deviation facts
    if doc:
        extracted = _rpc._from_jsonld(doc) or _rpc._from_meta(doc) or _rpc._from_text(doc) or {}
        price, currency = extracted.get("price"), extracted.get("currency")
        facts.update({
            "observed_price": price,
            "observed_currency": currency,
            "price_extraction_source": extracted.get("source"),
        })
        if expected_price and price:
            try:
                facts["price_deviation_pct"] = round((float(price) - float(expected_price)) / float(expected_price) * 100.0, 1)
            except (TypeError, ValueError, ZeroDivisionError):
                pass
        # 6. machine-consumability signals (for agent consumers)
        facts["has_structured_data"] = bool(_rpc._from_jsonld(doc))
        facts["business_category"] = _classify_category(doc, host)

    facts["disclaimer"] = (
        "Raw observations only, methods disclosed in _methodology. Onyx makes "
        "no claim that this merchant is legitimate, safe, or fraudulent — "
        "interpretation of these facts is the caller's responsibility. The "
        "Ed25519 signature proves this observation is genuine Onyx output and "
        "untampered; it does not vouch for the merchant."
    )
    facts["_methodology"] = _METHODOLOGY
    return _onyx_sign.attest(facts, tool=NAME)


run.__when_to_use__ = (
    "BEFORE a shopping/checkout agent transacts with an unfamiliar storefront, "
    "or whenever an assistant surfaces a merchant the user didn't type "
    "themselves. One call answers: how old is this domain, who registered it, "
    "how old is its TLS cert, does it redirect somewhere else, how close is "
    "its name to the brand it resembles, and does its price deviate from "
    "what was quoted — all as signed, verifiable facts."
)
run.__vs_alternatives__ = (
    "whois alone gives registration data with no brand/price/TLS context. "
    "Reputation databases return someone's opinion you can't verify. This "
    "returns the raw pre-checkout facts in one signed envelope — verify the "
    "signature with onyx_attestation_verify (free) and you know the "
    "observation is genuine without trusting any database."
)
run.__example_request__ = {
    "domain": "brand-outlet-sale.com",
    "brand": "Brand",
    "expected_price": 49.99,
}
run.__example_response__ = {
    "ok": True,
    "domain": "brand-outlet-sale.com",
    "domain_age_days": 9,
    "registrar": "Example Registrar LLC",
    "tls_cert_age_days": 8,
    "brand_similarity": 0.62,
    "lookalike_tokens_present": ["outlet", "sale"],
    "observed_price": 24.99,
    "price_deviation_pct": -50.0,
    "disclaimer": "Raw observations only...",
}
