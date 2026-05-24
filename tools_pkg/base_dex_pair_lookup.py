"""Base DEX pair lookup — all pairs for a token across Base DEXes.

Queries DexScreener (free, no auth) for every pair where the input token
appears on Base. Returns per-pair: DEX, price USD, 24h volume, liquidity,
price change %, fees. Sorts by liquidity desc.

Composes with onyx_base_swap_quote (find best route after seeing where
liquidity is) and onyx_base_token_risk_scan (verify token isn't a rug
before trading the most-liquid pool).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

NAME = "onyx_base_dex_pair_lookup"
PRICE_USDC = "0.0015"
TIER = "metered"
DESCRIPTION = (
    "Every DEX pair for a Base token: DEX name, price USD, 24h volume, "
    "liquidity USD, price-change percentages (5m/1h/6h/24h), pool fees. "
    "Sorted by liquidity. Backed by DexScreener (free). Use to find where "
    "a token is actually trading before routing a swap or assessing rug "
    "risk via volume/liquidity ratios."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "token_address": {
            "type": "string",
            "description": "Token contract address on Base mainnet (0x...).",
        },
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 30,
            "default": 10,
            "description": "Max pairs to return (sorted by liquidity desc).",
        },
    },
    "required": ["token_address"],
}

_DEX_SCREENER = "https://api.dexscreener.com/latest/dex/tokens"
_UA = "onyx-base-dex-pair-lookup/1.0"


def _hex_addr(s: str) -> bool:
    s = (s or "").strip()
    return s.startswith("0x") and len(s) == 42


def run(token_address: str, limit: int = 10, **_: object) -> dict:
    if not _hex_addr(token_address):
        return {"ok": False, "error": "token_address must be 0x... 20-byte hex"}
    limit = max(1, min(30, int(limit)))

    url = f"{_DEX_SCREENER}/{token_address.lower()}"
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            d = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"dexscreener_http_{e.code}"}
    except urllib.error.URLError as e:
        return {"ok": False, "error": "dexscreener_unreachable", "detail": str(e)[:200]}

    all_pairs = d.get("pairs") or []
    # Filter to Base chain only
    base_pairs = [p for p in all_pairs if (p.get("chainId") or "").lower() == "base"]

    def _liquidity(p: dict) -> float:
        return float((p.get("liquidity") or {}).get("usd") or 0)

    base_pairs.sort(key=_liquidity, reverse=True)
    top = base_pairs[:limit]

    shaped = []
    total_liq = 0.0
    total_vol_24h = 0.0
    for p in top:
        liq = _liquidity(p)
        vol_24h = float((p.get("volume") or {}).get("h24") or 0)
        total_liq += liq
        total_vol_24h += vol_24h
        shaped.append({
            "dex": p.get("dexId"),
            "pair_address": p.get("pairAddress"),
            "base": (p.get("baseToken") or {}).get("symbol"),
            "quote": (p.get("quoteToken") or {}).get("symbol"),
            "price_usd": p.get("priceUsd"),
            "liquidity_usd": liq,
            "volume_24h_usd": vol_24h,
            "volume_6h_usd": (p.get("volume") or {}).get("h6"),
            "txns_24h": (p.get("txns") or {}).get("h24"),
            "price_change_5m": (p.get("priceChange") or {}).get("m5"),
            "price_change_1h": (p.get("priceChange") or {}).get("h1"),
            "price_change_24h": (p.get("priceChange") or {}).get("h24"),
            "url": p.get("url"),
        })

    # Quick health signals
    most_liquid = shaped[0] if shaped else None
    vol_liq_ratio = (total_vol_24h / total_liq) if total_liq > 0 else None
    health = None
    if vol_liq_ratio is not None:
        if vol_liq_ratio > 10:
            health = "very_high_turnover — possible wash trading or momentum"
        elif vol_liq_ratio > 2:
            health = "healthy_trading"
        elif vol_liq_ratio > 0.1:
            health = "low_activity"
        else:
            health = "dormant — illiquid, swaps may have high slippage"

    return {
        "ok": True,
        "token_address": token_address.lower(),
        "total_pairs_on_base": len(base_pairs),
        "returned": len(shaped),
        "total_liquidity_usd": round(total_liq, 2),
        "total_volume_24h_usd": round(total_vol_24h, 2),
        "volume_liquidity_ratio": round(vol_liq_ratio, 3) if vol_liq_ratio is not None else None,
        "health_signal": health,
        "most_liquid_pair": most_liquid,
        "pairs": shaped,
    }


run.__when_to_use__ = (
    "Before swapping any Base ERC-20, check where the token actually trades. "
    "Tokens with low total liquidity → high slippage. Tokens with sky-high "
    "volume:liquidity ratios → possible wash trading."
)
run.__vs_alternatives__ = (
    "Web DexScreener UI is browse-only. CoinGecko has API but rate-limited "
    "and slower data. DexScreener API is real-time, no auth, no rate limit."
)
run.__example_request__ = {
    "token_address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    "limit": 5,
}
