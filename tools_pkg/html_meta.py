"""Extract OG tags + structured meta from any URL."""
from __future__ import annotations

import re
import time
from html import unescape

import httpx

NAME = "onyx_html_meta"
PRICE_USDC = "0.0008"
TIER = "metered"
DESCRIPTION = (
    "Fetch a URL and extract OpenGraph + Twitter Card + standard meta tags: "
    "og:title, og:description, og:image, og:type, twitter:card, "
    "twitter:image, canonical link, favicon, JSON-LD blocks. Use when an "
    "agent needs to preview a link before sharing, build a citation card, "
    "or detect spam/ads via meta-tag fingerprints. Stripped of HTML noise. "
    "~150-500ms typical."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "URL to inspect"},
    },
    "required": ["url"],
}

_META = re.compile(
    r"<meta\s+([^>]+?)>", re.IGNORECASE | re.DOTALL
)
_ATTR = re.compile(r'(\w[\w:-]*)\s*=\s*"([^"]*)"', re.IGNORECASE)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_LINK = re.compile(r"<link\s+([^>]+?)>", re.IGNORECASE | re.DOTALL)
_JSONLD = re.compile(
    r'<script[^>]+type\s*=\s*"application/ld\+json"[^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
_WS = re.compile(r"\s+")


def _attrs(tag: str) -> dict:
    return {m.group(1).lower(): m.group(2) for m in _ATTR.finditer(tag)}


def run(url: str, **_: object) -> dict:
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError("url must start with http:// or https://")
    started = time.time()
    r = httpx.get(url, timeout=12.0, follow_redirects=True,
                  headers={"User-Agent": "onyx-actions/0.2"})
    r.raise_for_status()
    html = r.text[:600_000]  # cap

    metas = []
    for m in _META.finditer(html):
        a = _attrs(m.group(1))
        key = a.get("property") or a.get("name") or a.get("itemprop")
        content = a.get("content")
        if key and content:
            metas.append({"key": key, "content": unescape(content)[:500]})

    og = {m["key"]: m["content"] for m in metas if m["key"].startswith("og:")}
    twitter = {m["key"]: m["content"] for m in metas if m["key"].startswith("twitter:")}
    other = [m for m in metas if not m["key"].startswith(("og:", "twitter:"))]

    title_m = _TITLE.search(html)
    title = unescape(_WS.sub(" ", title_m.group(1)).strip()) if title_m else None

    canonical = None
    favicon = None
    for lm in _LINK.finditer(html):
        a = _attrs(lm.group(1))
        rel = (a.get("rel") or "").lower()
        href = a.get("href")
        if href and "canonical" in rel and not canonical:
            canonical = href
        if href and "icon" in rel and not favicon:
            favicon = href

    jsonld_blocks = len(list(_JSONLD.finditer(html)))

    return {
        "url": str(r.url),
        "status": r.status_code,
        "title": title,
        "og": og,
        "twitter": twitter,
        "canonical": canonical,
        "favicon": favicon,
        "other_meta_count": len(other),
        "jsonld_blocks": jsonld_blocks,
        "elapsed_ms": int((time.time() - started) * 1000),
    }
