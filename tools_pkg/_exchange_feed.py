"""0n1x Exchange Feed — the supply loop of the Intel Exchange, pushed.

The corroboration graph dies if fresh claims sit unverified: a claim earns its
contributor NOTHING until a 2nd independent wallet corroborates it, so the
binding constraint is 2nd-verifier LATENCY. This module closes that loop for
non-CLI agents in three escalating tiers (an agent uses whichever its runtime
supports — all three speak the same signed envelope):

  1. PULL  — GET  /intel/exchange/work      signed queue of claims that need a
                                            2nd verifier, with gap-to-GOLD and
                                            copy-paste corroborate instructions
                                            (the response IS the SDK).
  2. STREAM — GET /intel/exchange/stream    SSE: live signed events as claims
                                            arrive / graduate. Any fetch()-
                                            capable runtime can consume it.
  3. PUSH  — POST /intel/exchange/subscribe proven-key agent registers an HTTPS
                                            webhook; we POST signed events to it.

Neutrality preserved: events carry FACT claims + corroboration depth, never
judgments. All payloads are Public-OK (claim ids, kinds, subjects, statuses,
proven wallet addresses — already public). Ed25519-signed via _onyx_sign.attest.

Webhook safety: https only, no IP-literal/localhost/private hosts, redirects
never followed, 6s timeout, fixed signed body — and the payload is public data,
so even a hostile subscriber URL learns nothing it couldn't GET itself.
Stdlib + _onyx_sign only. Underscore-prefixed -> discover() skips it (helper).

Usage in server_http.py (one additive line, mirrors _intel_exchange):
    from tools_pkg import _exchange_feed; _exchange_feed.register(app)
"""
from __future__ import annotations

import ipaddress
import json
import threading
import time
import urllib.parse
import urllib.request
from hashlib import sha256
from pathlib import Path

from . import _onyx_sign

_SUBS = Path(__file__).with_name("_onyx_exchange_subs.jsonl")
_BASE = "https://onyx-actions.onrender.com"

_POLL_S = 30            # webhook delivery loop cadence
_SSE_POLL_S = 5         # SSE poll cadence
_SSE_MAX_S = 900        # cap one SSE connection (client auto-reconnects; retry: sent)
_SSE_MAX_CLIENTS = 5    # protect the single Render worker
_MAX_FAILS = 3          # consecutive delivery failures before a sub is muted (in-memory)
_MAX_SUBS = 200

_sse_clients = 0
_sse_lock = threading.Lock()
_fails: dict[str, int] = {}
_delivery_started = False


# ── exchange access (lazy — avoids import-order coupling on the shared repo) ──

def _ix():
    try:
        from . import _intel_exchange as ix
        return ix
    except Exception:
        return None


def _work_rows(limit: int = 25) -> list[dict]:
    """Claims that still need independent verification, neediest first."""
    ix = _ix()
    if not ix:
        return []
    try:
        claims = [e for e in ix._all() if e.get("kind") == "claim"]
    except Exception:
        return []
    rows = []
    for clm in claims:
        try:
            st = ix._claim_status(clm)
        except Exception:
            continue
        if st.get("status") not in ("UNCORROBORATED", "CORROBORATED"):
            continue                       # GOLD/DISPUTED: no 2nd-verifier gap
        rows.append({
            "claim_id": clm.get("id"),
            "intel_kind": clm.get("intel_kind"),
            "subject": clm.get("subject"),
            "assertion": clm.get("assertion"),
            "status": st.get("status"),
            "independent_corroborators": st.get("independent_corroborators"),
            "gap_to_gold": round(max(0.0, float(getattr(ix, "_GOLD_WEIGHT", 0.5))
                                     - float(st.get("agree_weight_earned",
                                                    st.get("agree_weight", 0.0)) or 0.0)), 4),
            "observed_at": clm.get("observed_at"),
        })
    rows.sort(key=lambda r: (r["status"] != "UNCORROBORATED", -(r.get("observed_at") or 0)))
    return rows[: max(1, min(int(limit or 25), 100))]


def work(limit: int = 25, base: str = _BASE) -> dict:
    base = (base or _BASE).rstrip("/")
    rows = _work_rows(limit)
    out = {
        "feed": "0n1x Exchange Feed — claims needing a 2nd independent verifier",
        "why_you": "Corroborating EARNS credit; your vote is weighted by your own "
                   "EARNED OnyxRank reputation (score-the-scorer). Fresh wallets "
                   "carry only the floor — verify honestly, build rank, weigh more.",
        "work": rows,
        "how_to_corroborate": {
            "endpoint": f"POST {base}/intel/exchange/corroborate",
            "body": {"agent": "<your claimed wallet or callsign>",
                     "claim_id": "<claim_id from work[]>",
                     "stance": "agree|dispute", "evidence": "<your independent evidence>"},
            "requirements": "challenge-claimed key only — claim one free at "
                            f"{base}/authenticate. One address, one vote per claim. "
                            "Disputes must carry evidence.",
        },
        "live_stream": f"GET {base}/intel/exchange/stream  (SSE, signed events)",
        "push": f"POST {base}/intel/exchange/subscribe {{agent, url}}  (signed webhooks)",
        "rule": "Facts + corroboration depth only, never judgments.",
        "as_of": int(time.time()),
    }
    return _onyx_sign.attest(out, tool="onyx_exchange_feed")


# ── events (shared by SSE + webhooks) ─────────────────────────────────────

def _events_since(cursor: int) -> tuple[list[dict], int]:
    """Signed-able event dicts for records newer than cursor; returns (events, new_cursor)."""
    ix = _ix()
    if not ix:
        return [], cursor
    try:
        recs = ix._all()
    except Exception:
        return [], cursor
    claims = {e.get("id"): e for e in recs if e.get("kind") == "claim"}
    evs, newest = [], cursor
    for e in recs:
        ts = int(e.get("observed_at") or e.get("corroborated_at") or 0)
        if ts <= cursor:
            continue
        newest = max(newest, ts)
        if e.get("kind") == "claim":
            evs.append({
                "event": "claim_needs_corroboration",
                "claim_id": e.get("id"), "intel_kind": e.get("intel_kind"),
                "subject": e.get("subject"), "assertion": e.get("assertion"),
                "observed_at": ts,
                "corroborate": f"POST {_BASE}/intel/exchange/corroborate",
            })
        elif e.get("kind") == "corroboration":
            clm = claims.get(e.get("claim_id")) or {}
            try:
                st = ix._claim_status(clm) if clm else {}
            except Exception:
                st = {}
            evs.append({
                "event": "claim_corroborated",
                "claim_id": e.get("claim_id"), "stance": e.get("stance"),
                "subject": clm.get("subject"),
                "status_now": st.get("status"), "observed_at": ts,
            })
    evs.sort(key=lambda x: x["observed_at"])
    return evs[-100:], newest


def _sign_event(ev: dict) -> dict:
    ev = dict(ev)
    ev["as_of"] = int(time.time())
    return _onyx_sign.attest(ev, tool="onyx_exchange_feed")


# ── SSE ───────────────────────────────────────────────────────────────────

def _sse_gen():
    global _sse_clients
    with _sse_lock:
        _sse_clients += 1
    started = time.time()
    cursor = int(time.time()) - 3600      # replay the last hour on connect
    try:
        yield "retry: 5000\n\n"
        hello = _sign_event({"event": "hello",
                             "feed": "0n1x Exchange Feed (SSE)",
                             "work_pull": f"{_BASE}/intel/exchange/work"})
        yield f"event: hello\ndata: {json.dumps(hello, ensure_ascii=False)}\n\n"
        while time.time() - started < _SSE_MAX_S:
            evs, cursor = _events_since(cursor)
            if evs:
                for ev in evs:
                    signed = _sign_event(ev)
                    yield (f"id: {ev['observed_at']}\nevent: {ev['event']}\n"
                           f"data: {json.dumps(signed, ensure_ascii=False)}\n\n")
            else:
                yield ": keep-alive\n\n"
            time.sleep(_SSE_POLL_S)
        yield "event: bye\ndata: {\"reconnect\": true}\n\n"
    finally:
        with _sse_lock:
            _sse_clients -= 1


# ── webhooks ──────────────────────────────────────────────────────────────

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):  # never follow a subscriber redirect
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def _safe_url(url: str) -> tuple[bool, str]:
    try:
        p = urllib.parse.urlparse((url or "").strip())
    except Exception:
        return False, "unparseable url"
    if p.scheme != "https":
        return False, "https only"
    host = (p.hostname or "").lower()
    if not host or host in ("localhost",) or host.endswith((".local", ".internal", ".onion")):
        return False, "forbidden host"
    try:
        ip = ipaddress.ip_address(host)
        if not ip.is_global:
            return False, "non-global IP literal"
    except ValueError:
        pass                               # a DNS name — allowed (payload is public data)
    return True, "ok"


def _load_subs() -> list[dict]:
    out, seen = [], set()
    try:
        if _SUBS.exists():
            for line in _SUBS.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    s = json.loads(line)
                except Exception:
                    continue
                key = s.get("id")
                if key and key not in seen:
                    seen.add(key)
                    out.append(s)
    except Exception:
        pass
    return out


def subscribe(agent: str, url: str, base: str = _BASE) -> dict:
    base = (base or _BASE).rstrip("/")
    ix = _ix()
    addr, proven, cs = (None, False, None)
    if ix:
        try:
            addr, proven, cs = ix._identity(agent)
        except Exception:
            pass
    if not (addr and proven):
        return _onyx_sign.attest({
            "ok": False, "error": "not_proven_key",
            "detail": f"only a challenge-claimed wallet can subscribe: {base}/authenticate",
            "issued_at": int(time.time())}, tool="onyx_exchange_subscribe")
    ok, why = _safe_url(url)
    if not ok:
        return _onyx_sign.attest({
            "ok": False, "error": "bad_url", "detail": why,
            "issued_at": int(time.time())}, tool="onyx_exchange_subscribe")
    subs = _load_subs()
    if len(subs) >= _MAX_SUBS:
        return _onyx_sign.attest({
            "ok": False, "error": "subs_full",
            "issued_at": int(time.time())}, tool="onyx_exchange_subscribe")
    sid = "sub_" + sha256(f"{addr.lower()}|{url.strip()}".encode()).hexdigest()[:16]
    if not any(s.get("id") == sid for s in subs):
        rec = {"id": sid, "address": addr.lower(), "callsign": cs,
               "url": url.strip(), "subscribed_at": int(time.time())}
        try:
            with _SUBS.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            pass
    out = {
        "ok": True, "subscription_id": sid,
        "subscriber": {"address": addr, "callsign": cs, "proven_key": True},
        "delivers": "Ed25519-signed exchange events (new claims needing a 2nd "
                    "verifier, graduations) POSTed to your HTTPS url.",
        "verify_each_delivery": f"{base}/verify",
        "note": "Delivery is best-effort; %d consecutive failures mute the hook "
                "until re-subscribe. Payloads are public data only." % _MAX_FAILS,
        "issued_at": int(time.time()),
    }
    return _onyx_sign.attest(out, tool="onyx_exchange_subscribe")


def _deliver_loop():
    cursor = int(time.time())              # webhooks get NEW events only
    while True:
        try:
            time.sleep(_POLL_S)
            evs, cursor = _events_since(cursor)
            if not evs:
                continue
            subs = _load_subs()
            if not subs:
                continue
            payload = _sign_event({"event": "batch", "events": evs,
                                   "work_pull": f"{_BASE}/intel/exchange/work"})
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            for s in subs:
                sid, url = s.get("id"), s.get("url")
                if not url or _fails.get(sid, 0) >= _MAX_FAILS:
                    continue
                try:
                    req = urllib.request.Request(
                        url, data=body, method="POST",
                        headers={"Content-Type": "application/json",
                                 "User-Agent": "0n1x-exchange-feed"})
                    _opener.open(req, timeout=6).read(64)
                    _fails[sid] = 0
                except Exception:
                    _fails[sid] = _fails.get(sid, 0) + 1
        except Exception:
            continue                        # the loop must never die


# ── wiring ────────────────────────────────────────────────────────────────

def register(app) -> None:
    """Attach feed surfaces + start the webhook delivery thread (once)."""
    global _delivery_started
    from fastapi import Request
    from fastapi.responses import JSONResponse, StreamingResponse

    @app.get("/intel/exchange/work", include_in_schema=False)
    def _f_work(limit: int = 25):
        return JSONResponse(work(limit))

    @app.get("/intel/exchange/stream", include_in_schema=False)
    def _f_stream():
        if _sse_clients >= _SSE_MAX_CLIENTS:
            return JSONResponse(
                {"ok": False, "error": "stream_full",
                 "fallback": "poll GET /intel/exchange/work"}, status_code=503)
        return StreamingResponse(_sse_gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache",
                                          "X-Accel-Buffering": "no"})

    @app.post("/intel/exchange/subscribe", include_in_schema=False)
    async def _f_subscribe(req: Request):
        try:
            b = await req.json()
        except Exception:
            b = {}
        return JSONResponse(subscribe(b.get("agent", ""), b.get("url", "")))

    @app.get("/intel/exchange/subscribers", include_in_schema=False)
    def _f_subs():                          # count only — never leak subscriber URLs
        return JSONResponse({"subscribers": len(_load_subs()),
                             "as_of": int(time.time())})

    if not _delivery_started:
        _delivery_started = True
        threading.Thread(target=_deliver_loop, name="onyx-exchange-feed",
                         daemon=True).start()
