"""Signed web enrichment aggregator — paid x402 MCP tool.

The single highest-volume product class on x402 is the ENRICHMENT AGGREGATOR:
StableEnrich (~108K calls/30d, the #1 service) wraps people/web/scrape/places/
social/contact sources behind one pay-per-call endpoint. The whole market buys
DATA bundles, not 'verification'. This is that product — one call, many signals —
with the thing none of the aggregators ship: an Ed25519 signature over the bundle.

    "everything publicly knowable about THIS site in one signed call:
     identity, description, contacts, social presence, structured data —
     fetched now, provable, tamper-rejected."

Covers three of the six StableEnrich legs in one shot (web scrape + contact +
social) and adds Onyx's edge: lightweight legitimacy signals (HTTPS, canonical,
declared org) so the enrichment doubles as a first-pass trust read. Facts, not
judgments; we extract what the page exposes and never invent.

Reuses the SSRF-guarded fetch (_provenance.safe_fetch) so the aggregator can't be
pointed at internal/metadata endpoints. Bright line: public web data only.
"""
from __future__ import annotations

import html
import json
import re
import time
import urllib.error

from . import _onyx_sign

NAME = "onyx_web_enrich"
PRICE_USDC = "0.01"
TIER = "metered"
DESCRIPTION = (
    "Signed web enrichment in one call. Give a domain or URL; get a single "
    "Ed25519-signed bundle of everything the page exposes — title, description, "
    "declared organization (schema.org), emails, phones, social profiles, "
    "canonical/lang, and HTTPS/legitimacy signals — fetched now and verifiable "
    "offline (tamper -> rejected). The aggregator pattern that dominates x402 "
    "(StableEnrich-style), with provenance the unsigned feeds can't offer."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "Domain or full URL to enrich, e.g. 'stripe.com' or 'https://stripe.com/about'."},
    },
    "required": ["url"],
}

_TIMEOUT = 14.0
_MAX_BYTES = 2_500_000
_SOCIAL = {
    "twitter": r"(?:twitter\.com|x\.com)/([A-Za-z0-9_]{1,30})",
    "linkedin": r"linkedin\.com/(?:company|in)/([A-Za-z0-9\-_%]{2,80})",
    "facebook": r"facebook\.com/([A-Za-z0-9.\-]{2,80})",
    "instagram": r"instagram\.com/([A-Za-z0-9_.]{2,40})",
    "github": r"github\.com/([A-Za-z0-9\-]{1,39})",
    "youtube": r"youtube\.com/(?:@|c/|channel/|user/)?([A-Za-z0-9_\-]{2,80})",
}
_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?:\+?\d[\d\s().\-]{7,}\d)")
_JUNK_EMAIL = ("example.com", "sentry.io", "wixpress.com", "@2x", "domain.com")


def _meta(doc: str, *keys: str) -> str | None:
    for key in keys:
        m = re.search(
            r'<meta[^>]+(?:property|name)=["\']' + re.escape(key) + r'["\'][^>]+content=["\']([^"\']+)["\']',
            doc, re.I) or re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']' + re.escape(key) + r'["\']',
            doc, re.I)
        if m:
            return html.unescape(m.group(1).strip())
    return None


def _orgs(doc: str) -> list[dict]:
    out = []
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', doc, re.I | re.S):
        try:
            data = json.loads(m.group(1).strip())
        except (ValueError, TypeError):
            continue
        stack = [data]
        while stack:
            n = stack.pop()
            if isinstance(n, list):
                stack.extend(n); continue
            if not isinstance(n, dict):
                continue
            stack.extend(n.get("@graph", []) if isinstance(n.get("@graph"), list) else [])
            t = n.get("@type")
            types = {t} if isinstance(t, str) else set(t or [])
            if types & {"Organization", "Corporation", "LocalBusiness", "WebSite"}:
                out.append({k: n.get(k) for k in ("name", "url", "sameAs", "@type") if n.get(k)})
    return out[:5]


def _clean_phones(doc_text: str) -> list[str]:
    seen, out = set(), []
    for m in _PHONE.findall(doc_text):
        digits = re.sub(r"\D", "", m)
        if 8 <= len(digits) <= 15 and digits not in seen:
            seen.add(digits); out.append(m.strip())
        if len(out) >= 5:
            break
    return out


def run(url: str = "", **_: object) -> dict:
    url = (url or "").strip()
    if not url:
        raise ValueError("url is required")
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    observed_at = int(time.time())

    from . import _provenance
    try:
        status, doc, prov = _provenance.safe_fetch(url, timeout=_TIMEOUT, max_bytes=_MAX_BYTES)
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": "http_error", "http_status": e.code, "url": url, "observed_at": observed_at}
    except (urllib.error.URLError, TimeoutError) as e:
        return {"ok": False, "error": "fetch_failed", "detail": str(e)[:160], "url": url, "observed_at": observed_at}
    except Exception as e:
        if type(e).__name__ == "SSRFBlocked":
            return {"ok": False, "error": "ssrf_blocked", "detail": str(e)[:120], "url": url, "observed_at": observed_at}
        raise

    visible = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", doc, flags=re.I | re.S)
    text = html.unescape(re.sub(r"<[^>]+>", " ", visible))

    emails = []
    for e in _EMAIL.findall(doc):
        e = e.lower()
        if e not in emails and not any(j in e for j in _JUNK_EMAIL):
            emails.append(e)
        if len(emails) >= 8:
            break

    socials = {}
    for net, pat in _SOCIAL.items():
        m = re.search(pat, doc, re.I)
        if m:
            socials[net] = m.group(0) if m.group(0).startswith("http") else "https://" + m.group(0)

    final_url = prov.get("final_url", url) if isinstance(prov, dict) else url
    orgs = _orgs(doc)
    result = {
        "ok": True,
        "url": url,
        "final_url": final_url,
        "http_status": status,
        "observed_at": observed_at,
        "observed_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(observed_at)),
        "title": _meta(doc, "og:title") or (re.search(r"<title[^>]*>(.*?)</title>", doc, re.I | re.S).group(1).strip()[:200] if re.search(r"<title", doc, re.I) else None),
        "description": _meta(doc, "description", "og:description"),
        "site_name": _meta(doc, "og:site_name"),
        "language": (re.search(r'<html[^>]+lang=["\']([A-Za-z\-]{2,8})', doc, re.I).group(1) if re.search(r'<html[^>]+lang=', doc, re.I) else None),
        "canonical": (re.search(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)', doc, re.I).group(1) if re.search(r'rel=["\']canonical', doc, re.I) else None),
        "image": _meta(doc, "og:image"),
        "organizations": orgs,
        "emails": emails,
        "phones": _clean_phones(text),
        "social_profiles": socials,
        "legitimacy": {
            "https": final_url.lower().startswith("https://"),
            "declares_org": bool(orgs),
            "has_canonical": bool(re.search(r'rel=["\']canonical', doc, re.I)),
            "contactable": bool(emails or socials),
        },
        "signals_found": None,  # filled below
        "vantage": "onyx-observer",
        "provenance": prov,
    }
    result["signals_found"] = sum([
        bool(result["title"]), bool(result["description"]), bool(orgs),
        bool(emails), bool(result["phones"]), bool(socials),
    ])
    return _onyx_sign.attest(result, tool=NAME)


run.__when_to_use__ = (
    "When an agent needs to enrich/qualify a company or website in one call — "
    "lead research, vendor due-diligence, CRM fill, outreach prep — and wants a "
    "verifiable bundle (identity + contacts + socials + structured data) instead "
    "of N separate scrapes it has to trust blindly."
)
run.__vs_alternatives__ = (
    "StableEnrich and other x402 aggregators return the same bundle UNSIGNED. "
    "Plain scrape tools (incl. onyx_html_meta) return one layer. This returns a "
    "multi-source bundle Ed25519-signed with provenance, so any third party can "
    "verify Onyx observed exactly this — and it doubles as a first-pass "
    "legitimacy read."
)
run.__example_request__ = {"url": "stripe.com"}
run.__example_response__ = {
    "ok": True, "title": "Stripe | Financial Infrastructure",
    "organizations": [{"name": "Stripe", "@type": "Organization"}],
    "social_profiles": {"twitter": "https://twitter.com/stripe"},
    "signals_found": 6, "legitimacy": {"https": True, "declares_org": True},
}
