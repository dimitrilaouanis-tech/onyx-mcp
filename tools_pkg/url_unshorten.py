"""Follow URL redirects, return final destination + full chain."""
from __future__ import annotations

import time

import httpx

NAME = "onyx_url_unshorten"
PRICE_USDC = "0.0005"
TIER = "metered"
DESCRIPTION = (
    "Follow HTTP redirects on any URL and return the final destination + the "
    "full redirect chain. Use when an agent encounters a bit.ly/t.co/lnkd.in/ "
    "shortened link and needs to know where it actually goes before clicking. "
    "Returns each hop's status code, location, and final URL with status. "
    "Cap of 10 hops to prevent loops. ~100-400ms typical."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "URL to unshorten"},
    },
    "required": ["url"],
}


def run(url: str, **_: object) -> dict:
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError("url must start with http:// or https://")
    started = time.time()
    chain = []
    current = url
    with httpx.Client(follow_redirects=False, timeout=8.0,
                      headers={"User-Agent": "onyx-actions/0.2"}) as client:
        for hop in range(10):
            r = client.head(current)
            if r.status_code == 405 or "location" not in r.headers:
                # Some servers reject HEAD — fall back to GET
                r = client.get(current)
            chain.append({"url": current, "status": r.status_code,
                          "location": r.headers.get("location")})
            if 300 <= r.status_code < 400 and "location" in r.headers:
                current = httpx.URL(current).join(r.headers["location"]).human_repr()
                continue
            break
    return {
        "input_url": url,
        "final_url": current,
        "hops": len(chain),
        "chain": chain,
        "elapsed_ms": int((time.time() - started) * 1000),
    }
