"""Bazaar — public x402 leaderboard.

Pulls Coinbase's CDP discovery API every BAZAAR_REFRESH_SEC seconds,
ranks all paid x402 services by 30-day calls / unique payers / freshness,
and serves three views as both HTML and JSON.

Loss-leader citation surface — free for the ecosystem, owns the search
keyword "x402 leaderboard" / "agentic.market stats".
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Optional

import httpx

DISCOVERY_URL = os.environ.get(
    "BAZAAR_DISCOVERY_URL",
    "https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources",
)
REFRESH_SEC = int(os.environ.get("BAZAAR_REFRESH_SEC", "900"))  # 15 min
PAGE_SIZE = int(os.environ.get("BAZAAR_PAGE_SIZE", "1000"))


QUALITY_PROBE_LIMIT = int(os.environ.get("BAZAAR_PROBE_LIMIT", "200"))
QUALITY_PROBE_TIMEOUT = float(os.environ.get("BAZAAR_PROBE_TIMEOUT", "8.0"))


class Cache:
    def __init__(self) -> None:
        self.items: list[dict] = []
        self.quality: dict[str, dict] = {}  # resource URL -> {ok, status, has_402_payload, ts}
        self.last_refresh_ts: float = 0
        self.last_quality_ts: float = 0
        self.last_error: Optional[str] = None
        self._lock = asyncio.Lock()

    async def refresh(self) -> None:
        async with self._lock:
            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    r = await client.get(DISCOVERY_URL, params={"limit": PAGE_SIZE})
                    r.raise_for_status()
                    data = r.json()
                items = data.get("resources") or data.get("data") or data.get("items") or []
                self.items = items if isinstance(items, list) else []
                self.last_refresh_ts = time.time()
                self.last_error = None
            except Exception as e:
                self.last_error = f"{type(e).__name__}: {str(e)[:200]}"

    async def probe_quality(self) -> None:
        """Probe top-N services for actual reachability + 402 protocol validity.

        Quality scoring (0-100):
            +40  endpoint resolves at TCP level (any HTTP response)
            +30  returns HTTP 402 on POST without payment header
            +20  402 body parses as JSON with `accepts` field (x402 spec)
            +10  served TLS without errors
        """
        if not self.items:
            return
        ranked = sorted(
            self.items,
            key=lambda i: (i.get("quality") or {}).get("l30DaysTotalCalls") or 0,
            reverse=True,
        )[:QUALITY_PROBE_LIMIT]

        async def probe_one(client: httpx.AsyncClient, item: dict) -> tuple[str, dict]:
            res = item.get("resource") or ""
            if not res or not res.startswith("http"):
                return res, {"ok": False, "score": 0, "reason": "no_resource_url"}
            try:
                r = await client.post(
                    res,
                    json={},
                    headers={"content-type": "application/json"},
                    timeout=QUALITY_PROBE_TIMEOUT,
                )
                score = 40
                ok = True
                reason = "reachable"
                returned_402 = r.status_code == 402
                json_402 = False
                if returned_402:
                    score += 30
                    reason = "402_returned"
                    try:
                        body = r.json()
                        if isinstance(body, dict) and (
                            "accepts" in body or "x402Version" in body
                        ):
                            score += 20
                            json_402 = True
                            reason = "402_with_accepts_payload"
                    except Exception:
                        pass
                if res.startswith("https://"):
                    score += 10
                return res, {
                    "ok": ok,
                    "score": min(100, score),
                    "status": r.status_code,
                    "returned_402": returned_402,
                    "json_402": json_402,
                    "reason": reason,
                    "ts": time.time(),
                }
            except httpx.TimeoutException:
                return res, {"ok": False, "score": 0, "reason": "timeout", "ts": time.time()}
            except httpx.RemoteProtocolError as e:
                return res, {"ok": False, "score": 0, "reason": f"protocol_error: {str(e)[:80]}", "ts": time.time()}
            except Exception as e:
                return res, {"ok": False, "score": 0, "reason": f"{type(e).__name__}: {str(e)[:80]}", "ts": time.time()}

        new_quality: dict[str, dict] = {}
        async with httpx.AsyncClient(timeout=QUALITY_PROBE_TIMEOUT, follow_redirects=False) as client:
            results = await asyncio.gather(
                *[probe_one(client, it) for it in ranked],
                return_exceptions=True,
            )
        for r in results:
            if isinstance(r, Exception):
                continue
            if isinstance(r, tuple) and len(r) == 2:
                k, v = r
                if k:
                    new_quality[k] = v
        async with self._lock:
            self.quality.update(new_quality)
            self.last_quality_ts = time.time()

    def stale(self) -> bool:
        return (time.time() - self.last_refresh_ts) > REFRESH_SEC


cache = Cache()


def _q(item: dict) -> dict:
    """Best-effort extract of quality metrics."""
    q = item.get("quality") or {}
    return {
        "calls_30d": int(q.get("l30DaysTotalCalls") or 0),
        "payers_30d": int(q.get("l30DaysUniquePayers") or 0),
        "last_called": q.get("lastCalledAt"),
    }


def _domain(item: dict) -> str:
    res = item.get("resource") or ""
    if "://" in res:
        return res.split("://", 1)[1].split("/")[0]
    return res[:60]


def _price(item: dict) -> str:
    accepts = item.get("accepts") or []
    if not accepts:
        return "?"
    a = accepts[0] if isinstance(accepts, list) else accepts
    # CDP discovery uses `amount`; some legacy/community manifests use `maxAmountRequired`
    amt = a.get("amount") or a.get("maxAmountRequired") or "0"
    try:
        v = int(amt) / 1_000_000
        if v >= 1:
            return f"${v:.2f}"
        if v >= 0.01:
            return f"${v:.4f}"
        return f"${v:.6f}"
    except (TypeError, ValueError):
        return "?"


def _network(item: dict) -> str:
    accepts = item.get("accepts") or []
    if not accepts:
        return "?"
    a = accepts[0] if isinstance(accepts, list) else accepts
    n = (a.get("network") or "?").strip()
    nlow = n.lower()
    # Normalize the long Solana CAIP and the various Base aliases
    if nlow in ("eip155:8453", "base"):
        return "Base"
    if nlow in ("eip155:84532", "base-sepolia"):
        return "Base-Sepolia"
    if nlow.startswith("solana:"):
        return "Solana"
    if nlow == "stellar:testnet":
        return "Stellar-Testnet"
    return {"eip155:1": "Ethereum", "eip155:137": "Polygon"}.get(n, n)


def _short_desc(item: dict) -> str:
    accepts = item.get("accepts") or []
    if accepts:
        a = accepts[0] if isinstance(accepts, list) else accepts
        d = a.get("description") or ""
        if d:
            return (d[:120] + "…") if len(d) > 120 else d
    return ""


def ranked(view: str = "volume", limit: int = 100) -> list[dict]:
    rows = []
    for it in cache.items:
        q = _q(it)
        res = it.get("resource", "")
        qual = cache.quality.get(res, {})
        rows.append({
            "resource": res,
            "domain": _domain(it),
            "price": _price(it),
            "network": _network(it),
            "calls_30d": q["calls_30d"],
            "payers_30d": q["payers_30d"],
            "last_called": q["last_called"],
            "description": _short_desc(it),
            "quality_score": qual.get("score"),
            "quality_status": qual.get("status"),
            "quality_reason": qual.get("reason"),
            "quality_ts": qual.get("ts"),
        })
    if view == "volume":
        rows.sort(key=lambda r: r["calls_30d"], reverse=True)
    elif view == "payers":
        rows.sort(key=lambda r: r["payers_30d"], reverse=True)
    elif view == "newest":
        rows.sort(key=lambda r: (r["last_called"] or ""), reverse=True)
    elif view == "cheapest":
        def kp(r: dict) -> float:
            try:
                return float(r["price"].lstrip("$"))
            except (ValueError, AttributeError):
                return 1e9
        rows.sort(key=kp)
    elif view == "quality":
        rows.sort(key=lambda r: (r["quality_score"] or -1, r["calls_30d"]), reverse=True)
    return rows[:limit]


def stats_summary() -> dict:
    items = cache.items
    quality_scores = [v.get("score", 0) for v in cache.quality.values() if v.get("score") is not None]
    qual_total = len(quality_scores)
    return {
        "total_indexed": len(items),
        "total_calls_30d": sum(_q(i)["calls_30d"] for i in items),
        "total_payers_30d_unique_sum": sum(_q(i)["payers_30d"] for i in items),
        "by_network": _by_network(items),
        "last_refresh_ts": cache.last_refresh_ts,
        "stale": cache.stale(),
        "last_error": cache.last_error,
        "quality": {
            "probed": qual_total,
            "last_probe_ts": cache.last_quality_ts,
            "avg_score": round(sum(quality_scores) / qual_total, 1) if qual_total else None,
            "buckets": {
                "green_70_plus": sum(1 for s in quality_scores if s >= 70),
                "yellow_40_69": sum(1 for s in quality_scores if 40 <= s < 70),
                "red_below_40": sum(1 for s in quality_scores if s < 40),
            },
        },
    }


def _by_network(items: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for it in items:
        net = _network(it)
        out[net] = out.get(net, 0) + 1
    return out


def render_html(view: str, rows: list[dict], stats: dict) -> str:
    view_links = " · ".join(
        f'<a href="?view={v}"{(" class=active" if v == view else "")}>{label}</a>'
        for v, label in [("volume", "Top by Volume"), ("payers", "Most Unique Payers"),
                          ("newest", "Recently Active"), ("cheapest", "Cheapest"),
                          ("quality", "Highest Quality")]
    )
    network_breakdown = " · ".join(f"{n}: {c}" for n, c in sorted(stats["by_network"].items(), key=lambda x: -x[1]))
    def quality_dot(r: dict) -> str:
        s = r.get("quality_score")
        reason = r.get("quality_reason") or ""
        if s is None:
            return '<span class="qd qd-grey" title="not probed yet">·</span>'
        if s >= 70:
            return f'<span class="qd qd-green" title="score {s}/100 — {reason}">●</span>'
        if s >= 40:
            return f'<span class="qd qd-yellow" title="score {s}/100 — {reason}">●</span>'
        return f'<span class="qd qd-red" title="score {s}/100 — {reason}">●</span>'

    body_rows = []
    for i, r in enumerate(rows, 1):
        body_rows.append(
            f"<tr><td class=rank>{i}</td>"
            f"<td>{quality_dot(r)} <span class=domain>{r['domain']}</span><div class=desc>{r['description']}</div></td>"
            f"<td class=price>{r['price']}</td>"
            f"<td class=net>{r['network']}</td>"
            f"<td class=num>{r['calls_30d']:,}</td>"
            f"<td class=num>{r['payers_30d']:,}</td></tr>"
        )
    rows_html = "\n".join(body_rows) or "<tr><td colspan=6>Loading… first refresh in flight.</td></tr>"
    last_refresh = "never" if not stats["last_refresh_ts"] else \
        f"{int(time.time() - stats['last_refresh_ts'])}s ago"
    return f"""<!doctype html><html lang=en><head>
<meta charset=utf-8>
<title>Onyx Bazaar — x402 Leaderboard</title>
<meta name=description content="Public leaderboard of every paid x402 service on Base, Solana, and beyond. Refreshed every 15 minutes from the Coinbase CDP discovery API.">
<style>
:root{{color-scheme:dark}}
body{{font:14px/1.55 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;background:#0a0a0a;color:#ddd;margin:0;padding:48px 24px;max-width:1100px;margin:0 auto}}
h1{{color:#fff;font-size:30px;margin:0 0 4px;letter-spacing:-.02em}}
.tagline{{color:#888;margin:0 0 24px;font-size:15px}}
nav{{margin:0 0 24px;padding:14px 16px;background:#111;border:1px solid #222;border-radius:4px}}
nav a{{color:#79c0ff;text-decoration:none;margin-right:6px}}
nav a.active{{color:#ffd166;font-weight:600}}
.summary{{color:#888;font-size:12px;margin:0 0 24px;display:flex;flex-wrap:wrap;gap:12px}}
.summary span{{padding:4px 10px;border:1px solid #222;border-radius:3px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th,td{{text-align:left;padding:10px 12px;border-bottom:1px solid #1a1a1a;vertical-align:top}}
th{{color:#888;font-weight:normal;font-size:11px;text-transform:uppercase;letter-spacing:.08em;border-bottom:1px solid #333}}
.rank{{color:#666;width:40px}}
.domain{{color:#7ee787;font-size:14px}}
.desc{{color:#888;font-size:12px;margin-top:4px;max-width:480px}}
.price{{color:#ffd166;white-space:nowrap}}
.qd{{display:inline-block;width:12px;text-align:center;font-size:14px;line-height:1;margin-right:4px;vertical-align:middle}}
.qd-green{{color:#7ee787}}.qd-yellow{{color:#ffd166}}.qd-red{{color:#ff7b72}}.qd-grey{{color:#444}}
.net{{color:#79c0ff;font-size:12px}}
.num{{color:#ddd;text-align:right;font-variant-numeric:tabular-nums}}
footer{{color:#555;font-size:11px;margin-top:48px;text-align:center}}
footer a{{color:#79c0ff}}
</style></head><body>
<h1>Onyx Bazaar</h1>
<p class=tagline>Public leaderboard of every paid x402 service. Refreshed from Coinbase CDP discovery every 15 min. Free citation surface — drop a link in any blog/PR/talk.</p>

<nav>{view_links}</nav>

<div class=summary>
  <span>{stats['total_indexed']:,} services indexed</span>
  <span>{stats['total_calls_30d']:,} calls / 30d</span>
  <span>last refresh: {last_refresh}</span>
  <span>networks: {network_breakdown}</span>
</div>

<table>
<thead><tr><th>#</th><th>Service</th><th>Price</th><th>Network</th><th class=num>Calls 30d</th><th class=num>Unique Payers</th></tr></thead>
<tbody>{rows_html}</tbody>
</table>

<footer>
Built by <a href="https://onyx-actions.onrender.com">Onyx Actions</a> on the
<a href="https://github.com/dimitrilaouanis-tech/onyx-mcp">onyx-paid-mcp</a> framework.
Source: <a href="{DISCOVERY_URL}">CDP discovery API</a>.
JSON: <a href="?view={view}&format=json">/bazaar.json</a>.
</footer>
</body></html>"""
