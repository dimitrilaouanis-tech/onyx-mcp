"""DNS A/AAAA resolution + reverse PTR via stdlib."""
from __future__ import annotations

import socket
import time

NAME = "onyx_dns_lookup"
PRICE_USDC = "0.0005"
TIER = "metered"
DESCRIPTION = (
    "Resolve a domain to its A/AAAA records, or reverse-resolve an IP to its "
    "hostname. Useful for validating a domain exists before scraping, "
    "checking if two domains share infrastructure, mapping CDN origins, or "
    "doing safety lookups before agents call third-party APIs. Returns IPv4, "
    "IPv6, canonical hostname, and resolution time. Powered by stdlib so "
    "results are whatever the host's DNS resolver returns — typically "
    "20-100ms."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "host": {"type": "string", "description": "Domain (example.com) or IP address"},
    },
    "required": ["host"],
}


def run(host: str, **_: object) -> dict:
    host = (host or "").strip().lower()
    if not host:
        raise ValueError("host required")
    started = time.time()
    out: dict = {"host": host}
    try:
        infos = socket.getaddrinfo(host, None)
        ipv4 = sorted({i[4][0] for i in infos if i[0] == socket.AF_INET})
        ipv6 = sorted({i[4][0] for i in infos if i[0] == socket.AF_INET6})
        out["ipv4"] = ipv4
        out["ipv6"] = ipv6
        out["resolved"] = bool(ipv4 or ipv6)
    except socket.gaierror as e:
        out["resolved"] = False
        out["error"] = str(e)
    try:
        is_ip = all(c.isdigit() or c == "." for c in host)
        if is_ip:
            out["reverse"] = socket.gethostbyaddr(host)[0]
    except Exception:
        pass
    out["elapsed_ms"] = int((time.time() - started) * 1000)
    return out
