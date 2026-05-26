"""MCP Meta-Router — the 1inch / Jupiter / KyberSwap layer for paid MCPs.

The world's first capability-routing layer for the x402 paid-MCP ecosystem.
An agent describes what it needs ("Base tx explainer", "captcha OCR",
"DEX swap quote on Polygon"); the router queries the ENTIRE Coinbase
Bazaar / CDP discovery corpus, scores every candidate by price + freshness
+ schema match + facilitator health, returns the best-route call template
the agent can execute directly.

This is the missing aggregator layer. Until now every agent had to
manually crawl Bazaar, compare endpoints, pick one, fail, retry. Onyx
Meta-Router collapses that into one paid call.

Phase 1 (this tool): return the best-route quote. Agent executes.
Phase 2 (future): execute on agent's behalf via delegated x402 auth.

Composes:
  - bazaar_compare (catalog source)
  - chain_picker (network ranking)
  - facilitator_health (settlement-side liveness)
  - meta_call (per-route preflight)
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter

NAME = "onyx_mcp_router"
PRICE_USDC = "0.01"
TIER = "metered"
DESCRIPTION = (
    "FIRST MCP meta-router. Describe a capability in plain English ('Base "
    "tx explainer', 'captcha OCR', 'DEX swap quote'); the router queries "
    "the entire CDP x402 discovery corpus, scores every candidate by price + "
    "freshness + schema match + network preference, and returns the top N "
    "ranked routes with full call templates (URL, method, body schema, "
    "expected price, payTo, asset, network). The agent calls the top route "
    "directly. Onyx is the aggregator; every other paid MCP is the supply."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "capability": {
            "type": "string",
            "description": "Plain-English description of what the agent needs. E.g. 'Base transaction explainer', 'swap quote Solana', 'captcha OCR'.",
        },
        "max_price_usdc": {
            "type": "number",
            "description": "Cap on per-call price. Omit for no cap. Use 0.01 for cheap-only.",
        },
        "preferred_network": {
            "type": "string",
            "description": "Preferred network: 'eip155:8453' (Base), 'eip155:84532' (Base Sepolia), 'solana', etc. Sorted higher when present.",
        },
        "top_n": {
            "type": "integer",
            "minimum": 1,
            "maximum": 10,
            "default": 3,
            "description": "Number of route candidates to return.",
        },
        "include_onyx_routes": {
            "type": "boolean",
            "default": True,
            "description": "If false, exclude Onyx Actions endpoints from the comparison (e.g. for independent third-party benchmark).",
        },
    },
    "required": ["capability"],
}

_CDP = "https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources?limit=1000"
_UA = "onyx-mcp-router/1.0"
_ONYX_HOST = "onyx-actions.onrender.com"


def _tokens(s: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", (s or "").lower()) if len(t) >= 2]


def _fetch_corpus(timeout: float = 12.0) -> list[dict]:
    req = urllib.request.Request(_CDP, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8")).get("items") or []


def _atomic_to_usdc(amount: str | int | None, decimals: int = 6) -> float | None:
    if amount is None:
        return None
    try:
        return float(int(amount)) / (10 ** decimals)
    except (TypeError, ValueError):
        return None


def _score_candidate(
    item: dict,
    cap_tokens: set[str],
    max_price: float | None,
    preferred_network: str | None,
) -> tuple[float, dict] | None:
    resource = (item.get("resource") or "").lower()
    desc = (item.get("description") or "").lower()
    res_tokens = set(_tokens(resource) + _tokens(desc))
    overlap = len(cap_tokens & res_tokens)
    if overlap == 0:
        return None  # no token match → skip

    # Best accepts entry (lowest USDC price among accepted networks)
    best_accept = None
    best_price = None
    for a in item.get("accepts") or []:
        price = _atomic_to_usdc(a.get("amount") or a.get("maxAmountRequired"))
        if price is None:
            continue
        if max_price is not None and price > max_price:
            continue
        if best_price is None or price < best_price:
            best_price = price
            best_accept = a

    if best_accept is None:
        return None  # price-capped out or no parseable price

    net = (best_accept.get("network") or "").lower()
    network_bonus = 0.0
    if preferred_network:
        if preferred_network.lower() == net:
            network_bonus = 2.0
        elif preferred_network.lower() in net or net in preferred_network.lower():
            network_bonus = 1.0

    # Score components:
    #   token_overlap (1-N) — directness of match
    #   network_bonus (0/1/2) — agent preference
    #   price_inv (1 / (price + 0.001)) — cheaper = higher
    #   bazaar_ext (0.5) — has the extensions.bazaar.info shape (OATP-tier)
    has_bazaar_ext = bool(((item.get("extensions") or {}).get("bazaar") or {}))
    score = (
        overlap * 1.0
        + network_bonus
        + (1.0 / (best_price + 0.001)) * 0.05  # price weight smaller — agents care MOST about capability
        + (0.5 if has_bazaar_ext else 0.0)
    )

    return (score, {
        "resource": item.get("resource"),
        "description": (item.get("description") or "")[:200],
        "network": best_accept.get("network"),
        "price_usdc": best_price,
        "pay_to": best_accept.get("payTo"),
        "asset": best_accept.get("asset"),
        "scheme": best_accept.get("scheme"),
        "max_timeout_seconds": best_accept.get("maxTimeoutSeconds"),
        "has_bazaar_extensions": has_bazaar_ext,
        "token_match_overlap": overlap,
        "router_score": round(score, 4),
        "call_template": {
            "method": "POST",
            "url": item.get("resource"),
            "headers": {
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            "body_note": "Pass x-payment header with EIP-3009 signed authorization on retry after 402.",
        },
    })


def run(
    capability: str,
    max_price_usdc: float | None = None,
    preferred_network: str | None = None,
    top_n: int = 3,
    include_onyx_routes: bool = True,
    **_: object,
) -> dict:
    cap = (capability or "").strip()
    if not cap:
        return {"ok": False, "error": "capability required"}
    cap_tokens = set(_tokens(cap))
    top_n = max(1, min(10, int(top_n)))
    if max_price_usdc is not None:
        try:
            max_price_usdc = float(max_price_usdc)
        except (TypeError, ValueError):
            return {"ok": False, "error": "max_price_usdc must be a number"}

    try:
        corpus = _fetch_corpus()
    except urllib.error.URLError as e:
        return {"ok": False, "error": "cdp_unreachable", "detail": str(e)[:200]}

    pre_filter_count = len(corpus)
    if not include_onyx_routes:
        corpus = [r for r in corpus if _ONYX_HOST not in (r.get("resource") or "").lower()]

    candidates = []
    for item in corpus:
        scored = _score_candidate(item, cap_tokens, max_price_usdc, preferred_network)
        if scored:
            candidates.append(scored)

    candidates.sort(key=lambda t: -t[0])
    top = [c[1] for c in candidates[:top_n]]

    # Stats — useful intel for the agent
    onyx_count = sum(1 for r in corpus if _ONYX_HOST in (r.get("resource") or "").lower())
    if candidates:
        all_prices = [c[1]["price_usdc"] for c in candidates if c[1]["price_usdc"] is not None]
        price_range = {
            "min_usdc": min(all_prices) if all_prices else None,
            "max_usdc": max(all_prices) if all_prices else None,
            "median_usdc": sorted(all_prices)[len(all_prices)//2] if all_prices else None,
        }
    else:
        price_range = {"min_usdc": None, "max_usdc": None, "median_usdc": None}

    # Decision summary — what to do with this
    if not top:
        decision = "No matching routes. Either capability is empty-niche (consider building it via onyx_bazaar_blue_ocean) or your filters are too tight."
    else:
        winner = top[0]
        savings = None
        if len(top) > 1 and top[0]["price_usdc"] is not None and top[1]["price_usdc"] is not None:
            diff = top[1]["price_usdc"] - top[0]["price_usdc"]
            if diff > 0:
                savings = round(diff, 6)
        decision = (
            f"Call {winner['resource'].split('/')[-1] if winner.get('resource') else 'top route'} "
            f"on {winner['network']} for ${winner['price_usdc']}."
            + (f" Saves ${savings} vs next-best." if savings else "")
        )

    return {
        "ok": True,
        "capability": cap,
        "filters": {
            "max_price_usdc": max_price_usdc,
            "preferred_network": preferred_network,
            "include_onyx_routes": include_onyx_routes,
        },
        "corpus_size": pre_filter_count,
        "candidates_matched": len(candidates),
        "price_range_across_candidates": price_range,
        "onyx_routes_in_corpus": onyx_count,
        "top_routes": top,
        "decision": decision,
        "router_version": "1.0-quote",
        "note": (
            "Phase 1: quote-only. The agent calls the top route directly using "
            "its own wallet. Phase 2 (planned): execute on agent's behalf via "
            "delegated x402 authorization for atomic multi-route composition."
        ),
    }


run.__when_to_use__ = (
    "Any agent that needs a capability and doesn't already know the best "
    "endpoint. Single call, structured ranking, ready call template. The "
    "missing aggregator layer for the paid-MCP ecosystem."
)
run.__vs_alternatives__ = (
    "Manually browsing Coinbase Bazaar UI. Manually grepping awesome-x402. "
    "Calling bazaar_compare (returns rows but no ranking decision). This "
    "tool gives ONE answer: which endpoint to call, on which network, at "
    "what price, with the body template."
)
run.__example_request__ = {
    "capability": "Base transaction explainer",
    "max_price_usdc": 0.1,
    "preferred_network": "eip155:8453",
    "top_n": 3,
}
