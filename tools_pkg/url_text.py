"""Fetch a URL, strip HTML, return readable text."""
from __future__ import annotations

import re
import time
from html import unescape

import httpx

NAME = "onyx_url_text"
PRICE_USDC = "0.001"
TIER = "metered"
DESCRIPTION = (
    "Fetch any public URL and return the readable text content stripped of "
    "HTML/scripts/styles. Use when an agent needs to reason over a web page "
    "without rendering a browser — docs pages, articles, search-result "
    "snippets, GitHub READMEs. Returns plain text + page title + word count "
    "+ final URL after redirects. Capped at 200kB output to keep token costs "
    "predictable. ~150-800ms typical depending on origin server."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "HTTPS URL to fetch"},
        "max_chars": {"type": "integer", "default": 50000, "description": "Truncate output (max 200000)"},
    },
    "required": ["url"],
}

_SCRIPT_STYLE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG = re.compile(r"<[^>]+>")
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_WHITESPACE = re.compile(r"\s+")


def run(url: str, max_chars: int = 50000, **_: object) -> dict:
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError("url must start with http:// or https://")
    cap = min(max(int(max_chars), 100), 200000)
    started = time.time()
    r = httpx.get(url, timeout=15.0, follow_redirects=True,
                  headers={"User-Agent": "onyx-actions/0.2 (+https://onyx-actions.onrender.com)"})
    r.raise_for_status()
    html = r.text
    title_m = _TITLE.search(html)
    title = unescape(_WHITESPACE.sub(" ", title_m.group(1)).strip()) if title_m else None
    cleaned = _SCRIPT_STYLE.sub(" ", html)
    text = unescape(_WHITESPACE.sub(" ", _TAG.sub(" ", cleaned)).strip())
    truncated = len(text) > cap
    if truncated:
        text = text[:cap]
    return {
        "url": str(r.url),
        "status": r.status_code,
        "title": title,
        "text": text,
        "char_count": len(text),
        "word_count": len(text.split()),
        "truncated": truncated,
        "elapsed_ms": int((time.time() - started) * 1000),
    }
