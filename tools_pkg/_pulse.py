"""Agentic Web Pulse — a VIEW over the signed observation log, not the product.

The product is `_observations`: a continuously growing, individually-signed log
of facts about the agent economy. This module does two jobs:

  1. ingest(): pull the x402 discovery firehose and turn it into individual
     signed observations — one per endpoint, plus `new_endpoint` and
     `price_drift` events versus what we already witnessed. Each FACT is signed,
     not the page.
  2. snapshot()/render_html(): reassemble those observations into the familiar
     "pulse" board — now explicitly a window onto the dataset, with a live
     count of how many signed observations sit underneath it.

Depth over breadth: x402 only, on purpose. Coverage + history first.
Stdlib-only. Underscore-prefixed -> not a tool.
"""
from __future__ import annotations

import json
import time
import urllib.request

from . import _observations, _onyx_sign

_DISCOVERY = "https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources?limit=200"
_TTL = 600  # rebuild the view every 10 min
_CACHE: dict = {"at": 0, "snap": None}


def _host(res: str) -> str:
    return res.split("/")[2] if "://" in (res or "") else ""


def ingest(now: int) -> dict:
    """Pull the firehose and append SIGNED observations for anything new/changed.
    Returns counters of what was witnessed this pass."""
    try:
        req = urllib.request.Request(_DISCOVERY, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            items = (json.loads(r.read()) or {}).get("items", [])
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)[:80]}", "items": 0}

    new_endpoints = drifts = indexed = 0
    for it in items:
        q = it.get("quality", {}) or {}
        host = _host(it.get("resource", ""))
        if not host:
            continue
        calls = int(q.get("l30DaysTotalCalls") or 0)
        payers = int(q.get("l30DaysUniquePayers") or 0)
        subject = {"type": "endpoint", "id": host}
        seen_before = bool(_observations._STATE["by_subject"].get(f"endpoint:{host}"))
        if not seen_before:
            rec = _observations.record(
                "new_endpoint", subject,
                {"resource": it.get("resource", ""),
                 "description": (it.get("description") or "")[:140],
                 "calls_30d": calls, "unique_payers_30d": payers},
                at=now)
            if rec:
                new_endpoints += 1
        # witness the calls figure; emits price_drift-style change record on move
        d = _observations.record_drift(subject, "calls_30d", calls, at=now)
        if d and d.get("kind") == "price_drift":
            drifts += 1
        indexed += 1

    return {"items": len(items), "new_endpoints": new_endpoints,
            "drifts": drifts, "indexed": indexed}


def _build_view(now: int) -> dict:
    """Reassemble the dashboard FROM the firehose + the signed log underneath."""
    try:
        req = urllib.request.Request(_DISCOVERY, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            items = (json.loads(r.read()) or {}).get("items", [])
    except Exception as e:
        return {"pulse": "agentic-web", "error": f"{type(e).__name__}: {str(e)[:80]}", "at": now}

    # ingest first so the log is fresh, then read the firehose for the live view
    ing = ingest(now)

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
                if now - t < 172800 and c <= 12:
                    fresh.append({"host": host, "calls_30d": c, "desc": (it.get("description") or "")[:60]})
            except Exception:
                pass

    movers = sorted(by_host.items(), key=lambda x: -x[1])
    log_stats = _observations.stats()
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
        "observation_log": {
            "total_observations": log_stats.get("total_observations", 0),
            "distinct_subjects": log_stats.get("distinct_subjects", 0),
            "this_pass": ing,
            "note": "This board is a VIEW. The product is the signed log below it: "
                    "every fact individually Ed25519-signed, queryable, replayable.",
            "query": {
                "endpoint_history": "/endpoint/{host}",
                "merchant_history": "/merchant/{domain}",
                "full_log": "/history",
                "timeline": "/timeline",
                "single_proof": "/proof/{obs_id}",
            },
        },
        "trust_layer": {
            "issuer": "onyx",
            "model": "Certificate Transparency for autonomous commerce",
            "note": "Onyx signs ground-truth observations agents check before they act. "
                    "Moat = coverage + history, not the signature alone.",
            "verify": "https://onyx-actions.onrender.com/verify",
            "challenge": "https://onyx-actions.onrender.com/fool",
        },
        "method": "x402 CDP discovery firehose, depth-first (no breadth widening)",
    }
    # The VIEW is still signed (so the page is tamper-evident), but the page is
    # no longer the asset — the per-observation signatures underneath it are.
    return _onyx_sign.attest(snap, tool="onyx_pulse_view")


def snapshot(now: int | None = None) -> dict:
    ts = int(now if now is not None else time.time())
    if not _CACHE["snap"] or ts - _CACHE["at"] > _TTL:
        _CACHE["snap"] = _build_view(ts)
        _CACHE["at"] = ts
    return _CACHE["snap"]


def render_html(base: str = "https://onyx-actions.onrender.com") -> str:
    s = snapshot()
    e = s.get("x402_economy", {})
    log = s.get("observation_log", {})
    movers = "".join(
        f"<tr><td>{i+1}</td><td class=h>{m['host']}</td><td class=n>{m['calls_30d']:,}</td></tr>"
        for i, m in enumerate(e.get("top_movers", []))
    ) or "<tr><td colspan=3>loading…</td></tr>"
    fresh = "".join(
        f"<li><span class=h>{f['host']}</span> <span class=d>{f['desc']}</span></li>"
        for f in e.get("fresh_arrivals", [])
    ) or "<li>—</li>"
    signed = "onyx_attestation" in s
    total_obs = log.get("total_observations", 0)
    subjects = log.get("distinct_subjects", 0)
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><meta http-equiv=refresh content=60>
<title>Agentic Web Pulse — Onyx Observation Network</title>
<meta property="og:title" content="Onyx — {total_obs:,} signed observations of the agent economy">
<style>
:root{{color-scheme:dark}}*{{box-sizing:border-box}}
body{{font:14px/1.5 ui-monospace,Menlo,Consolas,monospace;background:#05060a;color:#d6f5e0;margin:0;padding:34px 16px;max-width:860px;margin:0 auto}}
h1{{font-size:28px;margin:0 0 2px;color:#fff;letter-spacing:-.02em}}
.sub{{color:#5fb98a;margin:0 0 24px}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:0 0 16px}}
.k{{background:#0a0f12;border:1px solid #15291f;border-radius:10px;padding:16px 10px;text-align:center}}
.k .n{{font-size:26px;font-weight:700;color:#34d399}} .k .l{{color:#5fb98a;font-size:10px;text-transform:uppercase;letter-spacing:.09em;margin-top:5px}}
.ledger{{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin:0 0 26px}}
.ledger .k .n{{color:#7dd3fc}}
h3{{color:#9af5c4;font-size:13px;text-transform:uppercase;letter-spacing:.08em;margin:22px 0 8px}}
table{{width:100%;border-collapse:collapse}} td{{padding:7px 9px;border-bottom:1px solid #0e1a14}}
.h{{color:#7dd3fc}} .n{{text-align:right;color:#d6f5e0}} .d{{color:#5a6b62}}
ul{{list-style:none;padding:0;margin:0}} li{{padding:6px 0;border-bottom:1px solid #0e1a14}}
.seal{{margin-top:22px;padding:12px 14px;background:#0a0f12;border:1px solid #15291f;border-left:3px solid #34d399;border-radius:8px;color:#9af5c4;font-size:12px}}
.q{{margin-top:14px;font-size:12px;color:#5fb98a}} .q a{{color:#7dd3fc;text-decoration:none}} .q code{{color:#9af5c4}}
footer{{color:#3a4a42;font-size:11px;margin-top:26px;text-align:center}}footer a{{color:#7dd3fc}}
</style></head><body>
<h1>⚡ Agentic Web Pulse</h1>
<p class=sub>A live window onto the Onyx Observation Network — every fact below individually signed. As of {s.get('as_of_iso','')}</p>
<div class=grid>
  <div class=k><div class=n>{e.get('services_indexed',0)}</div><div class=l>Services</div></div>
  <div class=k><div class=n>{e.get('active_last_24h',0)}</div><div class=l>Live 24h</div></div>
  <div class=k><div class=n>{e.get('calls_30d',0):,}</div><div class=l>Calls 30d</div></div>
  <div class=k><div class=n>{e.get('unique_payers_30d_sum',0):,}</div><div class=l>Payers 30d</div></div>
</div>
<div class=ledger>
  <div class=k><div class=n>{total_obs:,}</div><div class=l>Signed observations on log</div></div>
  <div class=k><div class=n>{subjects:,}</div><div class=l>Endpoints tracked w/ history</div></div>
</div>
<h3>🔥 Top movers</h3>
<table>{movers}</table>
<h3>🌱 Fresh arrivals</h3>
<ul>{fresh}</ul>
<div class=q>Query the signed log directly:
 <a href="{base}/history">/history</a> ·
 <a href="{base}/timeline">/timeline</a> ·
 <code>/endpoint/&#123;host&#125;</code> ·
 <code>/merchant/&#123;domain&#125;</code> ·
 <code>/proof/&#123;obs_id&#125;</code></div>
<div class=seal>🔏 Each observation is <b>{"individually Ed25519-signed by Onyx" if signed else "unsigned"}</b> — a Certificate-Transparency-style log for autonomous commerce. Verify any record (free): <a href="{base}/verify" style="color:#7dd3fc">{base}/verify</a> · raw view JSON: <a href="{base}/pulse?format=json" style="color:#7dd3fc">/pulse.json</a></div>
<footer>Onyx — the independent signed trust layer for the agentic web · <a href="{base}/fool">can you fool it?</a></footer>
</body></html>"""
