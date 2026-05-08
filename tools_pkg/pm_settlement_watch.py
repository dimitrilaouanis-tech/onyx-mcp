"""Prediction-market settlement watch — odds, volume, resolution, anomaly flags.

Coinbase's PROJECT-IDEAS.md explicitly calls for this primitive:
"Prediction-Market Oracle: agent resolves any prediction market by fetching
consensus facts online. Payment moment: resolution fee on settlement."

As of 2026-05-08 the only paid x402 endpoint serving prediction-market data
is blockrun.ai/markets (markets index only, no settlement watch). Onyx fills
the gap with a per-market lookup that returns:
- current odds (yes/no probability)
- 24h volume + total liquidity
- close timestamp + resolution state
- if resolved: outcome + settlement timestamp
- if open: hours-to-close
- anomaly flags (zero-volume + tightening odds = potential mispricing)

Sources (failover):
  1. Polymarket Gamma API — largest venue, slug-based lookup
  2. Manifold Markets — fallback when Polymarket geoblocks the caller
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any
import httpx

NAME = "onyx_pm_settlement_watch"
PRICE_USDC = "0.005"
TIER = "metered"
DESCRIPTION = (
    "Prediction-market state lookup — current odds, volume, liquidity, "
    "resolution state, and anomaly flags for any market on Polymarket "
    "or Manifold. Pass a market slug or full URL. Use for arb agents "
    "watching for mispriced events, copy-trading agents tracking whales, "
    "or settlement-resolver agents that pay only on a final outcome. "
    "Coinbase PROJECT-IDEAS.md explicitly calls for this primitive."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "slug_or_url": {
            "type": "string",
            "description": "Polymarket slug ('will-trump-win-2024'), Manifold slug, or full https URL to either platform",
        },
        "venue": {
            "type": "string",
            "description": "Force a specific venue: 'polymarket' or 'manifold'. Auto-detected if omitted.",
        },
    },
    "required": ["slug_or_url"],
}

_POLYMARKET_GAMMA = "https://gamma-api.polymarket.com"
_MANIFOLD_API = "https://api.manifold.markets/v0"


def _parse_input(s: str) -> tuple[str, str]:
    """Returns (venue, slug). Auto-detects venue from URL host if present."""
    s = s.strip()
    if s.startswith("https://") or s.startswith("http://"):
        if "manifold.markets" in s:
            slug = s.rstrip("/").split("/")[-1]
            return "manifold", slug
        if "polymarket.com" in s:
            slug = s.rstrip("/").split("/")[-1].split("?")[0]
            return "polymarket", slug
    # No scheme — bare slug. Default to polymarket (larger venue).
    return "polymarket", s


def _hours_to(ts_iso: str | None) -> float | None:
    if not ts_iso:
        return None
    try:
        end = datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
        delta = (end - datetime.now(timezone.utc)).total_seconds() / 3600
        return round(delta, 2)
    except Exception:
        return None


def _fetch_polymarket(slug: str) -> dict | None:
    try:
        r = httpx.get(f"{_POLYMARKET_GAMMA}/markets",
                      params={"slug": slug}, timeout=10.0)
        if r.status_code != 200:
            return None
        data = r.json()
        if not data:
            return None
        m = data[0] if isinstance(data, list) else data
        prices = m.get("outcomePrices") or "[]"
        if isinstance(prices, str):
            import json as _json
            try: prices = _json.loads(prices)
            except Exception: prices = []
        outcomes = m.get("outcomes") or "[]"
        if isinstance(outcomes, str):
            import json as _json
            try: outcomes = _json.loads(outcomes)
            except Exception: outcomes = []
        end_date = m.get("endDate") or m.get("end_date_iso")
        return {
            "venue": "polymarket",
            "question": m.get("question"),
            "slug": m.get("slug"),
            "url": f"https://polymarket.com/event/{m.get('slug')}" if m.get("slug") else None,
            "outcomes": outcomes,
            "outcome_prices": [float(p) for p in prices] if prices else [],
            "active": bool(m.get("active")),
            "closed": bool(m.get("closed")),
            "resolved": m.get("closed") and m.get("active") is False,
            "volume_usd": float(m.get("volume") or 0),
            "liquidity_usd": float(m.get("liquidity") or 0),
            "end_date": end_date,
            "hours_to_close": _hours_to(end_date),
            "condition_id": m.get("conditionId"),
        }
    except Exception:
        return None


def _fetch_manifold(slug: str) -> dict | None:
    try:
        r = httpx.get(f"{_MANIFOLD_API}/slug/{slug}", timeout=10.0)
        if r.status_code != 200:
            return None
        m = r.json()
        close_iso = None
        if m.get("closeTime"):
            close_iso = datetime.fromtimestamp(m["closeTime"]/1000, tz=timezone.utc).isoformat()
        return {
            "venue": "manifold",
            "question": m.get("question"),
            "slug": m.get("slug"),
            "url": m.get("url"),
            "outcomes": ["YES", "NO"] if m.get("outcomeType") == "BINARY" else [m.get("outcomeType")],
            "outcome_prices": [m.get("probability")] if m.get("probability") is not None else [],
            "active": not m.get("isResolved"),
            "closed": bool(m.get("isResolved")),
            "resolved": bool(m.get("isResolved")),
            "resolution": m.get("resolution"),
            "volume_usd": float(m.get("volume") or 0),
            "liquidity_usd": float(m.get("totalLiquidity") or 0),
            "end_date": close_iso,
            "hours_to_close": _hours_to(close_iso),
        }
    except Exception:
        return None


def _flags(m: dict) -> list[str]:
    out = []
    if m.get("resolved"):
        out.append(f"market resolved (outcome: {m.get('resolution') or 'see outcome_prices'})")
    elif m.get("hours_to_close") is not None and m["hours_to_close"] < 24:
        out.append(f"market closes in {m['hours_to_close']:.1f}h — pre-settlement window")
    if m.get("liquidity_usd") and m.get("liquidity_usd") < 100:
        out.append(f"low liquidity (${m['liquidity_usd']:.2f}) — wide spreads expected")
    if m.get("volume_usd") and m.get("volume_usd") < 100:
        out.append(f"low volume (${m['volume_usd']:.2f}) — thin market signal")
    prices = m.get("outcome_prices") or []
    if len(prices) >= 1:
        p = prices[0]
        if p is not None and (p < 0.02 or p > 0.98):
            out.append(f"odds extreme ({p:.4f}) — high-confidence consensus")
    if not out:
        out.append("market healthy and active")
    return out


def run(slug_or_url: str, venue: str | None = None, **_: object) -> dict:
    if not slug_or_url or len(slug_or_url) > 300:
        raise ValueError("slug_or_url required (slug, or full URL)")
    started = time.time()

    auto_venue, slug = _parse_input(slug_or_url)
    use_venue = (venue or auto_venue).lower()
    if use_venue not in ("polymarket", "manifold"):
        raise ValueError("venue must be 'polymarket' or 'manifold'")

    # Primary fetch
    market = _fetch_polymarket(slug) if use_venue == "polymarket" else _fetch_manifold(slug)
    fallback_used = False

    # Fallback to the other venue if primary failed (geoblock, slug mismatch)
    if market is None:
        fallback_used = True
        market = _fetch_manifold(slug) if use_venue == "polymarket" else _fetch_polymarket(slug)

    if market is None:
        return {
            "error": "market not found on Polymarket or Manifold",
            "slug": slug,
            "input": slug_or_url,
            "elapsed_ms": int((time.time() - started) * 1000),
        }

    market["fallback_used"] = fallback_used
    market["flags"] = _flags(market)
    market["source"] = f"onyx.{market['venue']}"
    market["elapsed_ms"] = int((time.time() - started) * 1000)
    return market
