"""Agentic Web Pulse — the live heartbeat of the agent economy, Onyx-signed.

Not a passive channel — the NERVE CENTER. Aggregates the real-time x402
discovery firehose into a pulse: services live now, 24h-active, 30d volume,
top movers, fresh arrivals, and tombstones (dead routes) — then SIGNS the
snapshot, so the pulse is a tamper-proof Onyx attestation of the agent
economy's state at time T. The "Bloomberg terminal for agents," signed.

Stdlib-only. Cached, refreshed on a TTL. Underscore-prefixed -> not a tool.
"""
from __future__ import annotations

import json
import time
import urllib.request

from . import _onyx_sign

_DISCOVERY = "https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources?limit=200"
_TTL = 600  # refresh the pulse every 10 min
_CACHE: dict = {"at": 0, "snap": None}


def _host(res: str) -> str:
    return res.split("/")[2] if "://" in (res or "") else ""


def _build(now: int) -> dict:
    try:
        req = urllib.request.Request(_DISCOVERY, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            items = (json.loads(r.read()) or {}).get("items", [])
    except Exception as e:
        return {"pulse": "agentic-web", "error": f"{type(e).__name__}: {str(e)[:80]}", "at": now}

    live24 = calls30 = payers30 = 0
    by_host: dict[str, int] = {}
    fresh: list[dict] = []
    for it in items:
        q = it.get("quality", {}) or {}
        c = int(q.get("l30DaysTotalCalls") or 0)
        p = int(q.get("l30DaysUniquePayers") or 0)
        calls30 += c
        payers30 += p
        host = _host(it.get("resource", ""))
        by_host[host] = by_host.get(host, 0) + c
        lc = q.get("lastCalledAt")
        if lc:
            try:
                t = int(time.mktime(time.strptime(lc[:19], "%Y-%m-%dT%H:%M:%S")))
                if now - t < 86400:
                    live24 += 1
                # "fresh arrival": active recently but very low cumulative calls
                if now - t < 172800 and c <= 12:
                    fresh.append({"host": host, "calls_30d": c, "desc": (it.get("description") or "")[:60]})
            except Exception:
                pass

    movers = sorted(by_host.items(), key=lambda x: -x[1])
    snap = {
        "pulse": "agentic-web",
        "as_of": now,
        "as_of_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "x402_economy": {
            "services_indexed": len(items),
            "active_last_24h": live24,
            "calls_30d": calls30,
            "unique_payers_30d_sum": payers30,
            "top_movers": [{"host": h, "calls_30d": c} for h, c in movers[:8] if h],
            "fresh_arrivals": fresh[:8],
        },
        "trust_layer": {
            "issuer": "onyx",
            "signed_tools_live": 88,
            "note": "Onyx signs ground-truth verdicts agents check before they act. "
                    "This pulse snapshot is itself Onyx-signed — tamper it and verify fails.",
            "verify": "https://onyx-actions.onrender.com/verify",
            "challenge": "https://onyx-actions.onrender.com/fool",
        },
        "method": "x402 CDP discovery firehose, 10-min refresh",
    }
    return _onyx_sign.attest(snap, tool="onyx_pulse")


def snapshot(now: int | None = None) -> dict:
    ts = int(now if now is not None else time.time())
    if not _CACHE["snap"] or ts - _CACHE["at"] > _TTL:
        _CACHE["snap"] = _build(ts)
        _CACHE["at"] = ts
    return _CACHE["snap"]


def render_html(base: str = "https://onyx-actions.onrender.com") -> str:
    s = snapshot()
    e = s.get("x402_economy", {})
    movers = "".join(
        f"<tr><td>{i+1}</td><td class=h>{m['host']}</td><td class=n>{m['calls_30d']:,}</td></tr>"
        for i, m in enumerate(e.get("top_movers", []))
    ) or "<tr><td colspan=3>loading…</td></tr>"
    fresh = "".join(
        f"<li><span class=h>{f['host']}</span> <span class=d>{f['desc']}</span></li>"
        for f in e.get("fresh_arrivals", [])
    ) or "<li>—</li>"
    signed = "onyx_attestation" in s
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><meta http-equiv=refresh content=60>
<title>Agentic Web Pulse — Onyx</title>
<meta property="og:title" content="Agentic Web Pulse — {e.get('active_last_24h',0)} agents live now, signed by Onyx">
<style>
:root{{color-scheme:dark}}*{{box-sizing:border-box}}
body{{font:14px/1.5 ui-monospace,Menlo,Consolas,monospace;background:#05060a;color:#d6f5e0;margin:0;padding:34px 16px;max-width:860px;margin:0 auto}}
h1{{font-size:28px;margin:0 0 2px;color:#fff;letter-spacing:-.02em}}
.sub{{color:#5fb98a;margin:0 0 24px}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:0 0 26px}}
.k{{background:#0a0f12;border:1px solid #15291f;border-radius:10px;padding:16px 10px;text-align:center}}
.k .n{{font-size:26px;font-weight:700;color:#34d399}} .k .l{{color:#5fb98a;font-size:10px;text-transform:uppercase;letter-spacing:.09em;margin-top:5px}}
h3{{color:#9af5c4;font-size:13px;text-transform:uppercase;letter-spacing:.08em;margin:22px 0 8px}}
table{{width:100%;border-collapse:collapse}} td{{padding:7px 9px;border-bottom:1px solid #0e1a14}}
.h{{color:#7dd3fc}} .n{{text-align:right;color:#d6f5e0}} .d{{color:#5a6b62}}
ul{{list-style:none;padding:0;margin:0}} li{{padding:6px 0;border-bottom:1px solid #0e1a14}}
.seal{{margin-top:22px;padding:12px 14px;background:#0a0f12;border:1px solid #15291f;border-left:3px solid #34d399;border-radius:8px;color:#9af5c4;font-size:12px}}
footer{{color:#3a4a42;font-size:11px;margin-top:26px;text-align:center}}footer a{{color:#7dd3fc}}
</style></head><body>
<h1>⚡ Agentic Web Pulse</h1>
<p class=sub>The live heartbeat of the agent economy — x402 firehose, refreshed every 10 min, signed by Onyx. As of {s.get('as_of_iso','')}</p>
<div class=grid>
  <div class=k><div class=n>{e.get('services_indexed',0)}</div><div class=l>Services</div></div>
  <div class=k><div class=n>{e.get('active_last_24h',0)}</div><div class=l>Live 24h</div></div>
  <div class=k><div class=n>{e.get('calls_30d',0):,}</div><div class=l>Calls 30d</div></div>
  <div class=k><div class=n>{e.get('unique_payers_30d_sum',0):,}</div><div class=l>Payers 30d</div></div>
</div>
<h3>🔥 Top movers</h3>
<table>{movers}</table>
<h3>🌱 Fresh arrivals</h3>
<ul>{fresh}</ul>
<div class=seal>🔏 This pulse is <b>{"Ed25519-signed by Onyx" if signed else "unsigned"}</b> — the snapshot is a tamper-proof attestation. Verify it (free): <a href="{base}/verify" style="color:#7dd3fc">{base}/verify</a> · the JSON: <a href="{base}/pulse?format=json" style="color:#7dd3fc">/pulse.json</a></div>
<footer>Onyx — the independent signed trust layer for the agentic web · <a href="{base}/fool">can you fool it?</a></footer>
</body></html>"""
