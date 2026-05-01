"""Navigate a CDP-controlled Chrome to a URL."""
from __future__ import annotations

import time
from . import _cdp_client as cdp

NAME = "onyx_browser_navigate"
PRICE_USDC = "0.005"
TIER = "metered"
DESCRIPTION = (
    "Navigate a Chrome DevTools Protocol session to a target URL and wait "
    "for load. Returns the final URL after redirects, page title, and "
    "elapsed wait time. Use as the first step of a browser-agent workflow — "
    "screenshot/click/type tools below act on whatever page this lands on. "
    "Demo mode (default in cloud) returns a plausible synthetic result; "
    "self-host with ONYX_CDP_URL pointed at your Chrome (--remote-debugging"
    "-port=9222) for real navigation."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "URL to navigate to"},
        "wait_seconds": {"type": "number", "default": 1.5,
                         "description": "Settle time after navigation"},
    },
    "required": ["url"],
}


def run(url: str, wait_seconds: float = 1.5, **_: object) -> dict:
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError("url must start with http:// or https://")
    started = time.time()
    if cdp.demo_mode():
        return {
            "url": url, "final_url": url,
            "title": "Demo Page",
            "wait_seconds": wait_seconds,
            "demo": True,
            "note": "ONYX_DEMO_MODE=1. Self-host with ONYX_CDP_URL for real CDP.",
            "elapsed_ms": int((time.time() - started) * 1000),
        }
    cdp.cdp_call(None, "Page.navigate", {"url": url})
    time.sleep(max(0.1, min(wait_seconds, 10)))
    res = cdp.cdp_call(None, "Runtime.evaluate", {
        "expression": "JSON.stringify({u: location.href, t: document.title})",
        "returnByValue": True,
    })
    import json as _j
    info = _j.loads(res.get("result", {}).get("value") or "{}")
    return {
        "url": url,
        "final_url": info.get("u") or url,
        "title": info.get("t") or "",
        "elapsed_ms": int((time.time() - started) * 1000),
    }
