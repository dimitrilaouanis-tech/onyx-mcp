"""Live health probe across all known x402 facilitators.

x402_facilitators.py lists the 5 known facilitators statically. This tool
actually probes each one — measures latency, checks endpoint availability,
returns up/down + composite ecosystem health.

Lane: no public x402 facilitator status page exists. Agents picking a
facilitator at runtime, or operators alerting on outages, have nowhere
to look. This is the first.

Stdlib + threading. Free tier.
"""
from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

NAME = "onyx_facilitator_health"
PRICE_USDC = "0"
TIER = "free"
DESCRIPTION = (
    "Live up/down + latency probe for all 5 known x402 facilitators "
    "(Coinbase CDP, x402.org public, xpay.sh, cronos-x402, faremeter). "
    "Returns per-facilitator status, response time, capabilities probe, "
    "plus ecosystem-wide health score. Free tier — agents shouldn't "
    "hardcode a single facilitator; this lets them pick a live one."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "include_capabilities": {
            "type": "boolean",
            "default": True,
            "description": "Also probe each facilitator's /supported endpoint to enumerate networks + schemes.",
        },
        "timeout_seconds": {
            "type": "number",
            "default": 6.0,
            "description": "Per-facilitator HTTP timeout. Max 15.",
        },
    },
}

# Known x402 facilitators as of 2026-05
_FACILITATORS = [
    {
        "id": "coinbase-cdp",
        "name": "Coinbase CDP Facilitator",
        "url": "https://api.cdp.coinbase.com/platform/v2/x402",
        "health_path": "/supported",
        "requires_auth": True,
        "auth_note": "JWT Ed25519 (CDP_API_KEY_ID + CDP_API_KEY_SECRET)",
        "networks": ["eip155:8453", "eip155:84532"],
    },
    {
        "id": "x402-public",
        "name": "x402.org Public Facilitator",
        "url": "https://x402.org/facilitator",
        "health_path": "/supported",
        "requires_auth": False,
        "auth_note": "Public, no key required (testnet-grade)",
        "networks": ["eip155:84532"],
    },
    {
        "id": "xpay-sh",
        "name": "xpay.sh",
        "url": "https://xpay.sh",
        "health_path": "/",
        "requires_auth": True,
        "auth_note": "Account-based, key required",
        "networks": ["eip155:8453"],
    },
    {
        "id": "cronos-x402",
        "name": "Cronos x402 Facilitator",
        "url": "https://x402.cronos.org",
        "health_path": "/",
        "requires_auth": False,
        "auth_note": "Public (Cronos chain only)",
        "networks": ["eip155:25"],
    },
    {
        "id": "faremeter",
        "name": "Faremeter",
        "url": "https://faremeter.com",
        "health_path": "/",
        "requires_auth": True,
        "auth_note": "Account-based, key required",
        "networks": ["eip155:8453", "eip155:84532"],
    },
]


def _probe_one(fac: dict, include_caps: bool, timeout: float) -> dict:
    """Probe a single facilitator. Returns status dict."""
    base = fac["url"].rstrip("/")
    target = base + fac["health_path"]
    started = time.time()
    result = {
        "id": fac["id"],
        "name": fac["name"],
        "url": fac["url"],
        "requires_auth": fac["requires_auth"],
        "networks": fac["networks"],
    }
    try:
        req = urllib.request.Request(target, headers={
            "User-Agent": "Mozilla/5.0 (compatible; OnyxFacilitatorHealth/1.0)",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            elapsed_ms = int((time.time() - started) * 1000)
            body = resp.read(16384).decode("utf-8", "replace")
            result["status"] = resp.status
            result["latency_ms"] = elapsed_ms
            result["alive"] = True
            if include_caps:
                try:
                    j = json.loads(body)
                    if isinstance(j, dict):
                        result["capabilities"] = {
                            "kinds_supported": len(j.get("kinds", [])) if isinstance(j.get("kinds"), list) else None,
                            "schemes_supported": list({k.get("scheme") for k in (j.get("kinds") or []) if isinstance(k, dict)}),
                            "networks_advertised": list({k.get("network") for k in (j.get("kinds") or []) if isinstance(k, dict)}),
                        }
                except Exception:
                    pass
    except urllib.error.HTTPError as e:
        elapsed_ms = int((time.time() - started) * 1000)
        result["status"] = e.code
        result["latency_ms"] = elapsed_ms
        # 401/403 still proves the server is alive — auth-walled, not down
        result["alive"] = e.code in (401, 403, 404)
        if e.code in (401, 403):
            result["note"] = "auth-walled but reachable (server alive)"
        elif e.code == 404:
            result["note"] = "404 on health path — endpoint may have moved"
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as e:
        result["alive"] = False
        result["error"] = str(e)[:160]
        result["latency_ms"] = None
    return result


def run(
    include_capabilities: bool = True,
    timeout_seconds: float = 6.0,
    **_: object,
) -> dict:
    timeout = max(2.0, min(float(timeout_seconds), 15.0))

    results = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(_probe_one, fac, include_capabilities, timeout): fac
                   for fac in _FACILITATORS}
        for fut in as_completed(futures):
            try:
                results.append(fut.result())
            except Exception as e:
                fac = futures[fut]
                results.append({"id": fac["id"], "alive": False, "error": str(e)[:160]})

    # Sort by alive desc, latency asc
    results.sort(key=lambda r: (not r.get("alive", False), r.get("latency_ms") or 99999))

    alive = [r for r in results if r.get("alive")]
    dead = [r for r in results if not r.get("alive")]
    avg_latency = (
        sum(r["latency_ms"] for r in alive if r.get("latency_ms") is not None) / max(len(alive), 1)
        if alive else None
    )

    return {
        "ok": True,
        "facilitators_total": len(results),
        "facilitators_alive": len(alive),
        "facilitators_dead": len(dead),
        "ecosystem_health_pct": int(100 * len(alive) / max(len(results), 1)),
        "average_latency_ms": int(avg_latency) if avg_latency else None,
        "results": results,
        "fastest_alive": alive[0] if alive else None,
        "recommendation": (
            f"Fastest live facilitator: {alive[0]['name']} ({alive[0]['latency_ms']}ms)"
            if alive else "All facilitators dead — fall back to self-hosted or wait."
        ),
        "note": (
            "Auth-walled facilitators (401/403 on /supported) are counted as "
            "alive — the server is reachable, just requires credentials. To "
            "test functional integration, see onyx_verify_explain."
        ),
    }


run.__when_to_use__ = (
    "An agent or operator needs to know which x402 facilitators are live "
    "right now, with latency for each. Useful for picking a facilitator at "
    "runtime instead of hardcoding, or for alerting on outages."
)
run.__vs_alternatives__ = (
    "No public x402 facilitator status page exists. Each facilitator's own "
    "uptime page (if any) only covers themselves. This is the first cross-"
    "facilitator health dashboard."
)
run.__example_request__ = {"include_capabilities": True, "timeout_seconds": 6.0}
run.__example_response__ = {
    "ok": True,
    "facilitators_total": 5,
    "facilitators_alive": 3,
    "ecosystem_health_pct": 60,
    "average_latency_ms": 180,
    "fastest_alive": {"id": "x402-public", "latency_ms": 120, "name": "x402.org Public Facilitator"},
}
