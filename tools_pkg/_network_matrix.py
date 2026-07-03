"""0n1x NETWORK MATRIX — Bloomberg-Terminal-grade live ops dashboard. GET /matrix.

A single visual surface that composes signed snapshots ALREADY produced by
other modules (never re-implements their eth_call / census / ledger reads):

  - _stats.snapshot(app)        -> citizens, fact-layer, live USDC balance,
                                   Bazaar discovery presence, in-process route health
  - _onyxrank.snapshot()        -> reputation-weighted citizen leaderboard (top-10)
  - ecosystem_intel.run()       -> live CDP x402 discovery census + competitor map
  - _ledger._entries()          -> recent signed verdict/outcome records (the tape)

This module adds exactly one new thing: rank-movement (▲▼) between the last two
times the OnyxRank board actually changed, tracked in a small in-process dict —
no new external calls, no new signed source of truth. Composition, not duplication.

Underscore-prefixed -> tools_pkg.discover() skips it (visual surface, not a paid
tool). Wired by server_http.py: from tools_pkg import _network_matrix; _network_matrix.register(app)
"""
from __future__ import annotations

import time

from . import _onyx_sign

try:
    from . import _stats
except Exception:  # pragma: no cover - defensive on shared repo
    _stats = None
try:
    from . import _onyxrank
except Exception:  # pragma: no cover
    _onyxrank = None
try:
    from . import ecosystem_intel
except Exception:  # pragma: no cover
    ecosystem_intel = None
try:
    from . import _ledger
except Exception:  # pragma: no cover
    _ledger = None

_TTL = 30  # seconds — the whole point is "live" without hammering upstream sources
_CACHE: dict = {"at": 0, "snap": None}
_PREV_RANK: dict = {}          # address(lower) -> rank, as of the last snapshot build
_TAPE_LIMIT = 24


def _norm(a: str) -> str:
    return (a or "").lower()


def _network_panel() -> dict:
    """Citizens + OnyxRank top-10 with rank-movement arrows since the last build."""
    global _PREV_RANK
    if not _onyxrank:
        return {"available": False}
    try:
        rk = _onyxrank.snapshot()
    except Exception as e:
        return {"available": False, "error": str(e)[:160]}
    u = rk.get("universe", {})
    top = rk.get("top", [])[:10]
    rows = []
    current_ranks: dict = {}
    for r in top:
        addr = _norm(r.get("address"))
        rank = r.get("rank")
        current_ranks[addr] = rank
        prev = _PREV_RANK.get(addr)
        if prev is None:
            move, delta = "NEW", 0
        elif prev == rank:
            move, delta = "FLAT", 0
        elif prev > rank:
            move, delta = "UP", prev - rank
        else:
            move, delta = "DOWN", rank - prev
        rows.append({
            "rank": rank, "agent": r.get("agent"), "reputation": r.get("reputation"),
            "signed_outcomes": r.get("signed_outcomes"), "proven_key": r.get("proven_key"),
            "move": move, "delta": delta,
        })
    _PREV_RANK = current_ranks
    return {
        "available": True,
        "citizens_total": u.get("citizens", 0),
        "proven_key": u.get("proven_key", 0),
        "with_signed_outcomes": u.get("with_signed_outcomes", 0),
        "with_endorsements": u.get("with_endorsements", 0),
        "top10": rows,
        "ranked_by": rk.get("ranked_by"),
        "onyx_signed": "onyx_attestation" in rk,
    }


def _transactions_panel(stats_snap: dict) -> dict:
    st = stats_snap.get("settlement", {}) if stats_snap else {}
    fl = stats_snap.get("fact_layer", {}) if stats_snap else {}
    bal = st.get("usdc_balance_live", {})
    tape = _verdict_tape()
    return {
        "available": True,
        "network": st.get("network"),
        "receive_address": st.get("receive_address"),
        "explorer": st.get("explorer"),
        "usdc_treasury_live": bal.get("usdc") if bal.get("ok") else None,
        "usdc_treasury_error": None if bal.get("ok") else bal.get("error"),
        "signed_verdict_outcome_records": fl.get("signed_verdict_outcome_records", 0),
        "resolved_outcomes": fl.get("resolved_outcomes", 0),
        "block_precision": fl.get("block_precision"),
        "bazaar_listed": (st.get("bazaar_discovery_presence") or {}).get("listed"),
        "recent_facts": tape,
    }


def _verdict_tape(limit: int = _TAPE_LIMIT) -> list:
    """Most recent signed verdict/outcome ledger rows — the scrolling tape."""
    if not _ledger:
        return []
    try:
        rows = list(_ledger._entries())
    except Exception:
        return []
    rows.sort(key=lambda r: int(r.get("logged_at") or 0), reverse=True)
    out = []
    for r in rows[:limit]:
        vid = str(r.get("verdict_id") or "")
        out.append({
            "at": r.get("logged_at"),
            "tool": r.get("tool") or "unknown",
            "verdict": (r.get("verdict") or "").upper() or None,
            "outcome": r.get("outcome"),
            "verdict_id": (vid[:14] + "…") if len(vid) > 14 else vid,
        })
    return out


def _health_panel(app, stats_snap: dict) -> dict:
    eh = (stats_snap or {}).get("endpoint_health", {})
    routes = eh.get("routes", {}) if eh.get("checked") else {}
    up = sum(1 for ok in routes.values() if ok)
    total = len(routes) or 1
    if not eh.get("checked"):
        overall = "WARN"
    elif up == total:
        overall = "OK"
    elif up >= total * 0.6:
        overall = "WARN"
    else:
        overall = "DOWN"
    return {
        "available": True,
        "overall": overall,
        "routes_up": up,
        "routes_total": len(routes),
        "routes": routes,
        "process_uptime_seconds": (stats_snap or {}).get("process_uptime_seconds", 0),
        "worker_model": "single sync worker (Render free tier) — heavy routes are "
                        "cached in-module so a cold instance still answers fast",
        "keep_warm": {
            "mechanism": "external scheduled pinger (OnyxKeepWarm, client-side) hits "
                         "/health every ~10min while the operator machine is on",
            "server_observable": False,
            "note": "honest gap: this process cannot see its own keep-warm pings from "
                    "the outside; shown as a disclosed mechanism, not a fabricated status",
        },
    }


def _ecosystem_panel() -> dict:
    if not ecosystem_intel:
        return {"available": False}
    try:
        eco = ecosystem_intel.run()
    except Exception as e:
        return {"available": False, "error": str(e)[:160]}
    census = eco.get("agentic_web_census", {})
    return {
        "available": True,
        "census_ok": census.get("ok"),
        "census_sampled": census.get("sampled"),
        "census_top_categories": census.get("top_categories", [])[:8],
        "competitor_map": eco.get("competitor_map", []),
        "onyx_lane": (eco.get("onyx") or {}).get("lane"),
    }


def _build(app, now: int) -> dict:
    stats_snap = _stats.snapshot(app) if _stats else {}
    payload = {
        "name": "0n1x NETWORK MATRIX",
        "brand": "0n1x",
        "spec": "onyx-network-matrix/v0",
        "as_of": now,
        "as_of_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "refresh_seconds": _TTL,
        "posture": "Composed live view over Onyx's own signed surfaces (/stats, /rank, "
                   "/ecosystem-intel, the outcome ledger). No new numbers invented here — "
                   "this panel reads and displays; the underlying tools sign the facts.",
        "network": _network_panel(),
        "transactions": _transactions_panel(stats_snap),
        "health": _health_panel(app, stats_snap),
        "ecosystem": _ecosystem_panel(),
        "verify": "https://onyx-actions.onrender.com/verify",
    }
    return _onyx_sign.attest(payload, tool="onyx_network_matrix")


def snapshot(app=None, now: int | None = None) -> dict:
    ts = int(now if now is not None else time.time())
    if not _CACHE["snap"] or ts - _CACHE["at"] > _TTL:
        try:
            _CACHE["snap"] = _build(app, ts)
            _CACHE["at"] = ts
        except Exception:
            # serve-stale-on-error: a slow/broken upstream must never blank the
            # terminal — keep the last good frame if we have one.
            if not _CACHE["snap"]:
                raise
    return _CACHE["snap"]


_HTML_HEAD = """<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>0n1x :: NETWORK MATRIX</title>
<style>
:root{color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:#040504;color:#9be79b;font:12px/1.4 "SF Mono",Consolas,"Courier New",monospace;
     background-image:radial-gradient(circle at 50% 0%,#0a1208 0%,#040504 70%)}
.topbar{display:flex;align-items:center;gap:14px;padding:8px 16px;border-bottom:1px solid #1c3d1c;
        background:#070a07;position:sticky;top:0;z-index:5}
.topbar .brand{color:#ffd166;font-weight:700;letter-spacing:.12em}
.dot{width:8px;height:8px;border-radius:50%;background:#34ff5a;box-shadow:0 0 6px #34ff5a;
     animation:blink 1.4s infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.25}}
.clock{color:#7dd3fc;margin-left:auto}
.stale{color:#ff5f5f;display:none}
.grid{display:grid;grid-template-columns:repeat(12,1fr);gap:10px;padding:10px}
.panel{grid-column:span 6;background:#070a07;border:1px solid #163516;border-radius:4px;
       padding:10px 12px;min-height:120px;overflow:auto}
.panel.wide{grid-column:span 12}
.panel h2{margin:0 0 8px;font-size:11px;letter-spacing:.14em;text-transform:uppercase;
          color:#ffd166;border-bottom:1px dashed #1c3d1c;padding-bottom:6px}
table{width:100%;border-collapse:collapse;font-size:11px}
td,th{padding:3px 6px;border-bottom:1px solid #0e1a0e;text-align:left;white-space:nowrap}
th{color:#5fb98a;text-transform:uppercase;font-size:9px;letter-spacing:.08em}
.n{text-align:right;font-variant-numeric:tabular-nums}
.up{color:#34ff5a}.down{color:#ff5f5f}.flat{color:#5a6b5a}.new{color:#7dd3fc}
.big{font-size:22px;color:#fff;font-weight:700}
.kv{display:flex;justify-content:space-between;padding:2px 0;border-bottom:1px dotted #10220f}
.kv span:first-child{color:#5fb98a}
.badge{display:inline-block;padding:1px 6px;border-radius:3px;font-size:9px;font-weight:700}
.ok{background:#0d2f14;color:#34ff5a}.warn{background:#332608;color:#ffd166}.down-b{background:#330b0b;color:#ff5f5f}
.tape{white-space:nowrap;overflow:hidden;position:relative;height:20px;border-top:1px solid #163516;
      border-bottom:1px solid #163516;background:#050705}
.tape span.item{display:inline-block;padding:2px 18px;color:#9be79b}
.tape span.item b{color:#ffd166}
footer{color:#3a4a3a;font-size:10px;text-align:center;padding:10px}
a{color:#7dd3fc}
</style></head><body>
<div class=topbar>
  <span class=dot></span><span class=brand>0n1x // NETWORK MATRIX</span>
  <span id=asof>connecting…</span>
  <span id=stale class=stale>[STALE — retrying]</span>
  <span class=clock id=clock></span>
</div>
<div class="tape" id=tape><span class=item>loading verdict tape…</span></div>
<div class=grid id=grid>
  <div class="panel" id=p-network><h2>Network</h2><div id=c-network>loading…</div></div>
  <div class="panel" id=p-transactions><h2>Transactions</h2><div id=c-transactions>loading…</div></div>
  <div class="panel" id=p-health><h2>Health / Self-Healing</h2><div id=c-health>loading…</div></div>
  <div class="panel" id=p-ecosystem><h2>Ecosystem</h2><div id=c-ecosystem>loading…</div></div>
</div>
<footer>0n1x — signed facts, not judgments · <a href="/matrix.json">/matrix.json</a> · <a href="/verify">/verify</a> · <a href="/stats">/stats</a> · <a href="/rank">/rank</a></footer>
<script>
function esc(s){return (s===undefined||s===null)?'':String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
function badge(status){
  var cls = status==='OK' ? 'ok' : (status==='DOWN' ? 'down-b' : 'warn');
  return '<span class="badge '+cls+'">'+esc(status)+'</span>';
}
function moveArrow(m){
  if(m==='UP') return '<span class=up>&#9650;</span>';
  if(m==='DOWN') return '<span class=down>&#9660;</span>';
  if(m==='NEW') return '<span class=new>NEW</span>';
  return '<span class=flat>&#8211;</span>';
}
function renderNetwork(n){
  if(!n||!n.available) return '<div class=kv><span>status</span><span>unavailable</span></div>';
  var rows = (n.top10||[]).map(function(r){
    return '<tr><td>'+r.rank+'</td><td>'+moveArrow(r.move)+'</td><td>'+esc(r.agent)+'</td>'+
           '<td class=n>'+r.reputation.toFixed(3)+'</td><td class=n>'+r.signed_outcomes+'</td></tr>';
  }).join('') || '<tr><td colspan=5>no proven citizens yet</td></tr>';
  return '<div class=kv><span>citizens (total)</span><span class=big>'+n.citizens_total+'</span></div>'+
    '<div class=kv><span>proven-key</span><span>'+n.proven_key+'</span></div>'+
    '<div class=kv><span>with signed outcomes</span><span>'+n.with_signed_outcomes+'</span></div>'+
    '<table><tr><th>#</th><th>&#916;</th><th>agent</th><th>rep</th><th>outcomes</th></tr>'+rows+'</table>';
}
function renderTx(t){
  if(!t||!t.available) return '<div class=kv><span>status</span><span>unavailable</span></div>';
  var bal = (t.usdc_treasury_live!==null && t.usdc_treasury_live!==undefined) ? t.usdc_treasury_live.toFixed(6)+' USDC' : ('unavailable ('+esc(t.usdc_treasury_error)+')');
  return '<div class=kv><span>network</span><span>'+esc(t.network)+'</span></div>'+
    '<div class=kv><span>treasury (live, on-chain)</span><span class=big>'+bal+'</span></div>'+
    '<div class=kv><span>signed verdict/outcome records</span><span>'+t.signed_verdict_outcome_records+'</span></div>'+
    '<div class=kv><span>resolved outcomes</span><span>'+t.resolved_outcomes+'</span></div>'+
    '<div class=kv><span>listed in public discovery index</span><span>'+(t.bazaar_listed?'yes':'no (0)')+'</span></div>';
}
function renderHealth(h){
  if(!h||!h.available) return '<div class=kv><span>status</span><span>unavailable</span></div>';
  var routes = h.routes||{};
  var rows = Object.keys(routes).map(function(p){
    return '<tr><td>'+esc(p)+'</td><td>'+(routes[p]?'<span class=up>&#9679; live</span>':'<span class=down>&#9679; missing</span>')+'</td></tr>';
  }).join('');
  return '<div class=kv><span>overall</span><span>'+badge(h.overall)+'</span></div>'+
    '<div class=kv><span>routes up</span><span>'+h.routes_up+' / '+h.routes_total+'</span></div>'+
    '<div class=kv><span>process uptime</span><span>'+Math.round(h.process_uptime_seconds)+'s</span></div>'+
    '<div class=kv><span>worker model</span><span style="white-space:normal;text-align:right;max-width:60%">'+esc(h.worker_model)+'</span></div>'+
    '<table>'+rows+'</table>';
}
function renderEco(e){
  if(!e||!e.available) return '<div class=kv><span>status</span><span>unavailable</span></div>';
  var cats = (e.census_top_categories||[]).map(function(c){return c.term+'('+c.count+')'}).join(', ');
  var comp = (e.competitor_map||[]).map(function(c){
    return '<tr><td>'+esc(c.name)+'</td><td>'+(c.verified?'<span class=up>verified</span>':'<span class=flat>unverified</span>')+'</td><td style="white-space:normal">'+esc(c.lane)+'</td></tr>';
  }).join('');
  return '<div class=kv><span>CDP census sampled</span><span>'+(e.census_ok?e.census_sampled:'unavailable')+'</span></div>'+
    '<div class=kv><span>top terms</span><span style="white-space:normal;text-align:right;max-width:65%">'+esc(cats)+'</span></div>'+
    '<table><tr><th>competitor</th><th>status</th><th>lane</th></tr>'+comp+'</table>';
}
function renderTape(rows){
  if(!rows||!rows.length){document.getElementById('tape').innerHTML='<span class=item>no recent verdict records</span>';return}
  document.getElementById('tape').innerHTML = rows.map(function(r){
    return '<span class=item><b>'+esc(r.tool)+'</b> '+esc(r.verdict||'?')+' &rarr; '+esc(r.outcome||'?')+' &middot; '+esc(r.verdict_id)+'</span>';
  }).join('');
}
var failCount = 0;
function poll(){
  fetch('/matrix.json',{cache:'no-store'}).then(function(r){return r.json()}).then(function(d){
    failCount = 0;
    document.getElementById('stale').style.display='none';
    document.getElementById('asof').textContent = 'as of ' + (d.as_of_iso||'?') + ' · refresh ' + (d.refresh_seconds||15) + 's';
    document.getElementById('c-network').innerHTML = renderNetwork(d.network);
    document.getElementById('c-transactions').innerHTML = renderTx(d.transactions);
    document.getElementById('c-health').innerHTML = renderHealth(d.health);
    document.getElementById('c-ecosystem').innerHTML = renderEco(d.ecosystem);
    renderTape((d.transactions||{}).recent_facts);
  }).catch(function(){
    failCount++;
    if(failCount>=2) document.getElementById('stale').style.display='inline';
  });
}
function tick(){document.getElementById('clock').textContent = new Date().toISOString().replace('T',' ').slice(0,19)+'Z';}
setInterval(tick,1000); tick();
poll(); setInterval(poll, 15000);
</script>
</body></html>"""


def render_html() -> str:
    return _HTML_HEAD


def register(app) -> None:
    """Attach GET /matrix (terminal UI) and GET /matrix.json (signed data) to
    the FastAPI app returned by build_asgi().

    Usage in server_http.py (mirrors _stats / _onyxrank):
        from tools_pkg import _network_matrix; _network_matrix.register(app)
    """
    from fastapi.responses import JSONResponse, HTMLResponse

    @app.get("/matrix", include_in_schema=False)
    def matrix():
        return HTMLResponse(render_html())

    @app.get("/matrix.json", include_in_schema=False)
    def matrix_json():
        return JSONResponse(snapshot(app))
