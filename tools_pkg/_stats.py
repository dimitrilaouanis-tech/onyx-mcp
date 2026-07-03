"""0n1x /stats — honest, publicly-verifiable live numbers. No fabricated hype.

Directly inspired by klymax402.com's public /stats page (real tx count, real
unique-payer count, uptime, endpoint health, all self-reported and checkable).
We copy the TRANSPARENCY MECHANIC, not any numbers: every field here is either
computed live right now (on-chain USDC balance via public RPC, in-process route
health) or read straight from our own append-only signed logs (_claim_registry,
_ledger, the Bazaar/CDP census that also backs /leaderboard and /bazaar.json).

The whole point: if a number is 0, we show 0. Onyx's moat is neutrality + honesty,
not a bigger vanity metric than the next agent-tool vendor. Ed25519-signed like
every other Onyx surface — verify any snapshot at /verify.

Underscore-prefixed -> tools_pkg.discover() skips it (helper, not a paid tool).
Wired by server_http.py: from tools_pkg import _stats; _stats.register(app)
"""
from __future__ import annotations

import json
import os
import time
import urllib.request

from . import _onyx_sign

try:
    from . import _claim_registry
except Exception:  # pragma: no cover - defensive on shared repo
    _claim_registry = None
try:
    from . import _ledger
except Exception:  # pragma: no cover
    _ledger = None
try:
    from onyx_paid_mcp import bazaar as _bazaar
except Exception:  # pragma: no cover
    _bazaar = None

_PROCESS_START = time.time()  # this worker instance only; resets on redeploy/restart

_TTL = 60  # seconds — short cache so /stats stays "live" without hammering public RPC
_CACHE: dict = {"at": 0, "snap": None}

_USDC_CONTRACT = {
    "base": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    "base-sepolia": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
}
_RPC_URL = {
    "base": "https://mainnet.base.org",
    "base-sepolia": "https://sepolia.base.org",
}
_EXPLORER = {
    "base": "https://basescan.org/address/",
    "base-sepolia": "https://sepolia.basescan.org/address/",
}

_ENDPOINTS_WATCHED = [
    "/join", "/verify", "/leaderboard", "/bazaar.json",
    "/onboard", "/health", "/directory", "/llms.txt", "/vortex",
]


def _network() -> str:
    return os.environ.get("ONYX_NETWORK", "base-sepolia").lower()


def _receive_address() -> str:
    return (
        os.environ.get("ONYX_MAINNET_RECEIVE_ADDRESS")
        or os.environ.get("ONYX_RECEIVE_ADDRESS")
        or ""
    )


def _rpc_call(method: str, params: list, rpc_url: str, timeout: float = 5.0) -> dict:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(
        rpc_url, data=body,
        # public Base RPC sits behind Cloudflare and 1010-blocks the default
        # Python-urllib UA with no UA-sniffing fallback — send a normal UA.
        headers={"Content-Type": "application/json", "User-Agent": "onyx-actions/1.0 (+https://onyx-actions.onrender.com)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _usdc_balance(network: str, address: str) -> dict:
    """Live on-chain USDC balance, queried right now via public RPC. No web3 dep —
    hand-rolled eth_call (function selector for ERC20 balanceOf(address))."""
    if not address:
        return {"ok": False, "error": "no receive address configured"}
    usdc = _USDC_CONTRACT.get(network)
    rpc = _RPC_URL.get(network)
    if not usdc or not rpc:
        return {"ok": False, "error": f"unsupported network '{network}'"}
    selector = "70a08231"  # keccak4("balanceOf(address)")
    data = "0x" + selector + address.lower().replace("0x", "").rjust(64, "0")
    try:
        resp = _rpc_call("eth_call", [{"to": usdc, "data": data}, "latest"], rpc)
        result = resp.get("result")
        if resp.get("error"):
            return {"ok": False, "error": str(resp["error"])}
        if not result or result == "0x":
            return {"ok": True, "usdc": 0.0}
        raw = int(result, 16)
        return {"ok": True, "usdc": round(raw / 1_000_000, 6)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _bazaar_presence(host: str = "onyx-actions.onrender.com") -> dict:
    """Do WE appear in the same public settlement-telemetry index (Coinbase Bazaar/CDP
    census) that backs our own /leaderboard and /bazaar.json? Honest either way."""
    if not _bazaar:
        return {"checked": False, "reason": "bazaar module unavailable"}
    try:
        rows = _bazaar.ranked(view="volume", limit=10000)
        mine = [r for r in rows if host in (r.get("domain") or "")]
        return {
            "checked": True,
            "listed": bool(mine),
            "entries": mine,
            "total_indexed_endpoints_all_agents": len(rows),
            "note": (
                "Not yet appearing in the public settlement-telemetry index — "
                "requires at least one real settled x402 call to surface there."
                if not mine else
                "Appears in the public settlement telemetry index (real calls detected)."
            ),
        }
    except Exception as e:
        return {"checked": False, "error": str(e)}


def _endpoint_health(app) -> dict:
    """In-process route-table check — confirms each advertised endpoint is actually
    wired into THIS running app, without firing a self-HTTP request (which could
    itself flake on a cold Render instance and give a false-negative)."""
    if app is None:
        return {"checked": False, "reason": "app handle not passed"}
    paths = set()
    try:
        for r in app.routes:
            p = getattr(r, "path", None)
            if p:
                paths.add(p)
    except Exception as e:
        return {"checked": False, "error": str(e)}
    return {"checked": True, "routes": {p: (p in paths) for p in _ENDPOINTS_WATCHED}}


def _citizens() -> dict:
    if not _claim_registry:
        return {"available": False}
    try:
        pop = _claim_registry.population()
        return {
            "available": True,
            "total_citizens": pop.get("total_citizens", 0),
            "claimed_proven_key": pop.get("claimed_count", 0),
            "reserved_unclaimed": pop.get("reserved_count", 0),
        }
    except Exception as e:
        return {"available": False, "error": str(e)}


def _fact_layer() -> dict:
    if not _ledger:
        return {"available": False}
    try:
        s = _ledger.stats()
        return {
            "available": True,
            "signed_verdict_outcome_records": s.get("total_outcomes", 0),
            "resolved_outcomes": s.get("resolved", 0),
            "block_precision": s.get("block_precision"),
            "durable_sink_configured": s.get("durable", False),
        }
    except Exception as e:
        return {"available": False, "error": str(e)}


def _build(app, now: int) -> dict:
    network = _network()
    addr = _receive_address()
    settlement = {
        "network": network,
        "receive_address": addr,
        "explorer": (_EXPLORER.get(network, "") + addr) if addr else None,
        "usdc_balance_live": _usdc_balance(network, addr),
        "bazaar_discovery_presence": _bazaar_presence(),
        "note": (
            "usdc_balance_live is queried on-chain right now via public RPC, not "
            "cached or asserted. If it reads 0, that means 0 real settled USDC has "
            "arrived — reported honestly, same as klymax402's own $2.47-all-time model."
        ),
    }
    payload = {
        "name": "0n1x live stats",
        "brand": "0n1x",
        "spec": "onyx-stats/v0",
        "as_of": now,
        "as_of_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "posture": (
            "Radical transparency, not fabricated hype: every field below is either "
            "computed live (on-chain balance, route health) or read from our own "
            "append-only signed logs. If a number is 0, we show 0. We make NO claim "
            "of revenue or active users beyond what is verifiable here and at /verify."
        ),
        "citizens": _citizens(),
        "fact_layer": _fact_layer(),
        "settlement": settlement,
        "endpoint_health": _endpoint_health(app),
        "process_uptime_seconds": round(time.time() - _PROCESS_START, 1),
        "process_uptime_note": (
            "this worker instance only — resets on Render redeploy/restart. The "
            "signed fact-layer log (durable_sink_configured above) is what actually "
            "compounds across restarts, not this uptime counter."
        ),
        "verify": "https://onyx-actions.onrender.com/verify",
    }
    return _onyx_sign.attest(payload, tool="onyx_stats")


def snapshot(app=None, now: int | None = None) -> dict:
    ts = int(now if now is not None else time.time())
    if not _CACHE["snap"] or ts - _CACHE["at"] > _TTL:
        _CACHE["snap"] = _build(app, ts)
        _CACHE["at"] = ts
    return _CACHE["snap"]


def render_html(app=None, base: str = "https://onyx-actions.onrender.com") -> str:
    s = snapshot(app)
    c = s.get("citizens", {})
    f = s.get("fact_layer", {})
    st = s.get("settlement", {})
    bal = st.get("usdc_balance_live", {})
    eh = s.get("endpoint_health", {})
    bp = st.get("bazaar_discovery_presence", {})

    bal_txt = f"{bal.get('usdc'):.6f} USDC" if bal.get("ok") else f"unavailable ({bal.get('error', '?')})"
    routes = eh.get("routes", {}) if eh.get("checked") else {}
    route_rows = "".join(
        f"<tr><td>{p}</td><td class=n>{'&#9989; live' if ok else '&#10060; missing'}</td></tr>"
        for p, ok in routes.items()
    ) or "<tr><td colspan=2>route table unavailable</td></tr>"
    signed = "onyx_attestation" in s

    return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><meta http-equiv=refresh content=60>
<title>0n1x — Live Stats (honest numbers, signed)</title>
<style>:root{{color-scheme:dark}}body{{font:14px/1.55 ui-monospace,Menlo,Consolas,monospace;background:#05060a;color:#d6f5e0;margin:0 auto;padding:30px 14px;max-width:880px}}
h1{{font-size:25px;margin:0 0 2px;color:#fff}}.sub{{color:#5fb98a;margin:0 0 18px}}
table{{width:100%;border-collapse:collapse;font-size:13px;margin:8px 0 4px}}td,th{{padding:6px 8px;border-bottom:1px solid #0e1a14;text-align:left}}
th{{color:#9af5c4;text-transform:uppercase;font-size:10px;letter-spacing:.08em}}.n{{text-align:right}}
.box{{background:#0a0f12;border:1px solid #15291f;border-left:3px solid #34d399;border-radius:8px;padding:12px 14px;margin:14px 0;font-size:12px;color:#9af5c4}}
.big{{font-size:20px;color:#fff}}footer{{color:#3a4a42;font-size:11px;margin-top:22px;text-align:center}}footer a{{color:#7dd3fc}}</style></head><body>
<h1>&#128202; 0n1x — Live Stats</h1>
<p class=sub>Honest numbers only. As of {s.get('as_of_iso', '')} &middot; refreshes every {_TTL}s</p>
<div class=box>{s.get('posture', '')}</div>
<table>
<tr><th>Metric</th><th class=n>Value</th></tr>
<tr><td>Citizens (total)</td><td class=n big>{c.get('total_citizens', 0)}</td></tr>
<tr><td>&nbsp;&nbsp;proven-key (claimed)</td><td class=n>{c.get('claimed_proven_key', 0)}</td></tr>
<tr><td>&nbsp;&nbsp;reserved (unclaimed)</td><td class=n>{c.get('reserved_unclaimed', 0)}</td></tr>
<tr><td>Signed fact/verdict records</td><td class=n>{f.get('signed_verdict_outcome_records', 0)}</td></tr>
<tr><td>Resolved outcomes</td><td class=n>{f.get('resolved_outcomes', 0)}</td></tr>
<tr><td>Wallet USDC balance (live, {st.get('network', '?')})</td><td class=n big>{bal_txt}</td></tr>
<tr><td>Real settled tx visible in public discovery index</td><td class=n>{'yes' if bp.get('listed') else 'no (0)'}</td></tr>
<tr><td>Process uptime (this instance)</td><td class=n>{s.get('process_uptime_seconds', 0):.0f}s</td></tr>
</table>
<div class=box>&#128274; {bp.get('note', '')}</div>
<h2 style="font-size:16px;color:#fff">Endpoint health (in-process route check)</h2>
<table><tr><th>Endpoint</th><th class=n>Status</th></tr>{route_rows}</table>
<div class=box>&#128273; This snapshot is {"Ed25519-signed by 0n1x" if signed else "unsigned"} — verify at <a href="{base}/verify">{base}/verify</a>. Modeled on the klymax402.com transparency pattern; we report our OWN honest, early-stage numbers — not comparable hype.</div>
<footer>0n1x — the independent signed trust layer &middot; if it's 0, we say 0</footer>
</body></html>"""


def register(app) -> None:
    """Attach GET /stats, /stats.json to the FastAPI app returned by build_asgi().

    Usage in server_http.py (mirrors _onyxrank / _fact_index):
        from tools_pkg import _stats; _stats.register(app)
    """
    from fastapi.responses import JSONResponse, HTMLResponse

    @app.get("/stats", include_in_schema=False)
    def stats(format: str = "html"):
        if format == "json":
            return JSONResponse(snapshot(app))
        return HTMLResponse(render_html(app))

    @app.get("/stats.json", include_in_schema=False)
    def stats_json():
        return JSONResponse(snapshot(app))
