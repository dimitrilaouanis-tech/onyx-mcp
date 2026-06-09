"""Geo ground-truth oracle — what a real regional vantage actually sees.

Sibling of onyx_retail_price_check. Where that answers "what's the price,"
this answers "what does this URL actually resolve to *from a real in-region
vantage* — and does it differ from what a cloud agent would assume?"

A pure-software agent fetching from a datacenter IP sees the datacenter view:
it misses geo-redirects, region price/currency, "not available in your
country" walls, and 451/legal blocks. We observe from an independent Onyx
vantage and return a structured, timestamped result:

  - reachable / http_status / final_url (after redirects)
  - geo_redirected  (did the site bounce us to a region path/domain?)
  - geo_blocked     (legal / "not available in your country" wall?)
  - observed price + currency  (reused retail extraction)
  - language        (html lang)
  - divergence[]    (flags vs the caller's expectation)

Use before an agent assumes a price/availability/content is global when it is
actually region-gated. The divergence between a datacenter view and our
in-region view IS the product.

Bright line: observes a public page from a network vantage. Makes no claim
about persons or personhood.
"""
from __future__ import annotations

import re
import time
import urllib.error
import urllib.request

from . import retail_price_check as _rpc
from . import _onyx_sign

NAME = "onyx_geo_verify"
PRICE_USDC = "0.03"
TIER = "metered"
DESCRIPTION = (
    "Geo ground-truth oracle. Give a URL (optionally an expected price / "
    "currency / keyword); get what a real regional vantage actually "
    "sees — final URL after geo-redirects, region price + currency, "
    "geo-block / 'not available in your country' walls, page language — plus "
    "explicit divergence flags vs your expectation. Catches region-gating a "
    "datacenter-IP agent silently misses. Never guesses."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "url": {
            "type": "string",
            "description": "Full URL (http/https) to observe from the in-region vantage.",
        },
        "expect_currency": {
            "type": "string",
            "description": "Optional ISO currency you expect (e.g. 'USD'). If the in-region view shows a different currency, it's flagged as divergence.",
        },
        "expect_keyword": {
            "type": "string",
            "description": "Optional text you expect present on the page. If absent in the in-region view (e.g. geo-gated content), it's flagged.",
        },
    },
    "required": ["url"],
}

_UA = _rpc._UA
_TIMEOUT = _rpc._TIMEOUT
_MAX_BYTES = _rpc._MAX_BYTES

_BLOCK_PHRASES = (
    "not available in your country", "not available in your region",
    "unavailable in your country", "content is not available in your location",
    "this video is not available", "access denied in your country",
    "we don't ship to", "cannot be shipped to your", "restricted in your region",
    "blocked in your country", "geo-restricted", "geoblocked",
)
_VANTAGE = "onyx-observer"


def _fetch_with_final(url: str) -> tuple[int, str, str]:
    """Fetch following redirects; return (status, final_url, body)."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "text/html,application/xhtml+xml"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        raw = resp.read(_MAX_BYTES)
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.status, resp.geturl(), raw.decode(charset, "replace")


def _host(u: str) -> str:
    return u.split("://", 1)[-1].split("/", 1)[0].lower() if "://" in u else u


def _lang(doc: str) -> str | None:
    m = re.search(r'<html[^>]*\blang=["\']([a-zA-Z-]{2,8})["\']', doc, re.I)
    return m.group(1).lower() if m else None


def run(url: str = "", expect_currency: str | None = None,
        expect_keyword: str | None = None, **_: object) -> dict:
    url = (url or "").strip()
    if not url:
        raise ValueError("url is required")
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("url must be an http(s) URL")

    observed_at = int(time.time())
    try:
        status, final_url, doc = _fetch_with_final(url)
    except urllib.error.HTTPError as e:
        # 451 = legal block, 403 often geo — these ARE the observation, not a failure
        blocked = e.code in (451, 403, 401)
        return _onyx_sign.attest({
            "ok": True, "url": url, "http_status": e.code, "observed_at": observed_at,
            "reachable": False, "geo_blocked": blocked,
            "note": f"HTTP {e.code} from in-region vantage" + (" — likely geo/legal block" if blocked else ""),
            "vantage": _VANTAGE,
        }, tool=NAME)
    except (urllib.error.URLError, TimeoutError) as e:
        return {"ok": False, "error": "fetch_failed", "detail": str(e)[:200], "url": url,
                "observed_at": observed_at, "vantage": _VANTAGE}

    low = doc.lower()
    block_hit = next((p for p in _BLOCK_PHRASES if p in low), None)
    geo_redirected = _host(final_url) != _host(url) or final_url.rstrip("/") != url.rstrip("/")

    extracted = _rpc._from_jsonld(doc) or _rpc._from_meta(doc) or _rpc._from_text(doc) or {}
    currency = extracted.get("currency")
    price = extracted.get("price")
    lang = _lang(doc)

    divergence: list[str] = []
    if expect_currency and currency and currency.upper() != expect_currency.upper():
        divergence.append(f"currency: in-region shows {currency}, you expected {expect_currency.upper()}")
    if expect_keyword and expect_keyword.lower() not in low:
        divergence.append(f"keyword '{expect_keyword}' NOT present in in-region view (possible geo-gated content)")
    if block_hit:
        divergence.append(f"geo-block phrase detected: '{block_hit}'")
    if geo_redirected:
        divergence.append(f"geo-redirected to {final_url}")

    return _onyx_sign.attest({
        "ok": True,
        "url": url,
        "final_url": final_url,
        "http_status": status,
        "observed_at": observed_at,
        "observed_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(observed_at)),
        "reachable": True,
        "geo_redirected": geo_redirected,
        "geo_blocked": bool(block_hit),
        "language": lang,
        "price": price,
        "currency": currency,
        "extraction_source": extracted.get("source"),
        "divergence": divergence,
        "diverges": bool(divergence),
        "vantage": _VANTAGE,
        "summary": (
            "In-region view matches expectations." if not divergence
            else f"{len(divergence)} divergence(s) from a datacenter view — " + "; ".join(divergence)
        ),
    }, tool=NAME)


run.__when_to_use__ = (
    "Before an agent assumes a price, currency, availability, or content is "
    "global when it may be region-gated. To confirm a storefront/page renders "
    "the same from a real regional vantage as from a US datacenter. To detect "
    "geo-redirects, 451/legal blocks, and 'not available in your country' walls "
    "that a cloud-IP fetch silently passes through differently."
)
run.__vs_alternatives__ = (
    "A datacenter 'fetch this URL' tool returns the datacenter view and is "
    "blind to regional gating. Raw proxies sell you GBs and make "
    "you parse + interpret the result yourself. This returns one structured, "
    "sourced observation from a real regional vantage with explicit divergence flags."
)
run.__example_request__ = {"url": "https://shop.example.com/p/1", "expect_currency": "USD"}
run.__example_response__ = {
    "ok": True,
    "final_url": "https://shop.example.com/gr/p/1",
    "geo_redirected": True,
    "currency": "EUR",
    "diverges": True,
    "divergence": ["currency: in-region shows EUR, you expected USD", "geo-redirected to https://shop.example.com/gr/p/1"],
}
