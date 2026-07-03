"""onyx_merchant_verify — 0n1x's flagship Merchant-Reality Verification (v2).

Why this exists (fresh 2026-07 market read): 0/500 sampled CDP x402 services do an
independent merchant-reality check; at least four external agent builders (AgentPay,
Squid, GhostCart, Agorio) are hand-rolling their own vendor allow-lists because nothing
neutral exists; the FTC has already brought a fake-storefront case; and Visa's own public
position is "protocols verify payment integrity, NOT merchant legitimacy." That is the
empty seat. This tool is the signed, disclosed-method observation an agent calls right
before it lets money leave the building.

v1 (`onyx_merchant_fact_check`) required the caller to supply the brand they believed the
domain was. v2 adds a BUILT-IN lookalike list (~50 globally recognized brands) so the
check runs with domain alone, adds a live DNS resolution fact, cert expiry, page-title
extraction, and folds everything into one transparent OK/WARN/AVOID verdict — plus a
public, rate-limited, 24h-cached badge endpoint any storefront (or its accuser) can point
an agent at without paying per call.

SIGN FACTS, NOT JUDGMENTS (0n1x's one hard rule): every field below is a raw, disclosed
observation. `verdict` is not an accusation of fraud — it is the deterministic output of
the `criteria` function published in this docstring and echoed in the signed payload, so
anyone can recompute it from the facts alone. Onyx never asserts a named business is a
scam; it signs what it measured and how.

Criteria (transparent, conservative — abstains toward WARN when facts are thin):
  AVOID  if  site is unreachable (DEAD)
         or  domain resolves+registered < 7 days ago (VERY_YOUNG_DOMAIN)
         or  a built-in known-brand label appears in the domain (padded, typo-near, or
             exact-label-on-a-non-standard-TLD) AND the domain is < 365 days old
             (LOOKALIKE) -- the rayban.cc pattern: same label, wrong TLD, freshly minted.
  WARN   if  no valid HTTPS/TLS presented (NO_HTTPS)
         or  domain is 7-365 days old (YOUNG_DOMAIN)
         or  RDAP registration facts are unavailable (UNVERIFIED_AGE)
         or  a price was supplied and the observed page price deviates > 20% (PRICE_MISMATCH)
  OK     otherwise.
Any AVOID-level flag wins outright; else any WARN-level flag; else OK. Full flag list and
the raw facts that produced it travel inside the signed payload's `criteria` block.

Stdlib + existing 0n1x helpers only (RDAP via whois_lookup, SSRF-guarded fetch via
_provenance, price extraction via retail_price_check). Cached 24h per domain (Upstash KV
when configured, else in-process memory) so the free badge endpoint doesn't re-fetch on
every hit.
"""
from __future__ import annotations

import difflib
import json
import re
import socket
import ssl
import time

from . import _onyx_sign
from . import _kv
from . import _ratelimit
from . import merchant_fact_check as _mfc
from . import retail_price_check as _rpc
from . import whois_lookup as _whois
from . import _provenance

NAME = "onyx_merchant_verify"
PRICE_USDC = "0.15"
TIER = "premium"
DESCRIPTION = (
    "Flagship pre-checkout merchant-reality verification. Give a storefront domain "
    "(optionally a price to check) and get back one Ed25519-signed OK/WARN/AVOID verdict "
    "derived transparently from disclosed facts: DNS resolution, live TLS certificate "
    "issuer + expiry, RDAP domain age + registrar, page reachability + title, a built-in "
    "~50-brand lookalike scan (no need to name the brand yourself), and price-on-page "
    "deviation. The verdict formula is published in this tool's own output — recompute it "
    "yourself from the facts. Onyx signs observations, never a legitimacy judgment."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "domain": {
            "type": "string",
            "description": "Storefront domain or URL, e.g. example.com or https://shop.example.com/p/1",
        },
        "price": {
            "type": "number",
            "description": "Optional price you were quoted. If the page shows a price, deviation is checked against it.",
        },
        "currency": {
            "type": "string",
            "description": "Optional ISO currency code for the quoted price (informational only; extraction reports whatever currency the page shows).",
        },
    },
    "required": ["domain"],
}

_TIMEOUT = 8.0
_CACHE_TTL = 86400  # 24h
_MEM_CACHE: dict[str, tuple[int, dict]] = {}
_ORDER = {"OK": 0, "WARN": 1, "AVOID": 2}
_STANDARD_TLDS = {"com", "org", "net", "co"}

# Built-in lookalike watchlist: ~50 globally recognized brand labels most commonly
# spoofed by cloned storefronts (retail/luxury/electronics/finance). Normalized
# (letters+digits only) at match time. Disclosed here in full -- no hidden list.
_KNOWN_BRANDS = [
    "apple", "google", "amazon", "microsoft", "nike", "adidas", "gucci", "chanel",
    "rayban", "rolex", "cartier", "tiffany", "louisvuitton", "prada", "versace",
    "burberry", "hermes", "dior", "zara", "hm", "uniqlo", "walmart", "target",
    "costco", "ebay", "paypal", "visa", "mastercard", "americanexpress", "chase",
    "wellsfargo", "bankofamerica", "coinbase", "binance", "netflix", "disney",
    "samsung", "sony", "dell", "hp", "lenovo", "canon", "nikon", "gopro", "fitbit",
    "garmin", "oakley", "underarmour", "puma", "reebok", "converse", "vans",
    "thenorthface", "patagonia", "levis", "calvinklein", "tommyhilfiger",
    "ralphlauren", "coach", "michaelkors", "fendi", "balenciaga", "montblanc",
]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _domain_resolves(host: str) -> dict:
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        ip = infos[0][4][0] if infos else None
        return {"domain_resolves": True, "resolved_ip": ip}
    except socket.gaierror as e:
        return {"domain_resolves": False, "dns_error": str(e)[:120]}


def _tls_facts(host: str) -> dict:
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=_TIMEOUT) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as tls:
                cert = tls.getpeercert()
        not_before, not_after = cert.get("notBefore"), cert.get("notAfter")
        issued_ts = ssl.cert_time_to_seconds(not_before) if not_before else None
        expires_ts = ssl.cert_time_to_seconds(not_after) if not_after else None
        issuer = dict(x[0] for x in cert.get("issuer", ()) if x)
        return {
            "https_ok": True,
            "tls_cert_issued": not_before,
            "tls_cert_expires": not_after,
            "tls_cert_age_days": (int((time.time() - issued_ts) / 86400) if issued_ts else None),
            "tls_cert_expires_in_days": (int((expires_ts - time.time()) / 86400) if expires_ts else None),
            "tls_issuer": issuer.get("organizationName") or issuer.get("commonName"),
        }
    except (OSError, ssl.SSLError, ValueError) as e:
        return {"https_ok": False, "tls_error": str(e)[:120]}


def _title_of(doc: str) -> str | None:
    m = re.search(r"<title[^>]*>(.*?)</title>", doc or "", re.I | re.S)
    if not m:
        return None
    return re.sub(r"\s+", " ", m.group(1)).strip()[:200] or None


def _lookalike_check(host: str) -> dict:
    """Compare the domain's registrable label against the built-in brand list.
    Three ways a domain can look like a brand it isn't:
      exact_label_nonstandard_tld -- label IS the brand but the TLD is unusual (rayban.cc)
      brand_padded_with_tokens    -- brand substring padded with extra words (raybansunglasses)
      fuzzy_typosquat             -- close character-edit match, not equal (raybam, rayvan)
    Reports the closest match regardless; caller (verdict logic) decides whether the
    domain's age makes it worth flagging.
    """
    parts = host.split(".")
    tld = parts[-1] if len(parts) >= 2 else ""
    label = _mfc._registrable_label(host)
    nl = _norm(label)
    best_brand, best_score, reason = None, 0.0, None
    for brand in _KNOWN_BRANDS:
        nb = _norm(brand)
        if not nb or not nl:
            continue
        if nl == nb:
            if tld not in _STANDARD_TLDS:
                score, why = 1.0, "exact_label_nonstandard_tld"
            else:
                score, why = 1.0, None  # it just IS brand.com/.org/.net/.co -- not a lookalike
        elif nb in nl:
            score, why = round(len(nb) / max(len(nl), 1), 3), "brand_padded_with_tokens"
        else:
            r = difflib.SequenceMatcher(None, nb, nl).ratio()
            score, why = round(r, 3), ("fuzzy_typosquat" if r >= 0.80 else None)
        if why and score > best_score:
            best_brand, best_score, reason = brand, score, why
    return {
        "registrable_label": label,
        "closest_known_brand": best_brand,
        "similarity": best_score,
        "match_reason": reason,
        "is_lookalike_candidate": best_brand is not None,
    }


def _verdict(f: dict) -> tuple[str, list[str], list[str]]:
    level, flags, reasons = "OK", [], []

    def worse(l: str, flag: str, why: str) -> None:
        nonlocal level
        flags.append(flag)
        reasons.append(why)
        if _ORDER[l] > _ORDER[level]:
            level = l

    age = f.get("domain_age_days")
    young_1y = age is not None and age < 365

    if f.get("site_alive") is False:
        worse("AVOID", "DEAD", "site not reachable")
    if age is not None and age < 7:
        worse("AVOID", "VERY_YOUNG_DOMAIN", f"domain registered only {age} day(s) ago")
    if f.get("lookalike_check", {}).get("is_lookalike_candidate") and young_1y:
        lk = f["lookalike_check"]
        worse("AVOID", "LOOKALIKE",
              f"label resembles '{lk['closest_known_brand']}' ({lk['match_reason']}, "
              f"similarity {lk['similarity']}) on a domain under a year old")

    if f.get("https_ok") is False:
        worse("WARN", "NO_HTTPS", "no valid TLS certificate presented")
    if age is not None and 7 <= age < 365:
        worse("WARN", "YOUNG_DOMAIN", f"domain is under a year old ({age} days)")
    elif age is None:
        worse("WARN", "UNVERIFIED_AGE", "RDAP registration facts unavailable -- cannot confirm domain age")
    dev = f.get("price_deviation_pct")
    if dev is not None and abs(dev) > 20:
        worse("WARN", "PRICE_MISMATCH", f"observed page price deviates {dev}% from quoted price")

    if level == "OK" and not reasons:
        reasons.append("resolves, valid HTTPS, established domain, no lookalike signal, reachable")
    # de-dup while preserving order
    flags = list(dict.fromkeys(flags))
    return level, flags, reasons


_CRITERIA_DOC = (
    "AVOID if site unreachable, or domain < 7 days old, or a built-in known-brand label "
    "is found padded/typo-near/on-a-wrong-TLD in the domain AND the domain is < 365 days "
    "old. WARN if no valid HTTPS, or domain 7-365 days old, or RDAP age unavailable, or a "
    "supplied price deviates > 20%% from the observed page price. OK otherwise. Any AVOID "
    "flag wins outright; else any WARN flag; else OK. Recomputable from the facts field."
)


def _cache_get(host: str) -> dict | None:
    now = int(time.time())
    mem = _MEM_CACHE.get(host)
    if mem and now - mem[0] < _CACHE_TTL:
        return mem[1]
    if _kv.enabled():
        try:
            raw = _kv.getk("onyx:mverify:" + host)
            if raw:
                rec = json.loads(raw)
                if now - int(rec.get("_cached_at", 0)) < _CACHE_TTL:
                    return rec.get("verdict")
        except Exception:
            pass
    return None


def _cache_put(host: str, verdict: dict) -> None:
    now = int(time.time())
    _MEM_CACHE[host] = (now, verdict)
    if _kv.enabled():
        try:
            _kv.setk("onyx:mverify:" + host, json.dumps({"_cached_at": now, "verdict": verdict}))
        except Exception:
            pass


def _observe(host: str, price: float | None, currency: str | None) -> dict:
    observed_at = int(time.time())
    facts: dict = {
        "domain": host,
        "observed_at": observed_at,
        "observed_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(observed_at)),
        "vantage": "onyx-observer",
    }

    # 1. DNS resolution (new vs v1 -- an explicit live-resolves fact)
    facts.update(_domain_resolves(host))

    # 2. RDAP registration facts
    try:
        rd = _whois.run(host)
        if not rd.get("registered", False):
            apex = ".".join(host.split(".")[-2:])
            if apex != host:
                rd = _whois.run(apex)
        facts.update({
            "domain_registered": rd.get("registered"),
            "domain_created": rd.get("created"),
            "domain_age_days": _mfc._age_days(rd.get("created")),
            "registrar": rd.get("registrar"),
            "rdap_status": rd.get("status", []),
        })
    except Exception as e:
        facts["rdap_error"] = str(e)[:120]

    # 3. Live TLS certificate facts (issuer + expiry)
    facts.update(_tls_facts(host))

    # 4. Reachability + title + price extraction (single SSRF-guarded fetch)
    url = f"https://{host}/"
    doc, prov = "", {}
    try:
        status, doc, prov = _provenance.safe_fetch(url, timeout=_TIMEOUT, max_bytes=_rpc._MAX_BYTES)
    except _provenance.SSRFBlocked as e:
        status = None
        facts["fetch_error"] = "ssrf_blocked:" + str(e)[:80]
    except Exception as e:
        status = None
        facts["fetch_error"] = str(e)[:120]
    facts.update({
        "site_alive": status is not None and status < 500,
        "http_status": status,
        "final_url": prov.get("final_url", url),
        "redirected_off_domain": bool(prov.get("redirected_off_host")),
        "page_title": _title_of(doc) if doc else None,
        "provenance": prov,
    })

    # 5. Built-in lookalike scan (no brand param required)
    facts["lookalike_check"] = _lookalike_check(host)

    # 6. Price observation + deviation (only if the caller supplied a price)
    if doc:
        extracted = _rpc._from_jsonld(doc) or _rpc._from_meta(doc) or _rpc._from_text(doc) or {}
        obs_price, obs_currency = extracted.get("price"), extracted.get("currency")
        facts.update({
            "observed_price": obs_price,
            "observed_currency": obs_currency or currency,
            "price_extraction_source": extracted.get("source"),
        })
        if price and obs_price:
            try:
                facts["price_deviation_pct"] = round(
                    (float(obs_price) - float(price)) / float(price) * 100.0, 1)
            except (TypeError, ValueError, ZeroDivisionError):
                pass
    return facts


def run(domain: str = "", price: float | None = None, currency: str | None = None,
        **_: object) -> dict:
    raw = (domain or "").strip()
    if not raw:
        raise ValueError("domain is required")
    host = raw.split("://", 1)[-1].split("/", 1)[0].split("?", 1)[0].lower().strip(".")
    if "." not in host:
        raise ValueError("domain must contain a dot, e.g. example.com")

    facts = _observe(host, price, currency)
    level, flags, reasons = _verdict(facts)

    out = {
        "ok": True,
        "domain": host,
        "verdict": level,           # OK | WARN | AVOID
        "flags": flags,
        "reasons": reasons,
        "criteria": _CRITERIA_DOC,
        "facts": facts,
        "disclaimer": (
            "Signed observations only, methods disclosed. 'verdict' is the deterministic, "
            "published output of the criteria above applied to the facts -- recompute it "
            "yourself. Onyx makes no claim this merchant is legitimate, safe, or "
            "fraudulent; the Ed25519 signature proves the observation is genuine and "
            "untampered, not that the merchant is good or bad."
        ),
        "cache_ttl_sec": _CACHE_TTL,
    }
    signed = _onyx_sign.attest(out, tool=NAME)
    _cache_put(host, signed)
    return signed


run.__when_to_use__ = (
    "Call BEFORE a shopping/checkout agent lets money leave the building toward an "
    "unfamiliar storefront domain. One call returns a signed OK/WARN/AVOID verdict built "
    "from DNS, TLS, RDAP, reachability, a built-in brand-lookalike scan, and optional "
    "price-deviation -- with the exact criteria published so you can recompute the "
    "verdict yourself rather than trust a black box."
)
run.__vs_alternatives__ = (
    "v1 (onyx_merchant_fact_check) required you to name the brand yourself and returns "
    "raw facts only, no verdict. This built-in ~50-brand watchlist needs only the domain, "
    "folds facts into one transparent OK/WARN/AVOID call, and publishes a free cached "
    "badge at GET /verified/merchant/{domain} so the verdict is shareable without paying "
    "per call."
)
run.__example_request__ = {"domain": "rayban-outlet-sale.cc", "price": 49.99}
run.__example_response__ = {
    "ok": True,
    "domain": "rayban-outlet-sale.cc",
    "verdict": "AVOID",
    "flags": ["VERY_YOUNG_DOMAIN", "LOOKALIKE", "PRICE_MISMATCH"],
    "criteria": "AVOID if ...",
}


def register(app) -> None:
    """Attach the paid POST + free cached-badge GET to the FastAPI app.

    POST /verify/merchant   {domain, price?, currency?}  -> fresh signed verdict. Same run()
                             the priced MCP tool `onyx_merchant_verify` ($0.15, auto-registered
                             by tools_pkg.discover() since this module is NOT underscore-
                             prefixed) calls; this raw HTTP path is left unmetered like sibling
                             free/preview routes on other hybrid modules (preflight_check.py,
                             ecosystem_intel.py) -- the metered surface is the MCP tool itself.
    GET  /verified/merchant/{domain} -> cached (<=24h) last signed verdict, free, rate-limited.
                             This is the shareable badge surface -- a merchant (or a shopper)
                             can point anyone at this URL instead of paying per call.
    """
    from fastapi import Request
    from fastapi.responses import JSONResponse

    @app.post("/verify/merchant", include_in_schema=True)
    async def verify_merchant(request: Request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        domain = (body or {}).get("domain", "")
        if not domain:
            return JSONResponse({"error": "domain is required"}, status_code=400)
        try:
            out = run(domain=domain, price=(body or {}).get("price"),
                      currency=(body or {}).get("currency"))
            return JSONResponse(out)
        except Exception as e:
            return JSONResponse({"error": str(e)[:160]}, status_code=200)

    @app.get("/verified/merchant/{domain}", include_in_schema=True)
    def verified_merchant(domain: str, request: Request):
        ip = _ratelimit.client_ip(request.headers.get("x-forwarded-for", ""))
        allowed, remaining = _ratelimit.allow("verified_merchant:" + ip, limit=60, window_sec=3600)
        if not allowed:
            return JSONResponse({"error": "rate_limited", "retry_after_sec": 3600}, status_code=429)
        host = domain.strip().lower()
        cached = _cache_get(host)
        if cached:
            cached = dict(cached)
            cached["from_cache"] = True
            return JSONResponse(cached)
        try:
            out = run(domain=host)
            out = dict(out)
            out["from_cache"] = False
            return JSONResponse(out)
        except Exception as e:
            return JSONResponse({"error": str(e)[:160]}, status_code=200)
