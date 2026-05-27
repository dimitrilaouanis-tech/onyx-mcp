"""Arb finder — price arbitrage between Onyx Actions and peer x402 services.

For any capability we ship, this tool finds peer endpoints offering the same
or adjacent capability on the CDP x402 discovery corpus, computes the price
delta, and produces a one-line pitch: "Onyx is X% cheaper than peer Y on Z."

Use cases:
  - Competitive intelligence (which tools are commoditized vs differentiated)
  - Marketing copy generation (the pitch line is the output)
  - Pricing strategy (raise where we're free, drop where overpriced)
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

NAME = "onyx_arb_finder"
PRICE_USDC = "0.003"
TIER = "metered"
DESCRIPTION = (
    "Price arbitrage between Onyx Actions and peer x402 services. For any "
    "capability (e.g. 'tx_explainer', 'captcha'), queries the full CDP "
    "discovery corpus, identifies matching peer endpoints, computes price "
    "delta vs the Onyx native tool, and produces a one-line competitive "
    "pitch ('Onyx is 50% cheaper than OATP at $0.05 vs $0.10'). Use for "
    "competitive intel, marketing copy, or pricing decisions."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "capability": {
            "type": "string",
            "description": "Capability keyword to compare. E.g. 'tx_explainer', 'token_risk', 'captcha', 'swap_quote'.",
        },
        "onyx_price_usdc": {
            "type": "number",
            "description": "Onyx's price for this capability. Used as the comparison anchor. Default 0 = treat Onyx as if-we-shipped-free.",
        },
        "network": {
            "type": "string",
            "description": "Optional network filter: 'base', 'solana', 'eip155:8453'. Empty = all.",
        },
        "max_peers": {
            "type": "integer",
            "minimum": 1,
            "maximum": 30,
            "default": 8,
        },
    },
    "required": ["capability"],
}

_CDP = "https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources?limit=1000"
_UA = "onyx-arb-finder/1.0"
_ONYX_HOST = "onyx-actions.onrender.com"


def _tokens(s: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", (s or "").lower()) if len(t) >= 3}


def _fetch(timeout: float = 12.0) -> list[dict]:
    req = urllib.request.Request(_CDP, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8")).get("items") or []


def _net_match(item: dict, network: str) -> bool:
    if not network:
        return True
    nl = network.lower()
    nets = [(a.get("network") or "").lower() for a in (item.get("accepts") or [])]
    if nl == "base":
        return any(n in ("eip155:8453", "base") for n in nets)
    if nl == "solana":
        return any(n.startswith("solana") for n in nets)
    return any(nl in n or n in nl for n in nets)


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


def run(
    capability: str,
    onyx_price_usdc: float = 0.0,
    network: str = "",
    max_peers: int = 8,
    **_: object,
) -> dict:
    cap = (capability or "").strip().lower()
    if not cap:
        return {"ok": False, "error": "capability required"}
    cap_tokens = _tokens(cap)
    try:
        onyx_price_usdc = float(onyx_price_usdc)
    except (TypeError, ValueError):
        onyx_price_usdc = 0.0
    max_peers = max(1, min(30, int(max_peers)))

    try:
        items = _fetch()
    except urllib.error.URLError as e:
        return {"ok": False, "error": "cdp_unreachable", "detail": str(e)[:200]}

    matches: list[dict] = []
    for it in items:
        resource = (it.get("resource") or "")
        if _ONYX_HOST in resource.lower():
            continue  # skip Onyx itself
        if not _net_match(it, network):
            continue
        hay = (resource + " " + (it.get("description") or "")).lower()
        hay_tokens = _tokens(hay)
        overlap = len(cap_tokens & hay_tokens)
        if overlap == 0:
            continue
        price = _price_usdc(it)
        if price is None:
            continue
        matches.append({
            "resource": resource,
            "domain": resource.split("://")[-1].split("/")[0] if "://" in resource else "",
            "price_usdc": price,
            "match_overlap": overlap,
            "description": (it.get("description") or "")[:200],
        })

    matches.sort(key=lambda m: (m["price_usdc"], -m["match_overlap"]))
    top = matches[:max_peers]

    if not top:
        return {
            "ok": True,
            "capability": cap,
            "network": network or "all",
            "onyx_price_usdc": onyx_price_usdc,
            "peers_matched": 0,
            "verdict": "blue_ocean — no priced peer found in CDP corpus for this capability",
            "pitch": f"Onyx ships '{cap}' uncontested — no peer on CDP discovery offers it. First-mover position.",
        }

    cheapest_peer = top[0]
    avg_peer = sum(m["price_usdc"] for m in top) / len(top)

    if onyx_price_usdc <= 0:
        delta_pct = None
        verdict = f"onyx_free — peers charge avg ${avg_peer:.4f}, we ship free. Convert to paid at $${avg_peer*0.5:.4f} (half-market)?"
        pitch = f"Onyx ships '{cap}' FREE while {len(top)} peers charge avg ${avg_peer:.4f}. Cheapest peer: {cheapest_peer['domain']} at ${cheapest_peer['price_usdc']:.4f}."
    elif onyx_price_usdc < cheapest_peer["price_usdc"]:
        delta_pct = round(100 * (cheapest_peer["price_usdc"] - onyx_price_usdc) / cheapest_peer["price_usdc"], 1)
        verdict = f"onyx_cheaper — under cheapest peer by {delta_pct}%"
        pitch = (
            f"Onyx '{cap}' is {delta_pct}% cheaper than {cheapest_peer['domain']} "
            f"(${onyx_price_usdc:.4f} vs ${cheapest_peer['price_usdc']:.4f}). "
            f"Pitch to agents: route to Onyx for same capability + native AR-1 receipt."
        )
    elif onyx_price_usdc > cheapest_peer["price_usdc"]:
        delta_pct = round(100 * (onyx_price_usdc - cheapest_peer["price_usdc"]) / cheapest_peer["price_usdc"], 1)
        verdict = f"onyx_premium — {delta_pct}% above cheapest peer"
        pitch = (
            f"Onyx '{cap}' is {delta_pct}% MORE EXPENSIVE than {cheapest_peer['domain']} "
            f"(${onyx_price_usdc:.4f} vs ${cheapest_peer['price_usdc']:.4f}). "
            f"Either drop price OR differentiate via AR-1 receipts + bundled OAI score."
        )
    else:
        delta_pct = 0.0
        verdict = "onyx_parity — exact price match"
        pitch = f"Onyx '{cap}' is priced identically to cheapest peer. Differentiate on schema depth + AR-1 receipts."

    return {
        "ok": True,
        "capability": cap,
        "network": network or "all",
        "onyx_price_usdc": onyx_price_usdc,
        "peers_matched": len(matches),
        "peers_returned": len(top),
        "cheapest_peer": cheapest_peer,
        "avg_peer_price_usdc": round(avg_peer, 6),
        "delta_pct_vs_cheapest": delta_pct,
        "verdict": verdict,
        "pitch": pitch,
        "peer_table": top,
    }


run.__when_to_use__ = (
    "Setting a new tool's price. Writing competitive marketing copy. "
    "Deciding which Onyx tools to differentiate vs which to drop."
)
run.__vs_alternatives__ = (
    "Manually browsing Coinbase Bazaar + ctrl-F. Saved spreadsheet of peer "
    "prices that goes stale weekly. This is one call, structured output, "
    "ready pitch line."
)
run.__example_request__ = {
    "capability": "tx_explainer",
    "onyx_price_usdc": 0.05,
    "network": "base",
}
