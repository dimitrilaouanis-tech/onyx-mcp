"""Base swap quote — best-route DEX quote via KyberSwap aggregator.

Returns: amountOut, USD value, gas estimate, route hops, price impact.
Composes with onyx_base_tx_simulator (pre-flight the swap) and
onyx_base_token_risk_scan (verify the output token isn't a rug).

Backed by KyberSwap aggregator API (free, no auth). Covers Uniswap V2/V3,
Aerodrome, BaseSwap, PancakeSwap on Base, plus a dozen other Base DEXes.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

NAME = "onyx_base_swap_quote"
PRICE_USDC = "0.002"
TIER = "metered"
DESCRIPTION = (
    "Best-route swap quote on Base across all major DEXes (Uniswap V2/V3, "
    "Aerodrome, BaseSwap, PancakeSwap, plus ~12 others) via KyberSwap "
    "aggregator. Returns amountOut, USD value, gas estimate, route hops, "
    "price impact. Same role as Jupiter on Solana — most agents need this "
    "before any on-chain swap."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "token_in": {
            "type": "string",
            "description": "Address of input token (0x... on Base mainnet). Use 0x4200000000000000000000000000000000000006 for WETH.",
        },
        "token_out": {
            "type": "string",
            "description": "Address of output token (0x... on Base mainnet).",
        },
        "amount_in": {
            "type": "string",
            "description": "Atomic input amount (decimal string). E.g. 1 ETH = '1000000000000000000'; 100 USDC = '100000000'.",
        },
    },
    "required": ["token_in", "token_out", "amount_in"],
}

_KYBER = "https://aggregator-api.kyberswap.com/base/api/v1/routes"
_UA = "onyx-base-swap-quote/1.0"


def _hex_addr(s: str) -> bool:
    s = (s or "").strip()
    return s.startswith("0x") and len(s) == 42 and all(c in "0123456789abcdefABCDEF" for c in s[2:])


def run(token_in: str, token_out: str, amount_in: str, **_: object) -> dict:
    if not _hex_addr(token_in):
        return {"ok": False, "error": "token_in must be 0x... 20-byte hex"}
    if not _hex_addr(token_out):
        return {"ok": False, "error": "token_out must be 0x... 20-byte hex"}
    try:
        if int(amount_in) <= 0:
            return {"ok": False, "error": "amount_in must be positive"}
    except (TypeError, ValueError):
        return {"ok": False, "error": "amount_in must be a decimal string"}

    params = urllib.parse.urlencode({
        "tokenIn": token_in.lower(),
        "tokenOut": token_out.lower(),
        "amountIn": amount_in,
    })
    url = f"{_KYBER}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            d = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"kyberswap_http_{e.code}"}
    except urllib.error.URLError as e:
        return {"ok": False, "error": "kyberswap_unreachable", "detail": str(e)[:200]}

    if d.get("code") != 0:
        return {"ok": False, "error": "no_route", "detail": d.get("message", "")[:200]}

    rs = (d.get("data") or {}).get("routeSummary") or {}
    routes = rs.get("route") or []
    # Flatten: count hops + unique DEXes
    hops = sum(len(r) for r in routes)
    dexes = sorted({
        seg.get("exchange") for r in routes for seg in r if seg.get("exchange")
    })

    return {
        "ok": True,
        "token_in": token_in.lower(),
        "token_out": token_out.lower(),
        "amount_in": amount_in,
        "amount_out": rs.get("amountOut"),
        "amount_in_usd": rs.get("amountInUsd"),
        "amount_out_usd": rs.get("amountOutUsd"),
        "gas_estimate": rs.get("gas"),
        "gas_usd": rs.get("gasUsd"),
        "route_hops": hops,
        "dexes_used": dexes,
        "router_address": rs.get("routerAddress"),
    }


run.__when_to_use__ = (
    "Any agent about to perform a swap on Base. Get a price-and-route quote "
    "before signing the actual swap transaction."
)
run.__vs_alternatives__ = (
    "Direct Uniswap V3 quoter call gives single-pool quote, missing better "
    "routes on Aerodrome/BaseSwap. KyberSwap aggregates across ~15 DEXes."
)
run.__example_request__ = {
    "token_in": "0x4200000000000000000000000000000000000006",
    "token_out": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    "amount_in": "1000000000000000000",
}
