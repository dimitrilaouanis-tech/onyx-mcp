"""Market pulse — unified market state for paid x402 MCP economy.

Composes arb_finder + blue_ocean + indexer_health into a single Bloomberg-
terminal-style snapshot:

  - Top 10 priced services by CDP discovery + price quartile
  - Blue-ocean niches (zero peers)
  - Saturated niches (5+ peers — avoid)
  - Onyx pricing audit: which of our tools are over/under market
  - Recent additions to the corpus (heuristic by last-updated)
  - Per-network split (Base mainnet vs Sepolia vs Solana)

Built for paid-MCP builders + competitive intel teams + anyone trying to
understand the shape of the x402 economy in one call.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from collections import Counter

NAME = "onyx_market_pulse"
PRICE_USDC = "0.02"
TIER = "metered"
DESCRIPTION = (
    "One-call market snapshot of the paid x402 MCP economy. Returns top "
    "services by CDP visibility, blue-ocean niches with zero peers, "
    "saturated niches (5+ peers), Onyx pricing audit (over/under market "
    "by tool), and per-network split. Bloomberg-terminal for the agentic "
    "economy. Use for competitive intel, pricing decisions, niche selection."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "compare_onyx_prices": {
            "type": "boolean",
            "default": True,
            "description": "If true, include the Onyx pricing audit (our prices vs market median for matching capabilities).",
        },
        "blue_ocean_keywords": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional candidate capability tokens to check for blue-ocean status. Default = curated baseline of ~30 high-frequency agent capabilities.",
        },
    },
}

_CDP = "https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources?limit=1000"
_UA = "onyx-market-pulse/1.0"
_ONYX_HOST = "onyx-actions.onrender.com"

# Onyx's current price table (kept in sync with tools_pkg/*.py PRICE_USDC fields)
_ONYX_PRICES_BY_CAPABILITY = {
    "tx_explainer": 0.05,
    "tx_simulator": 0.10,
    "tx_decode": 0.002,
    "token_risk_scan": 0.25,
    "token_risk": 0.25,
    "token_metadata": 0.001,
    "contract_verify": 0.002,
    "swap_quote": 0.002,
    "bridge_quote": 0.003,
    "dex_pair_lookup": 0.0015,
    "event_logs": 0.003,
    "wallet_activity": 0.002,
    "jupiter_quote": 0.001,
    "ens_resolve": 0.0008,
    "aml_screen": 0.01,
    "captcha": 0.003,
    "url_text": 0.001,
    "agent_workflow": 0.020,
    "agent_id": 0.001,
    "agent_audit_trail": 0.05,
    "agent_budget_tracker": 0.0008,
    "research_intel": 0.05,
    "paper_synthesis": 0.03,
    "partnership_check": 0.02,
    "mcp_router": 0.01,
    "kya_verify": 0.001,
    "oai_lookup": 0.001,
    "arb_finder": 0.003,
    "capability_bundle": 0.02,
    "market_pulse": 0.02,
}

# Curated baseline of high-frequency agent capabilities for blue-ocean check
_BASELINE_CAPS = [
    "tx_explainer", "tx_simulator", "tx_decode", "token_risk", "token_metadata",
    "swap_quote", "bridge_quote", "ens", "contract_verify", "wallet_activity",
    "captcha", "browser", "screenshot", "dns", "whois", "email_validate",
    "ip_geo", "html_meta", "robots", "url_text",
    "research", "arxiv", "paper", "oauth_audit", "facilitator_health",
    "kya", "ar1", "oai", "agent_id", "aml", "audit_trail",
    "image_classify", "audio_transcribe", "translate", "summarize",
    "github_pr", "github_issue", "slack", "discord", "twitter",
    "lending_rate", "vault_apr", "perp_position", "funding_rate",
]


def _tokens(s: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", (s or "").lower()) if len(t) >= 3}


def _fetch(timeout: float = 12.0) -> list[dict]:
    req = urllib.request.Request(_CDP, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8")).get("items") or []


def _price_usdc(item: dict) -> float | None:
    for a in item.get("accepts") or []:
        amt = a.get("amount") or a.get("maxAmountRequired")
        if amt is None:
            continue
        try:
            return float(int(amt)) / 1e6
        except (TypeError, ValueError):
            continue
    return None


def _domain_of(resource: str) -> str:
    if "://" in resource:
        return resource.split("://")[1].split("/")[0]
    return resource


def _count_cap_in_corpus(items: list[dict], cap: str) -> tuple[int, list[float]]:
    """Returns (peer_count, prices) for items matching capability (Onyx excluded)."""
    cap_lc = cap.lower()
    peers, prices = 0, []
    for it in items:
        res = (it.get("resource") or "")
        if _ONYX_HOST in res.lower():
            continue
        hay = (res + " " + (it.get("description") or "")).lower()
        if cap_lc in hay:
            peers += 1
            p = _price_usdc(it)
            if p is not None:
                prices.append(p)
    return peers, prices


def run(
    compare_onyx_prices: bool = True,
    blue_ocean_keywords: list[str] | None = None,
    **_: object,
) -> dict:
    try:
        items = _fetch()
    except urllib.error.URLError as e:
        return {"ok": False, "error": "cdp_unreachable", "detail": str(e)[:200]}

    corpus_size = len(items)

    # Per-network split
    networks: Counter = Counter()
    domains: Counter = Counter()
    all_prices: list[float] = []
    for it in items:
        for a in it.get("accepts") or []:
            n = a.get("network") or "?"
            networks[n] += 1
        domains[_domain_of(it.get("resource") or "")] += 1
        p = _price_usdc(it)
        if p is not None:
            all_prices.append(p)
    all_prices.sort()

    # Price quartiles
    def _percentile(arr: list[float], p: float) -> float | None:
        if not arr: return None
        idx = max(0, min(len(arr) - 1, int(p * len(arr))))
        return arr[idx]

    price_quartiles = {
        "min": min(all_prices) if all_prices else None,
        "p25": _percentile(all_prices, 0.25),
        "p50": _percentile(all_prices, 0.50),
        "p75": _percentile(all_prices, 0.75),
        "max": max(all_prices) if all_prices else None,
        "count_priced": len(all_prices),
    }

    # Blue ocean + saturated audit
    seeds = blue_ocean_keywords or _BASELINE_CAPS
    blue_ocean: list[dict] = []
    saturated: list[dict] = []
    thin: list[dict] = []
    for cap in seeds:
        peers, prices = _count_cap_in_corpus(items, cap)
        median_price = sorted(prices)[len(prices)//2] if prices else None
        entry = {"capability": cap, "peers": peers, "median_peer_price_usdc": median_price}
        if peers == 0:
            blue_ocean.append(entry)
        elif peers >= 5:
            saturated.append(entry)
        elif peers >= 1:
            thin.append(entry)

    # Onyx pricing audit
    pricing_audit: list[dict] = []
    if compare_onyx_prices:
        for cap, onyx_price in _ONYX_PRICES_BY_CAPABILITY.items():
            peers, prices = _count_cap_in_corpus(items, cap)
            if not prices:
                pricing_audit.append({
                    "capability": cap,
                    "onyx_price_usdc": onyx_price,
                    "peers": peers,
                    "verdict": "blue_ocean_or_invisible — set price by value not market",
                })
                continue
            median = sorted(prices)[len(prices)//2]
            cheapest = min(prices)
            if onyx_price > cheapest * 2:
                verdict = f"OVERPRICED — {round((onyx_price/cheapest - 1)*100)}% above cheapest peer ${cheapest}"
            elif onyx_price < cheapest * 0.5:
                verdict = f"UNDERPRICED — {round((1 - onyx_price/median)*100)}% below median ${median} (room to raise)"
            else:
                verdict = "in_range — within 0.5x-2x of cheapest peer"
            pricing_audit.append({
                "capability": cap,
                "onyx_price_usdc": onyx_price,
                "peers": peers,
                "cheapest_peer_price_usdc": cheapest,
                "median_peer_price_usdc": median,
                "verdict": verdict,
            })

    # Summary card
    over = [a for a in pricing_audit if a.get("verdict", "").startswith("OVERPRICED")]
    under = [a for a in pricing_audit if a.get("verdict", "").startswith("UNDERPRICED")]

    summary = (
        f"x402 corpus: {corpus_size} routes across {len(networks)} networks "
        f"(top: {networks.most_common(3)}). Price range across priced routes: "
        f"${price_quartiles['min']:.4f} — ${price_quartiles['max']:.4f} "
        f"(median ${price_quartiles['p50']:.4f}). "
        f"Onyx pricing audit: {len(over)} overpriced, {len(under)} underpriced, "
        f"{len(blue_ocean)} blue-ocean caps. Saturated caps to avoid building in: {len(saturated)}."
    )

    return {
        "ok": True,
        "corpus_size": corpus_size,
        "networks": dict(networks.most_common(10)),
        "top_domains": dict(domains.most_common(10)),
        "price_quartiles": price_quartiles,
        "blue_ocean": blue_ocean[:20],
        "thin_niches": thin[:15],
        "saturated_niches": saturated[:10],
        "pricing_audit": pricing_audit,
        "actions": {
            "overpriced_to_drop": [a["capability"] for a in over],
            "underpriced_to_raise": [a["capability"] for a in under],
            "blue_ocean_to_claim": [b["capability"] for b in blue_ocean][:5],
        },
        "summary": summary,
    }


run.__when_to_use__ = (
    "Monthly competitive intel review. Pricing decision before launching a "
    "new tool. Niche selection. Strategic snapshot for a deck or grant."
)
run.__vs_alternatives__ = (
    "Manually running arb_finder + blue_ocean + price-percentile math by hand "
    "across 30 capabilities = 30 calls + spreadsheet. This is one call, "
    "structured output."
)
run.__example_request__ = {"compare_onyx_prices": True}
