"""onyx_preflight — pre-payment safety check for any x402-gated endpoint.

Why now: the exact lane we occupy is getting crowded — x402station runs a
preflight-before-every-payment check (decoys, zombie endpoints, dead services,
price traps) at $0.001/call, rplryan/x402-discovery returns an 0-100 trust
score, Octodamus ships an Ed25519-signed oracle. Onyx's differentiator isn't
"we also check" — it's the posture we run everywhere else in this catalog:
every flag is a disclosed, checkable observation (a status code, a parsed
JSON field, a regex match), never an opaque single-vendor score, and the
whole verdict is Ed25519-signed so a third party can verify it wasn't altered
after the fact.

Sign facts, not judgments: this tool does NOT assert the endpoint is
trustworthy. It reports what it observed (alive/dead/cold, does the 402 body
actually parse as x402 payment-requirements JSON, does payTo look like a real
checksummed address, mainnet vs testnet, an absurd price) and rolls those
disclosed observations into a mechanical OK/WARN/AVOID verdict.

SSRF-hardened: reuses onyx_mcp_health's public-address guard before ever
opening a connection, so this cannot be used to probe internal networks.
Stdlib + urllib only (matches the rest of the probe-style tools in this repo).
"""
from __future__ import annotations

import json
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

from . import _onyx_sign
from . import mcp_health as _mcph

try:
    from eth_utils import is_checksum_address
    _HAS_ETH_UTILS = True
except Exception:  # pragma: no cover - eth_utils ships with eth-account, always present in prod
    _HAS_ETH_UTILS = False

NAME = "onyx_preflight"
PRICE_USDC = "0.02"
TIER = "metered"
DESCRIPTION = (
    "Preflight safety check for an x402-gated endpoint, BEFORE you pay it. Probes "
    "the URL live (~8s timeout), confirms it actually speaks x402 (a proper HTTP "
    "402 with a parseable payment-requirements body — not a decoy demanding payment "
    "in prose), parses the advertised price to human USDC, sanity-checks the payTo "
    "address (0x format + EIP-55 checksum) and network (mainnet vs silently-testnet), "
    "and flags dead/cold/zombie endpoints and absurd price traps. Returns one signed "
    "verdict — OK, WARN, or AVOID — plus every disclosed flag behind it. Sign facts, "
    "not judgments: each flag traces to a checkable rule, not an opaque trust score."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "url": {
            "type": "string",
            "description": "The x402-gated endpoint to preflight (http:// or https://).",
        },
        "timeout_seconds": {
            "type": "number",
            "default": 8.0,
            "description": "Probe timeout in seconds. Clamped to [2, 15].",
        },
    },
    "required": ["url"],
}

_UA = "onyx-preflight/1.0 (+https://onyx-actions.onrender.com)"

# chain-id / alias -> (human chain name, mainnet|testnet). Extend as new
# facilitators advertise new networks.
_NETWORKS = {
    "eip155:8453": ("Base", "mainnet"),
    "base": ("Base", "mainnet"),
    "eip155:84532": ("Base Sepolia", "testnet"),
    "base-sepolia": ("Base Sepolia", "testnet"),
    "eip155:1": ("Ethereum", "mainnet"),
    "eip155:11155111": ("Ethereum Sepolia", "testnet"),
    "solana": ("Solana", "mainnet"),
    "solana-devnet": ("Solana", "testnet"),
}

_ADDR_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")

# Heuristic phrases a decoy uses when it demands payment WITHOUT a real 402 —
# i.e. it wants an agent to just trust prose instead of a machine-checkable header.
_PROSE_PAYMENT_HINTS = (
    "payment required", "please pay", "send usdc", "send payment",
    "pay to continue", "subscribe to access", "insert api key to unlock",
)

_MAJOR_FLAGS = {
    "unreachable", "malformed_402_body", "prose_payment_decoy",
    "zombie_html_only", "invalid_payto_format", "price_trap_absurd",
    "zero_or_negative_price",
}
_MINOR_FLAGS = {
    "cold_start", "testnet_network", "unrecognized_network",
    "bad_payto_checksum", "high_price", "no_402_returns_200",
}


def _atomic_to_usdc(raw, decimals: int = 6):
    try:
        n = int(str(raw))
    except (TypeError, ValueError):
        return None
    return round(n / (10 ** decimals), 6)


def _check_payto(addr: str | None) -> dict:
    if not addr or not isinstance(addr, str):
        return {"present": False, "format_valid": False, "checksum": "n/a"}
    fmt_ok = bool(_ADDR_RE.match(addr))
    if not fmt_ok:
        return {"present": True, "format_valid": False, "checksum": "n/a"}
    checksum = "unchecked"
    if _HAS_ETH_UTILS:
        try:
            if addr == addr.lower() or addr[2:] == addr[2:].upper():
                checksum = "all-lower-or-upper (unchecksummed, not necessarily invalid)"
            elif is_checksum_address(addr):
                checksum = "valid"
            else:
                checksum = "invalid"
        except Exception:
            checksum = "unchecked"
    return {"present": True, "format_valid": True, "checksum": checksum}


def _network_info(network: str | None) -> dict:
    n = (network or "").strip()
    chain, kind = _NETWORKS.get(n.lower(), (None, None))
    return {"raw": n or None, "chain": chain, "kind": kind or ("unknown" if n else "missing")}


def _probe(url: str, timeout: float) -> dict:
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": _UA, "Accept": "application/json, text/html;q=0.5"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(32768)
            return {"status": resp.status, "headers": dict(resp.headers.items()), "body": body,
                    "latency_ms": int((time.perf_counter() - t0) * 1000), "error": None}
    except urllib.error.HTTPError as e:
        try:
            body = e.read(32768)
        except Exception:
            body = b""
        return {"status": e.code, "headers": dict(e.headers.items()) if e.headers else {},
                "body": body, "latency_ms": int((time.perf_counter() - t0) * 1000), "error": None}
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as e:
        return {"status": None, "headers": {}, "body": b"",
                "latency_ms": int((time.perf_counter() - t0) * 1000), "error": str(e)[:200]}


def run(url: str = "", timeout_seconds: float = 8.0, **_: object) -> dict:
    if not (url or "").strip():
        raise ValueError("url is required")
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise ValueError("url must be http:// or https://")
    if not parsed.netloc:
        raise ValueError("url missing host")

    host = parsed.hostname or ""
    pub_ok, pub_reason = _mcph._is_public_address(host)
    if not pub_ok:
        result = {
            "url": url, "alive": False, "x402_valid": False, "price_usdc": None,
            "pay_to": None, "network": None, "flags": ["refused_non_public_address"],
            "verdict": "AVOID", "error": pub_reason,
        }
        return _onyx_sign.attest(result, tool="onyx_preflight")

    timeout = max(2.0, min(float(timeout_seconds), 15.0))
    p = _probe(url, timeout)
    cold = False
    if p["status"] is None and p["error"]:
        # one retry at 2x timeout to distinguish a truly dead host from a cold-starting one
        p2 = _probe(url, min(timeout * 2, 20.0))
        if p2["status"] is not None:
            p = p2
            cold = True

    flags: list[str] = []
    if cold:
        flags.append("cold_start")

    alive = p["status"] is not None
    if not alive:
        flags.append("unreachable")
        result = {
            "url": url, "alive": False, "http_status": None, "x402_valid": False,
            "price_usdc": None, "pay_to": None, "network": None, "flags": flags,
            "verdict": "AVOID", "latency_ms": p["latency_ms"], "error": p["error"],
        }
        return _onyx_sign.attest(result, tool="onyx_preflight")

    status = p["status"]
    ctype = (p["headers"].get("Content-Type") or "").lower()
    body_text = p["body"].decode("utf-8", "replace")

    x402_valid = False
    price_usdc = None
    pay_to = None
    accepts = None
    payto_check = {"present": False, "format_valid": False, "checksum": "n/a"}
    net_info = {"raw": None, "chain": None, "kind": "missing"}

    if status == 402:
        parsed_body = None
        if "json" in ctype or body_text.strip().startswith("{"):
            try:
                parsed_body = json.loads(body_text)
            except Exception:
                parsed_body = None
        if isinstance(parsed_body, dict):
            accepts = parsed_body.get("accepts")
        if isinstance(accepts, list) and accepts:
            x402_valid = True
            # prefer a Base entry (mainnet or sepolia) if present, else the first offer
            chosen = next(
                (a for a in accepts if isinstance(a, dict)
                 and str(a.get("network", "")).lower() in ("eip155:8453", "base", "eip155:84532", "base-sepolia")),
                accepts[0],
            )
            if isinstance(chosen, dict):
                network = chosen.get("network")
                pay_to = chosen.get("payTo")
                price_usdc = _atomic_to_usdc(chosen.get("maxAmountRequired"))
                payto_check = _check_payto(pay_to)
                net_info = _network_info(network)
        else:
            flags.append("malformed_402_body")
            if "html" in ctype and parsed_body is None:
                flags.append("zombie_html_only")
    else:
        lower_body = body_text.lower()
        if any(h in lower_body for h in _PROSE_PAYMENT_HINTS):
            flags.append("prose_payment_decoy")
        if status == 200 and "html" in ctype:
            flags.append("no_402_returns_200")

    if payto_check.get("present") and not payto_check.get("format_valid"):
        flags.append("invalid_payto_format")
    if payto_check.get("checksum") == "invalid":
        flags.append("bad_payto_checksum")
    if net_info.get("kind") == "testnet":
        flags.append("testnet_network")
    elif net_info.get("kind") == "unknown":
        flags.append("unrecognized_network")
    if price_usdc is not None:
        if price_usdc <= 0:
            flags.append("zero_or_negative_price")
        elif price_usdc > 50:
            flags.append("price_trap_absurd")
        elif price_usdc > 5:
            flags.append("high_price")

    if any(f in _MAJOR_FLAGS for f in flags) or (status == 402 and not x402_valid):
        verdict = "AVOID"
    elif any(f in _MINOR_FLAGS for f in flags):
        verdict = "WARN"
    else:
        verdict = "OK"

    result = {
        "url": url,
        "alive": alive,
        "http_status": status,
        "x402_valid": x402_valid,
        "price_usdc": price_usdc,
        "pay_to": pay_to,
        "pay_to_check": payto_check,
        "network": net_info,
        "flags": flags,
        "verdict": verdict,
        "latency_ms": p["latency_ms"],
        "accepts_count": len(accepts) if isinstance(accepts, list) else 0,
        "method": (
            "Live HTTP GET, no payment made. A 402 response body is parsed per the "
            "x402 spec (top-level 'accepts' array); payTo is checked for 0x-format + "
            "EIP-55 checksum; network is mapped against known Base/Ethereum/Solana chain "
            "identifiers. Non-402 responses are scanned for prose payment-demand phrasing "
            "(a decoy signal — a real x402 seller returns a machine-checkable 402, not text)."
        ),
    }
    return _onyx_sign.attest(result, tool="onyx_preflight")


run.__when_to_use__ = (
    "An agent is about to call an unfamiliar x402-gated endpoint and wants to know, "
    "BEFORE spending USDC, whether it is alive, actually speaks x402 correctly, and "
    "is not a decoy, dead service, or price trap."
)
run.__vs_alternatives__ = (
    "x402station and rplryan/x402-discovery run a similar class of preflight check but "
    "return an unsigned result from a single vendor's opinion. Onyx returns the same "
    "check as a disclosed, Ed25519-signed verdict — every flag traces to a checkable "
    "rule (a status code, a parsed field, a regex), not an opaque trust score, and "
    "anyone can independently re-verify the signature."
)
run.__example_request__ = {"url": "https://onyx-actions.onrender.com/mcp/", "timeout_seconds": 8}
run.__example_response__ = {
    "url": "https://example.com/paid-endpoint", "alive": True, "http_status": 402,
    "x402_valid": True, "price_usdc": 0.02, "pay_to": "0x1234...abcd",
    "network": {"raw": "eip155:8453", "chain": "Base", "kind": "mainnet"},
    "flags": [], "verdict": "OK",
}


def register(app) -> None:
    """Attach GET /preflight?url=... to the FastAPI app (free, rate-limited teaser
    of the paid onyx_preflight MCP tool — same engine, capped per IP so it can't be
    used to bulk-scrape the metered tool for free).

    Usage in server_http.py:
        from tools_pkg import preflight_check; preflight_check.register(app)
    """
    from fastapi import Header
    from fastapi.responses import JSONResponse

    @app.get("/preflight", include_in_schema=False)
    async def _preflight_get(url: str = "", timeout_seconds: float = 8.0,
                              x_forwarded_for: str = Header(default="")):
        from . import _ratelimit
        if not (url or "").strip():
            return JSONResponse({"ok": False, "error": "url query param required, e.g. /preflight?url=https://..."})
        ok, _rem = _ratelimit.allow("preflight:" + _ratelimit.client_ip(x_forwarded_for),
                                     limit=10, window_sec=3600)
        if not ok:
            return JSONResponse({
                "ok": False, "rate_limited": True,
                "error": "Free preflight limit reached (10/hour per IP). For unmetered "
                         "volume call the signed onyx_preflight tool over x402.",
            })
        try:
            return JSONResponse(run(url=url, timeout_seconds=timeout_seconds))
        except ValueError as ve:
            return JSONResponse({"ok": False, "error": str(ve)})
        except Exception as e:
            return JSONResponse({"ok": False, "error": f"preflight failed: {str(e)[:160]}"})
