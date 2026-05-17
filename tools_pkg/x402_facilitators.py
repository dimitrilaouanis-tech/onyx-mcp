"""Directory of known x402 facilitators with live up/down status.

No public x402-facilitator directory exists. Agents picking which facilitator
to route through (CDP vs x402.org vs xpay.sh vs Faremeter vs Cronos) get a
ranked, real-time list with supported networks, auth scheme, and last-seen
response time. Stdlib-only HTTP probes. Free tier.
"""
from __future__ import annotations

import socket
import time
import urllib.error
import urllib.parse
import urllib.request

NAME = "onyx_x402_facilitators"
PRICE_USDC = "0"
TIER = "free"
DESCRIPTION = (
    "Directory of known x402 facilitators (Coinbase CDP, x402.org public, "
    "xpay.sh, Cronos, Faremeter, others), each with live reachability probe, "
    "supported networks, payment auth scheme (JWT / open), and median latency. "
    "Agents use this to choose where to route /verify and /settle calls. "
    "Free tier — refreshes per call, no API key."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "network": {
            "type": "string",
            "description": "Filter facilitators that support this network (CAIP-2 like 'eip155:8453', or short form 'base', 'base-sepolia', 'solana'). Omit for all.",
        },
        "include_inactive": {
            "type": "boolean",
            "default": False,
            "description": "Include facilitators that didn't respond on probe.",
        },
    },
}

# Canonical registry. Each entry: name, base URL, supported networks (CAIP-2),
# auth scheme, project/owner, status URL to probe.
_KNOWN_FACILITATORS = [
    {
        "name": "coinbase-cdp",
        "url": "https://api.cdp.coinbase.com/platform/v2/x402",
        "probe": "https://api.cdp.coinbase.com/platform/v2/x402/supported",
        "owner": "Coinbase",
        "networks": ["eip155:8453", "eip155:84532", "eip155:1", "eip155:137", "eip155:42161"],
        "auth": "jwt-ed25519",
        "notes": "Mainnet-grade. Requires CDP API key + per-request Ed25519 JWT. Industry default for Base mainnet.",
    },
    {
        "name": "x402-foundation-public",
        "url": "https://x402.org/facilitator",
        "probe": "https://x402.org/facilitator/supported",
        "owner": "x402 Foundation",
        "networks": ["eip155:84532"],
        "auth": "open",
        "notes": "Public testnet-only facilitator. No auth. Good for prototyping.",
    },
    {
        "name": "xpay-sh",
        "url": "https://xpay.sh",
        "probe": "https://xpay.sh/facilitator/supported",
        "owner": "xpay.sh",
        "networks": ["eip155:8453"],
        "auth": "api-key",
        "notes": "Independent x402 facilitator + listing surface. Newer than CDP.",
    },
    {
        "name": "cronos-x402",
        "url": "https://x402-facilitator.cronos.org",
        "probe": "https://x402-facilitator.cronos.org/health",
        "owner": "Cronos Labs",
        "networks": ["eip155:25", "eip155:338"],
        "auth": "open",
        "notes": "Facilitator for Cronos chain (Cronos = chainId 25 mainnet, 338 testnet). Mirror of CDP shape.",
    },
    {
        "name": "faremeter",
        "url": "https://faremeter.dev",
        "probe": "https://faremeter.dev/health",
        "owner": "Faremeter (Switchboard)",
        "networks": ["solana:mainnet", "solana:devnet"],
        "auth": "open",
        "notes": "Solana-only x402 facilitator. Used by @switchboard-xyz/x402-utils.",
    },
]


def _normalize_network(s: str) -> str | None:
    if not s:
        return None
    t = s.lower().strip()
    m = {
        "base": "eip155:8453", "base-mainnet": "eip155:8453",
        "base-sepolia": "eip155:84532", "sepolia": "eip155:84532",
        "ethereum": "eip155:1", "eth": "eip155:1", "mainnet": "eip155:1",
        "polygon": "eip155:137", "matic": "eip155:137",
        "arbitrum": "eip155:42161", "arb": "eip155:42161",
        "solana": "solana:mainnet", "solana-mainnet": "solana:mainnet",
        "solana-devnet": "solana:devnet", "devnet": "solana:devnet",
        "cronos": "eip155:25", "cronos-testnet": "eip155:338",
    }
    return m.get(t, t)


def _probe(url: str, timeout: float = 6.0) -> dict:
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "onyx-x402-facilitators/1.0",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {
                "status": resp.status,
                "latency_ms": int((time.perf_counter() - t0) * 1000),
                "content_type": resp.headers.get("Content-Type", ""),
                "error": None,
            }
    except urllib.error.HTTPError as e:
        # auth-required is still "alive" for our purposes
        return {
            "status": e.code,
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "content_type": (e.headers.get("Content-Type", "") if e.headers else ""),
            "error": None if e.code in (401, 403, 405) else f"HTTP {e.code}",
        }
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as e:
        return {
            "status": None,
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "content_type": "",
            "error": str(e)[:200],
        }


def _is_alive(probe: dict) -> bool:
    return probe.get("status") is not None and probe.get("error") is None


def run(
    network: str | None = None,
    include_inactive: bool = False,
    **_: object,
) -> dict:
    want_net = _normalize_network(network) if network else None
    results = []
    for fac in _KNOWN_FACILITATORS:
        if want_net and want_net not in fac["networks"]:
            continue
        probe = _probe(fac["probe"])
        alive = _is_alive(probe)
        if not alive and not include_inactive:
            continue
        results.append({
            "name": fac["name"],
            "owner": fac["owner"],
            "url": fac["url"],
            "probe_url": fac["probe"],
            "supported_networks": fac["networks"],
            "auth_scheme": fac["auth"],
            "alive": alive,
            "status": probe["status"],
            "latency_ms": probe["latency_ms"],
            "content_type": probe["content_type"],
            "probe_error": probe["error"],
            "notes": fac["notes"],
        })

    # Sort by alive-first, then ascending latency
    results.sort(key=lambda r: (0 if r["alive"] else 1, r["latency_ms"] or 99999))

    return {
        "ok": True,
        "network_filter": network,
        "network_normalized": want_net,
        "total_known": len(_KNOWN_FACILITATORS),
        "alive": sum(1 for r in results if r["alive"]),
        "returned": len(results),
        "facilitators": results,
    }


run.__when_to_use__ = (
    "An agent or developer needs to pick which x402 facilitator to send /verify "
    "and /settle calls to. Different facilitators support different networks "
    "(CDP = EVM family, Faremeter = Solana, x402.org public = Sepolia only) "
    "with different auth requirements."
)
run.__vs_alternatives__ = (
    "No public x402-facilitator directory exists. Coinbase docs only list CDP; "
    "Faremeter only lists Faremeter; x402.org documents the public facilitator. "
    "Agents currently hardcode a single facilitator and fail silently when it "
    "doesn't support their chain. This tool gives them runtime routing data."
)
run.__example_request__ = {
    "network": "base",
}
run.__example_response__ = {
    "ok": True,
    "network_filter": "base",
    "network_normalized": "eip155:8453",
    "alive": 2,
    "returned": 2,
    "facilitators": [
        {"name": "coinbase-cdp", "owner": "Coinbase", "auth_scheme": "jwt-ed25519",
         "supported_networks": ["eip155:8453", "..."], "alive": True, "latency_ms": 187, "status": 401},
        {"name": "xpay-sh", "owner": "xpay.sh", "auth_scheme": "api-key",
         "supported_networks": ["eip155:8453"], "alive": True, "latency_ms": 320, "status": 200},
    ],
}
