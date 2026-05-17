"""Probe any public MCP / x402 server for health, discovery surface, and
composite reliability score. Stdlib-only. SSRF-hardened (blocks private/
loopback ranges so this can't be used to scan internal networks).

Composite score (0-100):
  +20 root reachable < 2s
  +20 /health returns 200
  +15 /.well-known/x402.json parseable
  +15 /mcp/ responds (any status, just live)
  +10 /llms.txt present
  +10 either /.well-known/oauth-authorization-server OR /.well-known/oauth-protected-resource (MCP 2026-04 DCR spec)
  +10 /manifest returns 200 JSON
"""
from __future__ import annotations

import ipaddress
import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

NAME = "onyx_mcp_health"
PRICE_USDC = "0"
TIER = "free"
DESCRIPTION = (
    "Probe any public MCP / x402 server and return a structured health "
    "snapshot: endpoint latencies, content types, MCP discovery surface, "
    "x402 readiness, OAuth DCR advertisement, and a 0-100 composite "
    "reliability score. Stdlib-only. SSRF-hardened — refuses private, "
    "loopback, link-local, and reserved address ranges. Free tier, no key."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "server_url": {
            "type": "string",
            "description": "Base URL of the MCP / x402 server (https://example.com). Must be public.",
        },
        "timeout_seconds": {
            "type": "integer",
            "description": "Per-request timeout. Defaults to 6.",
            "default": 6,
            "minimum": 1,
            "maximum": 20,
        },
        "extra_paths": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Additional paths to probe beyond the standard MCP/x402 set.",
        },
    },
}

_DEFAULT_SERVER = "https://onyx-actions.onrender.com"

_STANDARD_PATHS = [
    "/",
    "/health",
    "/manifest",
    "/.well-known/x402.json",
    "/.well-known/x402",
    "/.well-known/mcp",
    "/.well-known/oauth-authorization-server",
    "/.well-known/oauth-protected-resource",
    "/mcp/",
    "/llms.txt",
    "/bazaar.json",
]


def _is_public_address(host: str) -> tuple[bool, str]:
    """Resolve `host` and assert every result is a public IP.
    Returns (ok, reason). On any private/loopback/link-local hit returns False.
    """
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        return False, f"DNS resolve failed: {e}"
    seen = set()
    for fam, _, _, _, sa in infos:
        ip_str = sa[0]
        if ip_str in seen:
            continue
        seen.add(ip_str)
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return False, f"could not parse address {ip_str}"
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_multicast or ip.is_reserved or ip.is_unspecified):
            return False, f"refuses non-public address {ip_str} for host {host}"
    return True, "ok"


def _probe(url: str, timeout: float) -> dict:
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(
            url, headers={
                "User-Agent": "onyx-mcp-health/1.0",
                "Accept": "application/json, text/plain, text/html;q=0.5",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body_bytes = resp.read(8192)
            return {
                "url": url,
                "status": resp.status,
                "content_type": resp.headers.get("Content-Type", ""),
                "latency_ms": int((time.perf_counter() - t0) * 1000),
                "bytes": len(body_bytes),
                "json_parseable": _try_json(body_bytes, resp.headers.get("Content-Type", "")),
                "error": None,
            }
    except urllib.error.HTTPError as e:
        return {
            "url": url, "status": e.code,
            "content_type": e.headers.get("Content-Type", "") if e.headers else "",
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "bytes": 0, "json_parseable": False,
            "error": f"HTTP {e.code}",
        }
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as e:
        return {
            "url": url, "status": None, "content_type": "",
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "bytes": 0, "json_parseable": False,
            "error": str(e)[:200],
        }


def _try_json(body: bytes, ctype: str) -> bool:
    if "json" not in ctype.lower():
        return False
    try:
        json.loads(body.decode("utf-8", "replace"))
        return True
    except Exception:
        return False


def run(
    server_url: str | None = None,
    timeout_seconds: int = 6,
    extra_paths: list[str] | None = None,
    **_: object,
) -> dict:
    if not server_url:
        server_url = _DEFAULT_SERVER
    parsed = urllib.parse.urlparse(server_url.strip())
    if parsed.scheme not in ("http", "https"):
        raise ValueError("server_url must be http:// or https://")
    if not parsed.netloc:
        raise ValueError("server_url missing host")

    host = parsed.hostname or ""
    ok, reason = _is_public_address(host)
    if not ok:
        return {
            "ok": False,
            "server_url": server_url,
            "host": host,
            "error": reason,
            "endpoints": [],
            "score": 0,
        }

    base = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    paths = list(_STANDARD_PATHS)
    if extra_paths:
        for p in extra_paths:
            if isinstance(p, str) and p.startswith("/") and p not in paths:
                paths.append(p)

    results = []
    for p in paths:
        url = base + p
        results.append(_probe(url, timeout_seconds))

    by_path = {p: r for p, r in zip(paths, results)}

    # Composite score
    score = 0
    if (by_path["/"].get("status") in (200, 422, 404)
            and (by_path["/"].get("latency_ms") or 0) < 2000):
        score += 20
    if by_path["/health"].get("status") == 200:
        score += 20
    if (by_path["/.well-known/x402.json"].get("status") == 200
            and by_path["/.well-known/x402.json"].get("json_parseable")):
        score += 15
    if by_path["/mcp/"].get("status") is not None:
        score += 15
    if by_path["/llms.txt"].get("status") == 200:
        score += 10
    if (by_path["/.well-known/oauth-authorization-server"].get("status") == 200
            or by_path["/.well-known/oauth-protected-resource"].get("status") == 200):
        score += 10
    if (by_path["/manifest"].get("status") == 200
            and by_path["/manifest"].get("json_parseable")):
        score += 10

    # Capability flags for downstream agents to consume
    capabilities = {
        "mcp_advertised": by_path["/mcp/"].get("status") is not None,
        "x402_advertised": (by_path["/.well-known/x402.json"].get("status") == 200
                            or by_path["/.well-known/x402"].get("status") == 200),
        "oauth_dcr_advertised": (
            by_path["/.well-known/oauth-authorization-server"].get("status") == 200
            and by_path["/.well-known/oauth-protected-resource"].get("status") == 200),
        "manifest_json": (by_path["/manifest"].get("status") == 200
                          and by_path["/manifest"].get("json_parseable")),
        "llms_txt": by_path["/llms.txt"].get("status") == 200,
        "bazaar_data_exposed": by_path.get("/bazaar.json", {}).get("status") == 200,
    }

    # Latency summary across successful probes
    latencies = [r.get("latency_ms") for r in results if r.get("status") is not None]
    median_latency = sorted(latencies)[len(latencies)//2] if latencies else None

    grade = ("A" if score >= 90 else "B" if score >= 70
             else "C" if score >= 50 else "D" if score >= 30 else "F")

    return {
        "ok": True,
        "server_url": server_url,
        "host": host,
        "score": score,
        "grade": grade,
        "median_latency_ms": median_latency,
        "capabilities": capabilities,
        "endpoints": results,
    }


run.__when_to_use__ = (
    "An agent needs to evaluate whether an MCP server is alive, what it advertises "
    "(MCP transport, x402 payment, OAuth DCR, llms.txt, manifest), and how reliably "
    "it responds — before committing to call its paid endpoints."
)
run.__vs_alternatives__ = (
    "No paid 'uptime robot for MCPs' exists. UptimeRobot/Pingdom do generic HTTP probes "
    "but don't understand MCP/x402 discovery surface. This tool emits structured "
    "capability flags and a composite score agents can use directly in routing."
)
run.__example_request__ = {
    "server_url": "https://onyx-actions.onrender.com",
}
run.__example_response__ = {
    "ok": True,
    "server_url": "https://onyx-actions.onrender.com",
    "host": "onyx-actions.onrender.com",
    "score": 80,
    "grade": "B",
    "median_latency_ms": 240,
    "capabilities": {
        "mcp_advertised": True,
        "x402_advertised": True,
        "oauth_dcr_advertised": False,
        "manifest_json": True,
        "llms_txt": True,
        "bazaar_data_exposed": True,
    },
    "endpoints": [
        {"url": "...", "status": 200, "latency_ms": 180, "content_type": "application/json", "bytes": 1024, "json_parseable": True, "error": None},
    ],
}
