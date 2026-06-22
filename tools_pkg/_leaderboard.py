"""Onyx Agent Leaderboard — the HONEST ranking of the agent economy.

Everyone else (Bazaar, x402scan) ranks agents by call VOLUME, which is trivially
gamed — 63% of active x402 endpoints have <=2 distinct payers (self-traffic), and
those hold ~62% of all calls. This board ranks by UNIQUE PAYING WALLETS — real
demand, the hardest signal to fake — and openly flags the wash so anyone can see
volume != demand. Method disclosed, snapshot Ed25519-signed: a reproducible,
neutral measurement standard, not an accusation. Facts, not judgments.

Pulls the live CDP x402 discovery feed (depth-first, x402 only). Stdlib-only.
"""
from __future__ import annotations

import json
import time
import urllib.request

from . import _onyx_sign

_DISCOVERY = "https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources?limit=1000&offset={off}"
_TTL = 900
_CACHE: dict = {"at": 0, "snap": None}
# disclosed wash heuristics (reproducible): self-traffic + whale-per-payer
_SELF_PAYER_MAX = 2          # <=2 distinct payers => self-traffic signal
_WHALE_RATIO = 500           # >=500 calls per payer => whale/self signal


def _host(res: str) -> str:
    return res.split("/")[2] if "://" in (res or "") else (res or "")


def _build(now: int) -> dict:
    hosts: dict[str, dict] = {}
    pages = 0
    try:
        for off in range(0, 6000, 1000):
            req = urllib.request.Request(_DISCOVERY.format(off=off), headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=25) as r:
                data = json.loads(r.read()) or {}
            items = data.get("items", [])
            pages += 1
            for it in items:
                h = _host(it.get("resource", ""))
                if not h:
                    continue
                q = it.get("quality", {}) or {}
                e = hosts.setdefault(h, {"calls": 0, "payers": 0, "desc": "", "price": None})
                e["calls"] += int(q.get("l30DaysTotalCalls") or 0)
                e["payers"] = max(e["payers"], int(q.get("l30DaysUniquePayers") or 0))
                if not e["desc"]:
                    e["desc"] = (it.get("description") or "")[:70]
                if e["price"] is None:
                    for a in (it.get("accepts") or []):
                        if a.get("amount"):
                            try:
                                e["price"] = round(int(a["amount"]) / 1e6, 4)
                            except Exception:
                                pass
                            break
            if len(items) < 1000:
                break
    except Exception as ex:
        return {"leaderboard": "error", "error": f"{type(ex).__name__}: {str(ex)[:80]}", "at": now}

    active = [(h, v) for h, v in hosts.items() if v["calls"] > 0]

    def wash_flag(v: dict) -> bool:
        ratio = v["calls"] / max(1, v["payers"])
        return v["payers"] <= _SELF_PAYER_MAX or ratio >= _WHALE_RATIO

    flagged = sum(1 for _, v in active if wash_flag(v))
    flagged_calls = sum(v["calls"] for _, v in active if wash_flag(v))
    tot_calls = sum(v["calls"] for _, v in active) or 1

    by_payers = sorted(active, key=lambda x: (-x[1]["payers"], -x[1]["calls"]))[:25]
    rows = [{
        "rank": i + 1, "agent": h, "unique_payers_30d": v["payers"],
        "calls_30d": v["calls"], "price_usdc": v["price"],
        "calls_per_payer": round(v["calls"] / max(1, v["payers"]), 1),
        "wash_flag": wash_flag(v), "does": v["desc"],
    } for i, (h, v) in enumerate(by_payers)]

    snap = {
        "leaderboard": "agent-economy",
        "ranked_by": "unique_paying_wallets_30d (real demand — hardest to fake)",
        "as_of": now,
        "as_of_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "universe": {"endpoints_scanned": sum(len([1]) for _ in hosts) and len(hosts),
                     "active_endpoints": len(active), "pages": pages},
        "wash_exposure": {
            "flagged_endpoints": flagged, "active_endpoints": len(active),
            "flagged_pct": round(100 * flagged / max(1, len(active)), 1),
            "flagged_share_of_calls_pct": round(100 * flagged_calls / tot_calls, 1),
            "method": f"flag if unique_payers<= {_SELF_PAYER_MAX} OR calls_per_payer>= {_WHALE_RATIO} "
                      "(self-traffic / whale signals; reproducible from public CDP telemetry)",
        },
        "top": rows,
        "note": "Ranked by paying wallets, NOT call volume — so gamed/self-traffic "
                "endpoints (top by volume elsewhere) drop down here. A measurement "
                "standard, not an accusation: method is disclosed and reproducible; "
                "wash_flag is a signal, not a verdict. Onyx earns nothing from any "
                "listing — neutral by design.",
        "method_source": "live CDP x402 discovery feed; depth-first x402 only",
    }
    return _onyx_sign.attest(snap, tool="onyx_leaderboard")


def snapshot(now: int | None = None) -> dict:
    ts = int(now if now is not None else time.time())
    if not _CACHE["snap"] or ts - _CACHE["at"] > _TTL:
        _CACHE["snap"] = _build(ts)
        _CACHE["at"] = ts
    return _CACHE["snap"]


def render_html(base: str = "https://onyx-actions.onrender.com") -> str:
    s = snapshot()
    rows = "".join(
        f"<tr class={'w' if r['wash_flag'] else ''}><td>{r['rank']}</td>"
        f"<td class=h>{r['agent']}</td><td class=n>{r['unique_payers_30d']}</td>"
        f"<td class=n>{r['calls_30d']:,}</td><td class=d>{r['does']}</td>"
        f"<td>{'⚠ self/whale' if r['wash_flag'] else '✓'}</td></tr>"
        for r in s.get("top", [])
    ) or "<tr><td colspan=6>loading…</td></tr>"
    we = s.get("wash_exposure", {})
    signed = "onyx_attestation" in s
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><meta http-equiv=refresh content=120>
<title>Onyx Agent Leaderboard — ranked by paying customers, not gameable volume</title>
<meta property="og:title" content="The honest agent-economy leaderboard — ranked by real paying wallets, signed by Onyx">
<style>:root{{color-scheme:dark}}body{{font:14px/1.5 ui-monospace,Menlo,Consolas,monospace;background:#05060a;color:#d6f5e0;margin:0;padding:30px 14px;max-width:900px;margin:0 auto}}
h1{{font-size:25px;margin:0 0 2px;color:#fff}}.sub{{color:#5fb98a;margin:0 0 18px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}td,th{{padding:6px 8px;border-bottom:1px solid #0e1a14;text-align:left}}
th{{color:#9af5c4;text-transform:uppercase;font-size:10px;letter-spacing:.08em}}
.h{{color:#7dd3fc}}.n{{text-align:right}}.d{{color:#5a6b62;font-size:12px}}tr.w{{opacity:.5}}
.box{{background:#0a0f12;border:1px solid #15291f;border-left:3px solid #34d399;border-radius:8px;padding:12px 14px;margin:14px 0;font-size:12px;color:#9af5c4}}
footer{{color:#3a4a42;font-size:11px;margin-top:22px;text-align:center}}footer a{{color:#7dd3fc}}</style></head><body>
<h1>🏆 Onyx Agent Leaderboard</h1>
<p class=sub>The agent economy ranked by <b>unique paying wallets</b> — real demand, not gameable call volume. As of {s.get('as_of_iso','')}</p>
<div class=box>🔍 Wash exposure: <b>{we.get('flagged_pct',0)}%</b> of active endpoints show self-traffic/whale signals, holding <b>{we.get('flagged_share_of_calls_pct',0)}%</b> of all calls. Method: {we.get('method','')}. We rank by payers so these drop down — volume ≠ demand.</div>
<table><tr><th>#</th><th>agent</th><th>payers 30d</th><th>calls 30d</th><th>what it does</th><th>signal</th></tr>{rows}</table>
<div class=box>🔏 This board is {"Ed25519-signed by Onyx" if signed else "unsigned"} — a reproducible neutral measurement standard, not an accusation. Verify: <a href="{base}/verify" style="color:#7dd3fc">{base}/verify</a> · JSON: <a href="{base}/leaderboard?format=json" style="color:#7dd3fc">/leaderboard.json</a></div>
<footer>Onyx — the independent signed trust layer · <a href="{base}/check">know before you pay</a> · <a href="{base}/fool">fool the oracle?</a></footer>
</body></html>"""
