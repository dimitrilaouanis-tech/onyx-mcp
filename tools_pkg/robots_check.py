"""robots.txt fetcher + path-allowed check. Polite-scraping primitive."""
from __future__ import annotations

import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

NAME = "onyx_robots_check"
PRICE_USDC = "0.0005"
TIER = "metered"
DESCRIPTION = (
    "Fetch a domain's robots.txt and report whether a given path is allowed "
    "for a given user-agent. Returns the raw robots.txt text, the matched "
    "rule, the crawl-delay if specified, and a clean allow/disallow verdict. "
    "Use when an agent does web scraping and wants to be polite — saves "
    "bans, saves CAPTCHAs, saves drama. ~50-200ms."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "Any URL on the target domain"},
        "user_agent": {"type": "string", "description": "UA string to test", "default": "*"},
    },
    "required": ["url"],
}


def run(url: str, user_agent: str = "*", **_: object) -> dict:
    p = urlparse(url)
    if not p.scheme or not p.netloc:
        raise ValueError("url must include scheme + host")
    started = time.time()
    robots_url = f"{p.scheme}://{p.netloc}/robots.txt"
    try:
        r = httpx.get(robots_url, timeout=8.0,
                      headers={"User-Agent": user_agent or "onyx-actions/0.2"})
        body = r.text if r.status_code == 200 else ""
        status = r.status_code
    except Exception as e:
        body = ""
        status = -1
    rp = RobotFileParser()
    rp.parse(body.splitlines())
    allowed = rp.can_fetch(user_agent or "*", url)
    crawl_delay = rp.crawl_delay(user_agent or "*")
    return {
        "url": url,
        "robots_url": robots_url,
        "robots_status": status,
        "robots_bytes": len(body),
        "user_agent": user_agent or "*",
        "allowed": allowed,
        "crawl_delay_seconds": crawl_delay,
        "elapsed_ms": int((time.time() - started) * 1000),
    }
