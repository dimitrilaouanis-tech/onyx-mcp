"""Parse any URL into structured components. Stdlib urllib."""
from __future__ import annotations

from urllib.parse import urlparse, parse_qsl

NAME = "onyx_url_parse"
PRICE_USDC = "0.0003"
TIER = "metered"
DESCRIPTION = (
    "Parse any URL into structured components: scheme, host, port, path, "
    "query params (as both raw and decoded list), fragment, userinfo. Use "
    "when an agent needs to inspect, modify, or validate a URL — change a "
    "query param, strip tracking, normalize for caching. Stdlib only, no "
    "network calls, <1ms."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "URL to parse"},
    },
    "required": ["url"],
}


def run(url: str, **_: object) -> dict:
    if not url:
        raise ValueError("url required")
    p = urlparse(url)
    qs = parse_qsl(p.query, keep_blank_values=True)
    return {
        "url": url,
        "scheme": p.scheme,
        "userinfo": p.username,
        "password_present": bool(p.password),
        "host": p.hostname,
        "port": p.port,
        "path": p.path,
        "params": p.params or None,
        "query_raw": p.query,
        "query": [{"key": k, "value": v} for k, v in qs],
        "fragment": p.fragment or None,
    }
