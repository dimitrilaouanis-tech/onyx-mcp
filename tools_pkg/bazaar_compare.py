"""Compare paid agent tools across the x402 ecosystem.

Searches the public Coinbase Bazaar (via Onyx's leaderboard mirror), filters
by keyword + network, ranks by price / volume / unique payers / freshness,
and returns side-by-side comparison rows agents can use to choose a tool.

Stdlib-only HTTP. Free tier — no payment, no API key.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

NAME = "onyx_bazaar_compare"
PRICE_USDC = "0"
TIER = "free"
DESCRIPTION = (
    "Side-by-side comparison of paid agent tools across the x402 ecosystem. "
    "Filter by keyword (e.g. 'captcha', 'tx_explainer', 'aml', 'sms', 'browser') "
    "and network ('Base' / 'Solana' / etc.), rank by price, 30-day call volume, "
    "or unique payer count, and get cheapest/most-used picks. Reads Coinbase "
    "Bazaar via the public Onyx mirror — refreshed every 15 minutes. Free tier."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "Keyword to match in domain, resource URL, or description (case-insensitive). Empty string = no filter.",
        },
        "network": {
            "type": "string",
            "description": "Filter by network: 'Base', 'Solana', 'Polygon', etc. Omit for all networks.",
        },
        "sort_by": {
            "type": "string",
            "enum": ["price_asc", "volume_desc", "payers_desc", "freshness_desc"],
            "default": "volume_desc",
            "description": "Ranking order. price_asc = cheapest first; volume_desc = most-called first; payers_desc = most unique buyers; freshness_desc = most-recently-called first.",
        },
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 50,
            "default": 10,
        },
    },
    "required": ["query"],
}

_BAZAAR_URL = "https://onyx-actions.onrender.com/bazaar.json"


def _fetch_bazaar(view: str = "volume", limit: int = 500, timeout: float = 12.0) -> list[dict]:
    qs = urllib.parse.urlencode({"view": view, "limit": limit})
    url = f"{_BAZAAR_URL}?{qs}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "onyx-bazaar-compare/1.0",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("rows", []) if isinstance(data, dict) else []


def _parse_price_usdc(price_str: str) -> float | None:
    if not isinstance(price_str, str):
        return None
    s = price_str.replace("$", "").replace("USDC", "").replace("USD", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _match(row: dict, query_lc: str, network: str | None) -> bool:
    if network and (row.get("network") or "").lower() != network.lower():
        return False
    if not query_lc:
        return True
    hay = " ".join([
        row.get("resource") or "",
        row.get("domain") or "",
        row.get("description") or "",
    ]).lower()
    return query_lc in hay


def _shape_row(row: dict) -> dict:
    return {
        "resource": row.get("resource"),
        "domain": row.get("domain"),
        "price": row.get("price"),
        "price_usdc": _parse_price_usdc(row.get("price") or ""),
        "network": row.get("network"),
        "calls_30d": row.get("calls_30d") or 0,
        "payers_30d": row.get("payers_30d") or 0,
        "last_called": row.get("last_called"),
        "description": (row.get("description") or "")[:200],
        "quality_score": row.get("quality_score"),
    }


def run(
    query: str = "",
    network: str | None = None,
    sort_by: str = "volume_desc",
    limit: int = 10,
    **_: object,
) -> dict:
    query_lc = (query or "").strip().lower()
    limit = max(1, min(50, int(limit)))

    try:
        all_rows = _fetch_bazaar(view="volume", limit=500)
    except urllib.error.URLError as e:
        return {
            "ok": False,
            "query": query, "network": network, "sort_by": sort_by,
            "error": f"bazaar mirror unreachable: {str(e)[:200]}",
            "results": [], "total_matches": 0,
        }

    matches = [r for r in all_rows if _match(r, query_lc, network)]
    shaped = [_shape_row(r) for r in matches]

    def _sort_key(r: dict):
        if sort_by == "price_asc":
            return (r["price_usdc"] if r["price_usdc"] is not None else 1e9,)
        if sort_by == "payers_desc":
            return (-(r["payers_30d"] or 0),)
        if sort_by == "freshness_desc":
            return (r["last_called"] or "",)[:1] and (
                tuple([-1 * ord(c) for c in (r["last_called"] or "")[:25]])
            ) or ()
        return (-(r["calls_30d"] or 0),)

    shaped.sort(key=_sort_key)
    if sort_by == "freshness_desc":
        shaped.sort(key=lambda r: r["last_called"] or "", reverse=True)

    top = shaped[:limit]

    # Quick picks
    with_price = [r for r in shaped if r["price_usdc"] is not None]
    cheapest = min(with_price, key=lambda r: r["price_usdc"]) if with_price else None
    most_used = max(shaped, key=lambda r: r["calls_30d"] or 0) if shaped else None
    most_buyers = max(shaped, key=lambda r: r["payers_30d"] or 0) if shaped else None

    return {
        "ok": True,
        "query": query,
        "network": network,
        "sort_by": sort_by,
        "total_matches": len(matches),
        "returned": len(top),
        "cheapest": cheapest,
        "most_called": most_used,
        "most_unique_buyers": most_buyers,
        "results": top,
    }


run.__when_to_use__ = (
    "An agent has a capability need ('I need to screen an EVM address for AML risk') "
    "and wants to pick the best-priced or most-trusted x402 endpoint without "
    "manually crawling Bazaar."
)
run.__vs_alternatives__ = (
    "Coinbase Bazaar UI is browsable but not API-queryable as a price comparison. "
    "x402scan indexes endpoints but doesn't rank by economic metrics. This tool "
    "is the only programmatic price/volume/buyer comparison across the x402 catalog."
)
run.__example_request__ = {
    "query": "tx_explainer",
    "network": "Base",
    "sort_by": "price_asc",
    "limit": 5,
}
run.__example_response__ = {
    "ok": True,
    "query": "tx_explainer",
    "network": "Base",
    "sort_by": "price_asc",
    "total_matches": 4,
    "returned": 4,
    "cheapest": {"resource": "...", "price_usdc": 0.005},
    "most_called": {"resource": "...", "calls_30d": 15234},
    "results": [
        {"resource": "...", "domain": "...", "price": "$0.005", "price_usdc": 0.005,
         "network": "Base", "calls_30d": 410, "payers_30d": 12, "description": "..."},
    ],
}
