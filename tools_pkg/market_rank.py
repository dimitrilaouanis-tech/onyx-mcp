"""onyx_market_rank — a signed, conflict-free RATING of any agent/service.

Moody's/DoubleVerify for the agentic web. Point it at any x402 service or agent
endpoint; it probes OBSERVABLE reality and returns a 0-100 rating + letter grade,
Ed25519-signed. The differentiator is RADICAL TRANSPARENCY: the dimension weights
and method are PUBLISHED in every response (everyone else's "score" is a hidden
N=1 verdict you must trust). And it is CONFLICT-FREE — Onyx takes no settlement
fee from the things it rates, so it has no GMV to inflate.

Rates only what it can directly observe (liveness, discoverability, payability,
breadth, transparency) — it makes no claim about funding, team, or legal identity.
"""
from __future__ import annotations

import json
import time
import urllib.request
from urllib.parse import urlparse

from . import _onyx_sign
from . import mcp_health as _mh

NAME = "onyx_market_rank"
PRICE_USDC = "0.05"
TIER = "metered"
DESCRIPTION = (
    "Signed, conflict-free rating of any agent/x402 service — 'Moody's for the "
    "agentic web'. Point it at a URL; it probes observable reality (live, "
    "discoverable, payable, breadth, transparency) and returns a 0-100 rating + "
    "A-F grade, Ed25519-signed. Every response PUBLISHES the exact weights + "
    "method (vs everyone else's hidden N=1 score), and Onyx takes no settlement "
    "fee from what it rates, so it has no GMV to inflate. Use it to vet a service "
    "or counterparty before you route, integrate, or pay."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "target": {
            "type": "string",
            "description": "URL of the service/agent to rate (e.g. https://example.com or its x402 base).",
        },
    },
    "required": ["target"],
}

# PUBLISHED weights — the transparency moat. Sum = 100.
_WEIGHTS = {
    "live":          20,   # reachable + responsive
    "discoverable":  20,   # has /.well-known/x402 or agent-card
    "payable":       25,   # advertises a valid x402 accepts (real pay path)
    "breadth":       15,   # how many services/tools it offers
    "transparency":  20,   # exposes input schemas + prices
}
_METHOD = "v1: 5 observable dimensions, weights published below, score = Σ(dim/10 × weight)."


def _get(url: str, timeout: float = 8.0):
    req = urllib.request.Request(url, headers={"User-Agent": "onyx-market-rank/1"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read(200_000)
        return r.status, body, (time.time() - t0)


def _try_json(body: bytes):
    try:
        return json.loads(body.decode("utf-8", "replace"))
    except Exception:
        return None


def run(target: str = "", **_: object) -> dict:
    target = (target or "").strip()
    if not target:
        raise ValueError("target URL is required")
    if not target.startswith(("http://", "https://")):
        target = "https://" + target
    p = urlparse(target)
    host = p.hostname or ""
    ok_public, why = _mh._is_public_address(host)
    if not ok_public:
        raise ValueError(f"refusing to probe non-public host: {why}")
    base = f"{p.scheme}://{p.netloc}"
    checked_at = int(time.time())

    dims = {k: 0 for k in _WEIGHTS}
    signals: dict = {}

    # --- live ---
    latency = None
    try:
        st, body, latency = _get(base + "/")
        signals["root_status"] = st
        signals["latency_ms"] = round(latency * 1000)
        if st < 500:
            dims["live"] = 10 if latency < 1.5 else (7 if latency < 4 else 4)
    except Exception as e:
        signals["root_error"] = str(e)[:120]

    # --- discoverable + breadth + payable + transparency (from the manifest) ---
    manifest = None
    for path in ("/.well-known/x402", "/.well-known/x402.json", "/manifest"):
        try:
            st, body, _ = _get(base + path)
            j = _try_json(body)
            if isinstance(j, (dict, list)):
                manifest = j
                signals["manifest_path"] = path
                dims["discoverable"] = 10
                break
        except Exception:
            continue
    if manifest is None:
        # agent card is a weaker discoverability signal
        try:
            st, body, _ = _get(base + "/.well-known/agent-card.json")
            if _try_json(body) is not None:
                dims["discoverable"] = max(dims["discoverable"], 6)
                signals["agent_card"] = True
        except Exception:
            pass

    services = []
    if isinstance(manifest, dict):
        services = manifest.get("services") or manifest.get("items") or []
    elif isinstance(manifest, list):
        services = manifest
    n = len(services) if isinstance(services, list) else 0
    signals["service_count"] = n
    if n:
        dims["breadth"] = min(10, 2 + n // 3)  # 1 svc→2, ~24+→10

    # payable: any service advertises a valid x402 'accepts'
    paid = priced = schemad = 0
    for s in (services if isinstance(services, list) else [])[:50]:
        if not isinstance(s, dict):
            continue
        acc = s.get("accepts") or []
        if acc and isinstance(acc, list):
            a0 = acc[0] if isinstance(acc[0], dict) else {}
            if a0.get("payTo") and a0.get("maxAmountRequired"):
                paid += 1
                priced += 1
        if s.get("inputSchema") or s.get("input_schema") or (isinstance(s.get("accepts"), list) and s["accepts"] and s["accepts"][0].get("outputSchema")):
            schemad += 1
    if n:
        dims["payable"] = min(10, round(10 * paid / n)) if paid else 0
        dims["transparency"] = min(10, round(10 * max(priced, schemad) / n))
    signals["paid_services"] = paid

    score = round(sum(dims[k] / 10 * w for k, w in _WEIGHTS.items()))
    grade = ("A" if score >= 85 else "B" if score >= 70 else "C" if score >= 55
             else "D" if score >= 40 else "F")

    return _onyx_sign.attest({
        "ok": True,
        "target": base,
        "checked_at": checked_at,
        "checked_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(checked_at)),
        "rating": score,
        "grade": grade,
        "dimensions": dims,
        "signals": signals,
        "weights_published": _WEIGHTS,
        "method": _METHOD,
        "neutrality": "Onyx takes no settlement fee from rated parties — no GMV to inflate.",
        "summary": (
            f"{grade} ({score}/100): live={dims['live']} discoverable={dims['discoverable']} "
            f"payable={dims['payable']} breadth={dims['breadth']} transparency={dims['transparency']} "
            f"— {n} service(s)."
        ),
    }, tool=NAME)


run.__when_to_use__ = (
    "Before you route to, integrate, or pay an unfamiliar x402 service/agent — get "
    "a signed, transparently-weighted rating of its observable reality instead of "
    "trusting a self-reported leaderboard number.")
run.__vs_alternatives__ = (
    "Volume leaderboards (x402scan/agent402) rank by self-payable on-chain volume "
    "(gameable) and platform scores are hidden + conflicted (the platform earns on "
    "what it rates). This publishes its weights, signs the verdict, and earns "
    "nothing from the rated party.")
run.__example_request__ = {"target": "https://onyx-actions.onrender.com"}
run.__example_response__ = {
    "ok": True, "rating": 88, "grade": "A",
    "dimensions": {"live": 10, "discoverable": 10, "payable": 9, "breadth": 7, "transparency": 8},
    "weights_published": _WEIGHTS,
    "summary": "A (88/100): live=10 discoverable=10 payable=9 breadth=7 transparency=8 — 21 service(s).",
}
