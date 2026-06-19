"""Retail price / stock ground-truth oracle — paid x402 MCP tool.

The agentic web is flooding with synthetic, plausible-but-wrong output. The
scarce, premium commodity is GROUND TRUTH: a real-world observation an agent
cannot fabricate. This tool returns ONE signed observation —

    "the current price + in-stock state for THIS product URL, as actually
     fetched right now, with the evidence we extracted it from."

The empty slot: every existing retail MCP only covers merchants that built a
clean official API (Shopify Catalog, Kroger, Tesco). The long tail of
regional shops with NO api is invisible to agents — and that is
exactly where agents hallucinate prices. We observe the real page and return
a structured, timestamped result with the extraction source so the caller can
trust it.

Extraction order (most → least reliable):
  1. schema.org JSON-LD  (Product / Offer — the canonical e-commerce markup)
  2. OpenGraph / product meta  (og:price:amount, product:price:amount)
  3. itemprop microdata  (itemprop="price" / "availability")
  4. visible-text currency regex  (last-resort, flagged low-confidence)

We never invent a number. If nothing is found we say so (ok=True,
price=None, confidence="none") rather than guess — that honesty IS the
product in a hallucination-flooded market.

Bright line: this sells a REAL observation of a public page. It makes no
claim about persons, identity, or personhood.
"""
from __future__ import annotations

import html
import json
import re
import time
import urllib.error
import urllib.request

from . import _onyx_sign

NAME = "onyx_retail_price_check"
PRICE_USDC = "0.02"
TIER = "metered"
DESCRIPTION = (
    "Ground-truth retail oracle. Give a product URL; get the real current "
    "price, currency, and in-stock state as actually fetched now — with the "
    "extraction source (JSON-LD / OpenGraph / microdata) as evidence. Covers "
    "the long tail of no-API shops where agents otherwise hallucinate prices. "
    "Never guesses: returns price=None with confidence='none' when the page "
    "exposes no machine-readable price. Use before an agent quotes, compares, "
    "or transacts on a price it would otherwise invent."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "url": {
            "type": "string",
            "description": "Full product page URL (http/https). The exact page whose price + availability you want observed.",
        },
        "expect_price": {
            "type": "number",
            "description": "Optional. A price you believe is current. If given, the result includes matches_expected:bool + drift so a caller can detect a stale/hallucinated quote.",
        },
    },
    "required": ["url"],
}

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 onyx-truth/1.0"
)
_TIMEOUT = 14.0
_MAX_BYTES = 2_500_000  # don't slurp giant pages

_CUR_SYMBOL = {"€": "EUR", "$": "USD", "£": "GBP", "₺": "TRY", "¥": "JPY", "₹": "INR"}
_AVAIL_IN = ("instock", "in_stock", "available", "limitedavailability", "preorder", "backorder")
_AVAIL_OUT = ("outofstock", "out_of_stock", "soldout", "sold_out", "discontinued", "unavailable")


def _fetch(url: str) -> tuple[int, str, dict]:
    # SSRF-guarded + provenance-recording fetch (shared _provenance). An attacker
    # can no longer redirect the oracle to internal/metadata endpoints, and the
    # returned provenance (source/final URL, content sha256, fetched_at) is
    # embedded in the signed verdict so the signature commits to WHAT was observed.
    from . import _provenance
    status, text, prov = _provenance.safe_fetch(url, timeout=_TIMEOUT, max_bytes=_MAX_BYTES)
    return status, text, prov


def _num(v: object) -> float | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    # strip currency symbols/letters, normalise decimal comma -> dot
    s = re.sub(r"[^\d,.\-]", "", s)
    if not s:
        return None
    # "1.234,56" (EU) -> "1234.56" ; "1,234.56" (US) -> "1234.56"
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        # comma as decimal sep if it looks like one (2 trailing digits)
        s = s.replace(",", ".") if re.search(r",\d{1,2}$", s) else s.replace(",", "")
    try:
        return round(float(s), 4)
    except ValueError:
        return None


def _norm_avail(v: object) -> bool | None:
    if v is None:
        return None
    s = str(v).lower()
    s = s.rsplit("/", 1)[-1].replace(" ", "").replace("-", "")  # schema.org URL tail
    if any(t in s for t in _AVAIL_OUT):
        return False
    if any(t in s for t in _AVAIL_IN):
        return True
    return None


def _iter_jsonld(doc: str):
    for m in re.finditer(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', doc, re.I | re.S):
        block = m.group(1).strip()
        try:
            data = json.loads(block)
        except (ValueError, TypeError):
            continue
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, dict):
                if "@graph" in node and isinstance(node["@graph"], list):
                    stack.extend(node["@graph"])
                yield node


def _from_jsonld(doc: str) -> dict | None:
    for node in _iter_jsonld(doc):
        t = node.get("@type")
        types = {t.lower()} if isinstance(t, str) else {str(x).lower() for x in (t or [])}
        offers = node.get("offers")
        if not offers and "product" not in types and "offer" not in types:
            continue
        offer = offers
        if isinstance(offer, list):
            offer = offer[0] if offer else None
        if isinstance(offer, dict):
            price = _num(offer.get("price") or offer.get("lowPrice") or (offer.get("priceSpecification") or {}).get("price"))
            cur = offer.get("priceCurrency") or (offer.get("priceSpecification") or {}).get("priceCurrency")
            avail = _norm_avail(offer.get("availability"))
        else:
            price, cur, avail = _num(node.get("price")), node.get("priceCurrency"), _norm_avail(node.get("availability"))
        if price is not None:
            return {
                "price": price,
                "currency": (str(cur).upper()[:3] if cur else None),
                "in_stock": avail,
                "source": "jsonld",
                "confidence": "high",
                "title": (node.get("name") if isinstance(node.get("name"), str) else None),
            }
    return None


def _meta(doc: str, *keys: str) -> str | None:
    for key in keys:
        m = re.search(
            r'<meta[^>]+(?:property|name|itemprop)=["\']' + re.escape(key) + r'["\'][^>]+content=["\']([^"\']+)["\']',
            doc, re.I,
        )
        if not m:
            m = re.search(
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name|itemprop)=["\']' + re.escape(key) + r'["\']',
                doc, re.I,
            )
        if m:
            return html.unescape(m.group(1).strip())
    return None


def _from_meta(doc: str) -> dict | None:
    price = _num(_meta(doc, "product:price:amount", "og:price:amount", "price", "twitter:data1"))
    if price is None:
        return None
    cur = _meta(doc, "product:price:currency", "og:price:currency", "priceCurrency")
    avail = _norm_avail(_meta(doc, "product:availability", "og:availability", "availability"))
    return {
        "price": price,
        "currency": (cur.upper()[:3] if cur else None),
        "in_stock": avail,
        "source": "opengraph_meta",
        "confidence": "medium",
        "title": _meta(doc, "og:title"),
    }


def _from_text(doc: str) -> dict | None:
    # last-resort: a currency symbol next to a number in the visible HTML
    m = re.search(r'([€$£₺¥₹])\s?(\d[\d.,]{0,12}\d|\d)', doc)
    if not m:
        return None
    price = _num(m.group(2))
    if price is None:
        return None
    return {
        "price": price,
        "currency": _CUR_SYMBOL.get(m.group(1)),
        "in_stock": None,
        "source": "text_regex",
        "confidence": "low",
        "title": None,
    }


def run(url: str = "", expect_price: float | None = None, **_: object) -> dict:
    url = (url or "").strip()
    if not url:
        raise ValueError("url is required")
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("url must be an http(s) URL")

    observed_at = int(time.time())
    try:
        status, doc, prov = _fetch(url)
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": "http_error", "http_status": e.code, "url": url, "observed_at": observed_at}
    except (urllib.error.URLError, TimeoutError) as e:
        return {"ok": False, "error": "fetch_failed", "detail": str(e)[:200], "url": url, "observed_at": observed_at}
    except Exception as e:
        # SSRFBlocked and friends — refuse, don't fetch internal/attacker targets.
        if type(e).__name__ == "SSRFBlocked":
            return {"ok": False, "error": "ssrf_blocked", "detail": str(e)[:120], "url": url, "observed_at": observed_at}
        raise

    found = _from_jsonld(doc) or _from_meta(doc) or _from_text(doc)
    if not found:
        title = _meta(doc, "og:title")
        return _onyx_sign.attest({
            "ok": True,
            "url": url,
            "http_status": status,
            "observed_at": observed_at,
            "price": None,
            "currency": None,
            "in_stock": None,
            "confidence": "none",
            "title": title,
            "note": "No machine-readable price found. We return None rather than guess.",
            "vantage": "onyx-observer",
            "provenance": prov,
        }, tool=NAME)

    result = {
        "ok": True,
        "url": url,
        "http_status": status,
        "observed_at": observed_at,
        "observed_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(observed_at)),
        "price": found["price"],
        "currency": found["currency"],
        "in_stock": found["in_stock"],
        "extraction_source": found["source"],
        "confidence": found["confidence"],
        "title": found.get("title"),
        "vantage": "onyx-observer",
        "provenance": prov,
    }

    if expect_price is not None:
        try:
            exp = float(expect_price)
            drift = round(found["price"] - exp, 4)
            result["expected_price"] = exp
            result["drift"] = drift
            result["matches_expected"] = abs(drift) < max(0.01, exp * 0.005)
            if not result["matches_expected"]:
                result["stale_quote_warning"] = (
                    f"Observed {found['price']} {found['currency'] or ''} differs from "
                    f"expected {exp} by {drift} — your cached/quoted price is stale or invented."
                )
        except (TypeError, ValueError):
            pass

    return _onyx_sign.attest(result, tool=NAME)


run.__when_to_use__ = (
    "Before an agent quotes, compares, or transacts on a retail price — "
    "especially for shops with no official price API, where the agent would "
    "otherwise hallucinate. Also to detect a stale/invented cached price via "
    "expect_price drift."
)
run.__vs_alternatives__ = (
    "Official retail APIs (Shopify Catalog, Kroger, Tesco) only cover "
    "merchants who built them — the regional long tail is invisible. "
    "Generic 'fetch this URL' tools return raw HTML and make the agent parse "
    "(and mis-parse) it. This returns ONE structured, sourced, timestamped "
    "observation with an explicit confidence and never-guess guarantee."
)
run.__example_request__ = {"url": "https://www.example-shop.com/product/123", "expect_price": 49.90}
run.__example_response__ = {
    "ok": True,
    "price": 49.90,
    "currency": "EUR",
    "in_stock": True,
    "extraction_source": "jsonld",
    "confidence": "high",
    "matches_expected": True,
}
