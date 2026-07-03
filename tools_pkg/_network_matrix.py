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
:root{color-scheme:dark;
  --bg:#0a0a0a;--panel:#141516;--raised:#18191a;--border:#232426;
  --txt:#eaeaea;--mut:#8a8f98;--pos:#22c55e;--neg:#ef4444;--amb:#f5a623}
*{box-sizing:border-box}
html,body{margin:0}
body{background:var(--bg);color:var(--txt);
  font:12px/1.45 ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace;
  font-variant-numeric:tabular-nums}
a{color:var(--amb);text-decoration:none}
a:hover{text-decoration:underline}
.topbar{display:flex;align-items:center;gap:16px;height:40px;padding:0 16px;
  background:var(--panel);border-bottom:1px solid var(--border);border-top:2px solid var(--amb);
  position:sticky;top:0;z-index:5;white-space:nowrap;overflow:hidden}
.brand{font-weight:700;letter-spacing:.14em}
.brand b{color:var(--amb)}
.live{display:inline-flex;align-items:center;gap:6px;color:var(--pos);font-size:10px;letter-spacing:.12em}
.dot{width:8px;height:8px;border-radius:50%;background:var(--pos);animation:pulse 1.6s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}
.sub{color:var(--mut);font-size:11px;overflow:hidden;text-overflow:ellipsis}
.stale{color:var(--neg);font-size:11px;letter-spacing:.08em;opacity:0;transition:opacity .8s ease}
.clock{margin-left:auto;color:var(--mut)}
.tape{height:26px;line-height:26px;overflow:hidden;white-space:nowrap;
  background:var(--panel);border-bottom:1px solid var(--border);padding:0 12px;color:var(--mut)}
.tape b{color:var(--txt);font-weight:600}
.tape .sep{color:#3a3c40;padding:0 10px}
.v-ok{color:var(--pos)}.v-bad{color:var(--neg)}.v-mid{color:var(--amb)}
.grid{display:grid;grid-template-columns:repeat(12,1fr);gap:10px;padding:10px;max-width:1500px;margin:0 auto}
.panel{background:var(--panel);border:1px solid var(--border);overflow:hidden;display:flex;flex-direction:column}
.panel h2{margin:0;padding:8px 12px;font-size:10px;font-weight:700;letter-spacing:.16em;
  text-transform:uppercase;color:var(--amb);background:var(--raised);
  border-bottom:1px solid var(--border);display:flex;justify-content:space-between;gap:8px;white-space:nowrap;overflow:hidden}
.panel h2 .hint{color:var(--mut);font-weight:400;letter-spacing:.04em;text-transform:none;overflow:hidden;text-overflow:ellipsis}
.pbody{padding:10px 12px;flex:1;overflow-y:auto;overflow-x:hidden}
.p-network{grid-column:span 7;height:420px}
.p-treemap{grid-column:span 5;height:420px}
.p-tx{grid-column:span 4;height:312px}
.p-act{grid-column:span 4;height:312px}
.p-health{grid-column:span 4;height:312px}
.p-eco{grid-column:span 12;height:320px}
@media(max-width:980px){.panel{grid-column:span 12!important}}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:10px}
.stat{background:var(--raised);border:1px solid var(--border);padding:6px 10px;height:52px;overflow:hidden}
.stat .k{color:var(--mut);font-size:9px;letter-spacing:.1em;text-transform:uppercase;white-space:nowrap}
.stat .sv{font-size:18px;font-weight:700;margin-top:2px}
table{width:100%;border-collapse:collapse;table-layout:fixed;font-size:11px}
th{color:var(--mut);text-transform:uppercase;font-size:9px;letter-spacing:.1em;font-weight:600;
  text-align:left;padding:3px 8px;border-bottom:1px solid var(--border);background:var(--raised);white-space:nowrap}
td{padding:4px 8px;border-bottom:1px solid #1b1c1e;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;height:27px}
th.n,td.n{text-align:right;font-variant-numeric:tabular-nums}
.pos{color:var(--pos)}.neg{color:var(--neg)}.amb{color:var(--amb)}.mut{color:var(--mut)}
.n.pos{color:var(--pos)}.n.neg{color:var(--neg)}.n.mut{color:var(--mut)}
.kv{display:flex;justify-content:space-between;align-items:baseline;height:26px;line-height:26px;
  border-bottom:1px solid #1b1c1e;overflow:hidden}
.kv .k{color:var(--mut);font-size:10px;letter-spacing:.06em;text-transform:uppercase;white-space:nowrap}
.kv .kvv{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-left:12px;text-align:right;font-variant-numeric:tabular-nums}
.big{font-size:15px;font-weight:700}
td,.kv .kvv,.stat .sv,.badge{transition:background-color .8s ease}
.flash{transition:none!important;background-color:rgba(245,166,35,.28)!important}
.badge{display:inline-block;min-width:48px;text-align:center;padding:0 8px;font-size:10px;font-weight:700;
  letter-spacing:.08em;border:1px solid var(--border)}
.b-ok{color:var(--pos);background:rgba(34,197,94,.08);border-color:rgba(34,197,94,.35)}
.b-warn{color:var(--amb);background:rgba(245,166,35,.08);border-color:rgba(245,166,35,.35)}
.b-down{color:var(--neg);background:rgba(239,68,68,.08);border-color:rgba(239,68,68,.35)}
.agrid{display:grid;grid-template-columns:repeat(12,1fr);gap:3px}
.acell{aspect-ratio:1/1;background:#101112;border:1px solid var(--border);
  transition:background-color .8s ease,border-color .8s ease}
.legend{margin-top:8px;color:var(--mut);font-size:9px;letter-spacing:.06em;text-transform:uppercase;
  display:flex;gap:12px;white-space:nowrap;overflow:hidden}
.sw{display:inline-block;width:8px;height:8px;margin-right:4px}
canvas#tm{width:100%;height:auto;display:block;background:#101112;border:1px solid var(--border)}
.spark{width:60px;height:20px;display:block}
.spark polyline{fill:none;stroke:var(--amb);stroke-width:1.5}
footer{color:#5a5e66;font-size:10px;text-align:center;padding:12px;letter-spacing:.06em}
</style></head><body>
<header class=topbar>
  <span class=live><span class=dot></span>LIVE</span>
  <span class=brand><b>0N1X</b> // NETWORK MATRIX</span>
  <span class=sub id=asof>CONNECTING&#8230;</span>
  <span class=stale id=stale>&#9888; STALE &#8212; RETRYING</span>
  <span class=clock id=clock>&#8212;</span>
</header>
<div class=tape id=tape><span class=mut>loading verdict tape&#8230;</span></div>
<main class=grid>
  <section class="panel p-network"><h2>Network &#8212; OnyxRank Leaderboard<span class=hint>reputation-weighted signed outcomes</span></h2><div class=pbody>
    <div class=stats>
      <div class=stat><div class=k>Citizens</div><div class=sv id=n-cit>&#8212;</div></div>
      <div class=stat><div class=k>Proven Key</div><div class=sv id=n-key>&#8212;</div></div>
      <div class=stat><div class=k>Signed Outcomes</div><div class=sv id=n-out>&#8212;</div></div>
      <div class=stat><div class=k>Endorsed</div><div class=sv id=n-end>&#8212;</div></div>
    </div>
    <table><colgroup><col style="width:34px"><col style="width:56px"><col><col style="width:76px"><col style="width:76px"><col style="width:88px"><col style="width:44px"></colgroup>
    <thead><tr><th>#</th><th>&#916;</th><th>Agent</th><th class=n>Rep</th><th>Trend</th><th class=n>Outcomes</th><th>Key</th></tr></thead>
    <tbody id=lb></tbody></table>
  </div></section>
  <section class="panel p-treemap"><h2>Reputation Mass &#8212; Top 10<span class=hint>squarified treemap</span></h2><div class=pbody>
    <canvas id=tm width=560 height=330></canvas>
  </div></section>
  <section class="panel p-tx"><h2>Transactions / Treasury</h2><div class=pbody>
    <div class=kv><span class=k>Network</span><span class=kvv id=t-net>&#8212;</span></div>
    <div class=kv><span class=k>Treasury (live, on-chain)</span><span class="kvv big" id=t-bal>&#8212;</span></div>
    <div class=kv><span class=k>Signed verdict / outcome records</span><span class=kvv id=t-rec>&#8212;</span></div>
    <div class=kv><span class=k>Resolved outcomes</span><span class=kvv id=t-res>&#8212;</span></div>
    <div class=kv><span class=k>Block precision</span><span class=kvv id=t-prec>&#8212;</span></div>
    <div class=kv><span class=k>Public discovery index</span><span class=kvv id=t-listed>&#8212;</span></div>
    <div class=kv><span class=k>Receive address</span><span class="kvv mut" id=t-addr>&#8212;</span></div>
  </div></section>
  <section class="panel p-act"><h2>Activity &#8212; Verdict Grid<span class=hint>1 cell = 1 signed record</span></h2><div class=pbody>
    <div class=agrid id=agrid></div>
    <div class=legend>
      <span><span class=sw style="background:rgba(34,197,94,.9)"></span>pass</span>
      <span><span class=sw style="background:rgba(239,68,68,.9)"></span>block</span>
      <span><span class=sw style="background:rgba(245,166,35,.9)"></span>other</span>
      <span><span class=sw style="background:#101112;border:1px solid #232426"></span>empty &#183; brightness = recency</span>
    </div>
  </div></section>
  <section class="panel p-health"><h2>Health / Self-Healing</h2><div class=pbody>
    <div class=kv><span class=k>Overall</span><span class=kvv><span class="badge b-warn" id=h-overall>&#8212;</span></span></div>
    <div class=kv><span class=k>Routes up</span><span class=kvv id=h-up>&#8212;</span></div>
    <div class=kv><span class=k>Process uptime</span><span class=kvv id=h-upt>&#8212;</span></div>
    <table><colgroup><col><col style="width:96px"></colgroup>
    <thead><tr><th>Route</th><th>Status</th></tr></thead>
    <tbody id=hr></tbody></table>
  </div></section>
  <section class="panel p-eco"><h2>Ecosystem &#8212; CDP x402 Census<span class=hint>competitor map</span></h2><div class=pbody>
    <div class=kv><span class=k>Census sampled</span><span class=kvv id=e-samp>&#8212;</span></div>
    <div class=kv><span class=k>0n1x lane</span><span class=kvv id=e-lane>&#8212;</span></div>
    <div class=kv><span class=k>Top terms</span><span class="kvv mut" id=e-terms>&#8212;</span></div>
    <table><colgroup><col style="width:180px"><col style="width:110px"><col></colgroup>
    <thead><tr><th>Competitor</th><th>Status</th><th>Lane</th></tr></thead>
    <tbody id=er></tbody></table>
  </div></section>
</main>
<footer>0n1x &#8212; signed facts, not judgments &#183; <a href="/matrix.json">/matrix.json</a> &#183; <a href="/verify">/verify</a> &#183; <a href="/stats">/stats</a> &#183; <a href="/rank">/rank</a></footer>
<script>
'use strict';
function g(id){return document.getElementById(id)}
function esc(s){return (s===undefined||s===null)?'':String(s).replace(/[&<>]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c]})}
function fmt(v,dp){
  var n=Number(v);
  if(v===null||v===undefined||!isFinite(n))return '—';
  return n.toLocaleString('en-US',{minimumFractionDigits:dp||0,maximumFractionDigits:dp||0});
}
/* setTxt: in-place text update; on change, flash-fade background (color/opacity only, no reflow) */
function setTxt(el,txt,cls){
  if(typeof el==='string')el=g(el);
  txt=String(txt);
  if(el._v===txt&&(cls===undefined||el._c===cls))return;
  el._v=txt;
  if(cls!==undefined&&el._c!==cls){el._c=cls;el.className=cls;}
  el.textContent=txt;
  if(el._f){el.classList.add('flash');void el.offsetWidth;el.classList.remove('flash');}
  el._f=true;
}
/* quiet update (clock / timestamps / uptime): no flash */
function q(el,txt){if(typeof el==='string')el=g(el);txt=String(txt);if(el._v===txt)return;el._v=txt;el.textContent=txt;}
function vcls(v){
  v=String(v||'').toUpperCase();
  if(/BLOCK|FAIL|REJECT|DENY|SCAM|FAKE/.test(v))return 'v-bad';
  if(/ALLOW|PASS|OK|TRUE|LEGIT|VERIF|GOOD/.test(v))return 'v-ok';
  return 'v-mid';
}
function vrgb(v){
  var c=vcls(v);
  return c==='v-bad'?'239,68,68':(c==='v-ok'?'34,197,94':'245,166,35');
}
function upt(s){
  s=Math.max(0,Math.round(Number(s)||0));
  var d=Math.floor(s/86400),h=Math.floor(s%86400/3600),m=Math.floor(s%3600/60),ss=s%60;
  function p(n){return String(n).length<2?'0'+n:String(n)}
  return (d>0?d+'d ':'')+p(h)+':'+p(m)+':'+p(ss);
}
var S={hist:{},ring:new Array(60).fill(null),ringIdx:0,seen:{},seenCount:0,fail:0};
/* ---- build fixed DOM skeleton once: nothing is ever added/removed after this ---- */
(function build(){
  var h='',i;
  for(i=0;i<10;i++){
    h+='<tr><td class="n mut" id=lb'+i+'r>—</td><td class=mut id=lb'+i+'m>—</td>'+
       '<td class=mut id=lb'+i+'a>—</td><td class="n mut" id=lb'+i+'p>—</td>'+
       '<td><svg class=spark viewBox="0 0 60 20"><polyline id=lb'+i+'s points=""/></svg></td>'+
       '<td class="n mut" id=lb'+i+'o>—</td><td class=mut id=lb'+i+'k>—</td></tr>';
  }
  g('lb').innerHTML=h;
  h='';for(i=0;i<10;i++)h+='<tr><td class=mut id=hr'+i+'p>—</td><td class=mut id=hr'+i+'s>—</td></tr>';
  g('hr').innerHTML=h;
  h='';for(i=0;i<6;i++)h+='<tr><td class=mut id=er'+i+'n>—</td><td class=mut id=er'+i+'s>—</td><td class=mut id=er'+i+'l>—</td></tr>';
  g('er').innerHTML=h;
  h='';for(i=0;i<60;i++)h+='<div class=acell id=ac'+i+'></div>';
  g('agrid').innerHTML=h;
})();
/* ---- sparkline: rolling per-agent history, fixed 60x20 SVG ---- */
function drawSpark(poly,arr){
  if(!arr||!arr.length){poly.setAttribute('points','');return;}
  var a=arr.length<2?[arr[0],arr[0]]:arr;
  var mn=Math.min.apply(null,a),mx=Math.max.apply(null,a),sp=(mx-mn)||1;
  var pts='',i,x,y;
  for(i=0;i<a.length;i++){
    x=2+56*i/(a.length-1);
    y=17-14*((a[i]-mn)/sp);
    pts+=(i?' ':'')+x.toFixed(1)+','+y.toFixed(1);
  }
  poly.setAttribute('points',pts);
  var last=a[a.length-1],first=a[0];
  poly.style.stroke=last>first?'#22c55e':(last<first?'#ef4444':'#f5a623');
}
function renderNetwork(n){
  n=n||{};
  setTxt('n-cit',fmt(n.citizens_total));
  setTxt('n-key',fmt(n.proven_key));
  setTxt('n-out',fmt(n.with_signed_outcomes));
  setTxt('n-end',fmt(n.with_endorsements));
  var top=n.top10||[],i,r;
  for(i=0;i<10;i++){
    r=top[i];
    var poly=g('lb'+i+'s');
    if(r){
      setTxt('lb'+i+'r',fmt(r.rank),'n');
      var mv=r.move==='UP'?['▲ +'+r.delta,'pos']:
             r.move==='DOWN'?['▼ -'+r.delta,'neg']:
             r.move==='NEW'?['NEW','amb']:['0','mut'];
      setTxt('lb'+i+'m',mv[0],mv[1]);
      setTxt('lb'+i+'a',r.agent||'?','');
      setTxt('lb'+i+'p',fmt(r.reputation,3),'n');
      setTxt('lb'+i+'o',fmt(r.signed_outcomes),'n');
      setTxt('lb'+i+'k',r.proven_key?'✓':'—',r.proven_key?'pos':'mut');
      var nm=String(r.agent||('#'+r.rank));
      var arr=S.hist[nm]||(S.hist[nm]=[]);
      arr.push(Number(r.reputation)||0);
      if(arr.length>30)arr.shift();
      drawSpark(poly,arr);
    }else{
      setTxt('lb'+i+'r','—','n mut');setTxt('lb'+i+'m','—','mut');
      setTxt('lb'+i+'a',i===0?'no proven citizens yet':'—','mut');
      setTxt('lb'+i+'p','—','n mut');setTxt('lb'+i+'o','—','n mut');
      setTxt('lb'+i+'k','—','mut');
      drawSpark(poly,[]);
    }
  }
}
function renderTx(t){
  t=t||{};
  setTxt('t-net',t.network||'—');
  if(t.usdc_treasury_live!==null&&t.usdc_treasury_live!==undefined){
    var b=Number(t.usdc_treasury_live);
    setTxt('t-bal',fmt(b,(b>0&&b<1)?6:2)+' USDC','kvv big '+(b>0?'pos':'mut'));
  }else{
    setTxt('t-bal','UNAVAIL','kvv big amb');
  }
  setTxt('t-rec',fmt(t.signed_verdict_outcome_records));
  setTxt('t-res',fmt(t.resolved_outcomes));
  var p=t.block_precision,pt='—';
  if(typeof p==='number')pt=(p*100).toFixed(1)+'%';
  else if(p&&typeof p==='object'&&typeof p.precision==='number')pt=(p.precision*100).toFixed(1)+'%';
  else if(p!==null&&p!==undefined)pt=String(typeof p==='object'?JSON.stringify(p):p).slice(0,26);
  setTxt('t-prec',pt);
  setTxt('t-listed',t.bazaar_listed?'YES':'NO (0)','kvv '+(t.bazaar_listed?'pos':'amb'));
  var a=String(t.receive_address||'');
  q('t-addr',a.length>12?a.slice(0,6)+'…'+a.slice(-4):(a||'—'));
}
function renderHealth(h){
  h=h||{};
  var ov=h.overall||'—';
  setTxt('h-overall',ov,'badge '+(ov==='OK'?'b-ok':(ov==='DOWN'?'b-down':'b-warn')));
  setTxt('h-up',fmt(h.routes_up)+' / '+fmt(h.routes_total));
  q('h-upt',upt(h.process_uptime_seconds));
  var routes=h.routes||{},keys=Object.keys(routes).sort(),i;
  for(i=0;i<10;i++){
    var k=keys[i];
    if(k!==undefined){
      setTxt('hr'+i+'p',k,'');
      setTxt('hr'+i+'s',routes[k]?'● LIVE':'● MISSING',routes[k]?'pos':'neg');
    }else{
      setTxt('hr'+i+'p','—','mut');setTxt('hr'+i+'s','—','mut');
    }
  }
}
function renderEco(e){
  e=e||{};
  setTxt('e-samp',e.census_ok?fmt(e.census_sampled):'unavailable');
  setTxt('e-lane',e.onyx_lane||'—');
  var terms=(e.census_top_categories||[]).map(function(c){return c.term+' ('+fmt(c.count)+')'}).join(' · ');
  setTxt('e-terms',terms||'—');
  var comp=e.competitor_map||[],i,c;
  for(i=0;i<6;i++){
    c=comp[i];
    if(c){
      setTxt('er'+i+'n',c.name||'?','');
      setTxt('er'+i+'s',c.verified?'VERIFIED':'UNVERIFIED',c.verified?'pos':'mut');
      setTxt('er'+i+'l',c.lane||'—','mut');
    }else{
      setTxt('er'+i+'n','—','mut');setTxt('er'+i+'s','—','mut');setTxt('er'+i+'l','—','mut');
    }
  }
}
function renderTape(rows){
  var el=g('tape'),html;
  if(!rows||!rows.length){html='<span class=mut>no recent verdict records</span>';}
  else{
    html=rows.map(function(r){
      return '<b>'+esc(r.tool)+'</b> <span class="'+vcls(r.verdict)+'">'+esc(r.verdict||'?')+
             '</span> → '+esc(r.outcome||'?')+' <span class=mut>'+esc(r.verdict_id||'')+'</span>';
    }).join('<span class=sep>|</span>');
  }
  if(el._h!==html){el._h=html;el.innerHTML=html;}
}
/* ---- mempool-style activity grid: 60-slot ring buffer, fills L→R T→B, overwrites oldest ---- */
function updateActivity(rows){
  rows=(rows||[]).slice().sort(function(a,b){return (a.at||0)-(b.at||0)});
  rows.forEach(function(r){
    var k=String(r.verdict_id||'')+'|'+String(r.at||'')+'|'+String(r.tool||'');
    if(S.seen[k])return;
    S.seen[k]=1;S.seenCount++;
    r._k=k;
    S.ring[S.ringIdx]=r;
    S.ringIdx=(S.ringIdx+1)%60;
  });
  if(S.seenCount>600){
    S.seen={};S.seenCount=0;
    S.ring.forEach(function(ev){if(ev&&ev._k){S.seen[ev._k]=1;S.seenCount++;}});
  }
  var now=Date.now()/1000,i,ev,cell;
  for(i=0;i<60;i++){
    ev=S.ring[i];cell=g('ac'+i);
    if(!ev){
      cell.style.backgroundColor='#101112';cell.style.borderColor='#232426';cell.title='';
    }else{
      var age=Math.max(0,now-(Number(ev.at)||now));
      var alpha=Math.max(0.18,1-age/43200); /* fade over 12h, floor .18 */
      var rgb=vrgb(ev.verdict);
      cell.style.backgroundColor='rgba('+rgb+','+alpha.toFixed(2)+')';
      cell.style.borderColor='rgba('+rgb+','+Math.min(1,alpha+0.15).toFixed(2)+')';
      cell.title=(ev.tool||'?')+' '+(ev.verdict||'?')+' → '+(ev.outcome||'?');
    }
  }
}
/* ---- squarified treemap over top-10 reputation mass, fixed-size canvas ---- */
function worst(row,sum,side){
  var mx=0,mn=Infinity,i;
  for(i=0;i<row.length;i++){if(row[i].a>mx)mx=row[i].a;if(row[i].a<mn)mn=row[i].a;}
  var s2=sum*sum,sd2=side*side;
  return Math.max(sd2*mx/s2,s2/(sd2*mn));
}
function squarify(nodes,x,y,w,h){
  var rects=[],i=0;
  while(i<nodes.length&&w>0&&h>0){
    var row=[nodes[i]],rowSum=nodes[i].a;i++;
    var side=Math.min(w,h),wNow=worst(row,rowSum,side);
    while(i<nodes.length){
      var cand=rowSum+nodes[i].a;
      var w2=worst(row.concat([nodes[i]]),cand,side);
      if(w2>wNow)break;
      row.push(nodes[i]);rowSum=cand;wNow=w2;i++;
    }
    var j,n;
    if(w>=h){
      var sw=rowSum/h,yy=y;
      for(j=0;j<row.length;j++){n=row[j];rects.push({n:n,x:x,y:yy,w:sw,h:n.a/sw});yy+=n.a/sw;}
      x+=sw;w-=sw;
    }else{
      var sh=rowSum/w,xx=x;
      for(j=0;j<row.length;j++){n=row[j];rects.push({n:n,x:xx,y:y,w:n.a/sh,h:sh});xx+=n.a/sh;}
      y+=sh;h-=sh;
    }
  }
  return rects;
}
function truncText(ctx,s,w){while(s.length>1&&ctx.measureText(s).width>w)s=s.slice(0,-1);return s;}
function drawTreemap(top){
  var c=g('tm'),ctx=c.getContext('2d'),W=c.width,H=c.height;
  ctx.fillStyle='#101112';ctx.fillRect(0,0,W,H);
  var items=(top||[]).filter(function(r){return r&&Number(r.reputation)>0})
    .map(function(r){return {name:String(r.agent||'?'),v:Number(r.reputation)}})
    .sort(function(a,b){return b.v-a.v});
  ctx.font='10px ui-monospace,Consolas,monospace';
  if(!items.length){
    ctx.fillStyle='#8a8f98';ctx.textAlign='center';
    ctx.fillText('no ranked citizens yet',W/2,H/2);
    ctx.textAlign='left';return;
  }
  var total=0,i;
  for(i=0;i<items.length;i++)total+=items[i].v;
  for(i=0;i<items.length;i++)items[i].a=items[i].v*(W-2)*(H-2)/total;
  var rects=squarify(items,1,1,W-2,H-2);
  for(i=0;i<rects.length;i++){
    var rc=rects[i];
    ctx.fillStyle='hsl(145,42%,'+Math.max(10,24-i*1.6)+'%)';
    ctx.fillRect(rc.x,rc.y,rc.w,rc.h);
    ctx.strokeStyle='#232426';ctx.lineWidth=1;
    ctx.strokeRect(rc.x+0.5,rc.y+0.5,Math.max(0,rc.w-1),Math.max(0,rc.h-1));
    if(rc.w>64&&rc.h>28){
      ctx.fillStyle='#eaeaea';
      ctx.fillText(truncText(ctx,rc.n.name,rc.w-12),rc.x+6,rc.y+14);
      if(rc.h>44){ctx.fillStyle='#8a8f98';ctx.fillText(fmt(rc.n.v,3),rc.x+6,rc.y+28);}
    }
  }
}
function poll(){
  fetch('/matrix.json',{cache:'no-store'}).then(function(r){return r.json()}).then(function(d){
    S.fail=0;
    g('stale').style.opacity=0;
    q('asof','AS OF '+(d.as_of_iso||'?')+' · SERVER CACHE '+(d.refresh_seconds||30)+'S · POLL 15S');
    renderNetwork(d.network);
    renderTx(d.transactions);
    renderHealth(d.health);
    renderEco(d.ecosystem);
    var facts=((d.transactions||{}).recent_facts)||[];
    renderTape(facts);
    updateActivity(facts);
    drawTreemap((d.network||{}).top10);
  }).catch(function(){
    S.fail++;
    if(S.fail>=2)g('stale').style.opacity=1;
  });
}
function tick(){q('clock',new Date().toISOString().replace('T',' ').slice(0,19)+'Z');}
setInterval(tick,1000);tick();
poll();setInterval(poll,15000);
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
