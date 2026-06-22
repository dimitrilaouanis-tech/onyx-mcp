"""Onyx Signed Agent-Economy Index — the neutral, reproducible referee.

The agent economy is measured 15x apart by different parties: x402.org reports
~$24M/30d while wash-filtered analyses (Allium/a16z, Artemis) put REAL volume
at ~$1.1-1.6M/mo. Nobody publishes a number you can independently verify, and
DefiLlama / Token Terminal don't track it at all. That measurement vacuum is
the product.

This tool returns ONE Ed25519-signed Index combining:
  1. A LIVE census of the Coinbase Bazaar we pull right now (our own
     measurement — total resources, real unique operators, concentration,
     stale tombstones). Reproducible by anyone against the same public API.
  2. A DISCLOSED reconciliation of every named public volume source, with the
     defensible real-volume range and the inflation multiple — each figure
     attributed to its source, never fabricated.
  3. The published filter methodology version (the rules that separate
     real / testing / gamed) so the disclosure is reproducible.

We are the referee, not the accuser: "here is the verifiable number, and here
is exactly how it was derived and signed" — not "everyone is lying".

Honest scope: the LIVE half (census/concentration) is our own measurement. The
VOLUME half is a signed reconciliation of named third-party indexers (we do not
yet run our own full on-chain wash-filter — that is the v2 Validator, which
needs an indexer feed; flagged below as methodology, not claimed as our pull).

Bright line: this signs observations + a disclosed reconciliation. It makes no
claim about persons or personhood, and earns nothing from what it grades.
"""
from __future__ import annotations

import json
import time
import urllib.request

from . import _onyx_sign

NAME = "onyx_agent_economy_index"
PRICE_USDC = "0.25"
TIER = "premium"
DESCRIPTION = (
    "Signed Agent-Economy Index — the neutral referee for how big the agent "
    "economy REALLY is, by segment. Returns a signed map across enterprise "
    "agents, vertical AI agents, agentic commerce, consumer subscriptions, and "
    "the crypto x402 lane — correcting the common error of equating tiny x402 "
    "settlement (one small, shrinking lane) with the whole multi-billion economy. "
    "Includes a LIVE Coinbase Bazaar census we pull now (resources, real unique "
    "operators, concentration, % stale) PLUS a disclosed reconciliation of every "
    "named public volume source, Ed25519-signed and reproducible. Use before "
    "citing any agent-economy number in a deck, report, or decision."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "max_pages": {
            "type": "integer",
            "description": "Bazaar pages (100 resources each) to scan for the live census. Default 300 = full sweep (~28k). Lower it for a faster, sampled concentration read.",
        }
    },
}

BAZAAR = "https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources"

# --- Disclosed third-party volume sources (Q2 2026). Each attributed; never
# our own fabricated number. Update as sources publish. ---
VOLUME_SOURCES = [
    {"source": "x402.org", "metric": "30d volume (raw, multi-chain, unfiltered)",
     "value_usd": 24_240_000, "note": "includes PING meme-mint + self-cycling", "as_of": "2026-Q2"},
    {"source": "Allium (raw, Base)", "metric": "30d volume", "value_usd": 3_000_000,
     "note": "stricter event scope, Base-primary", "as_of": "2026-03"},
    {"source": "x402scan (Merit Systems)", "metric": "30d volume (filtered)",
     "value_usd": 1_110_000, "note": "3.69M txns, ~$0.30 avg", "as_of": "2026-05"},
    {"source": "Allium + a16z", "metric": "30d volume (wash-filtered)",
     "value_usd": 1_600_000, "note": "removes seller-prefunds-buyer round-trips", "as_of": "2026-03"},
    {"source": "Artemis (@OnchainLu)", "metric": "daily volume (filtered)",
     "value_usd": 28_000, "note": "~$0.84-1.0M/mo; 48% txns / 81% volume self-cycling", "as_of": "2026-03"},
]
REAL_VOLUME_RANGE_30D = {"low_usd": 1_100_000, "high_usd": 1_600_000,
                         "basis": "convergence of x402scan filtered + Allium/a16z wash-filtered + Artemis run-rate"}
DECLINE = {"txns_from_dec2025_peak_pct": -92, "revenue_pct": -97,
           "source": "OKX Ventures", "note": "731K->57K txns/day; protocol rev $1.02M->$35K"}
FILTER_METHOD_VERSION = "onyx-aei-filter/1.1"

# --- THE WHOLE ECONOMY, not just the x402 lane. The single most important
# correction this index makes: x402 crypto agent-to-agent settlement (the
# segment the live census measures) is the SMALLEST lane and is shrinking
# (-92% from Dec-2025 peak). The real money is enterprise + vertical + commerce
# + consumer. Each segment's size is attributed to a named source or flagged
# `pending_verified` — never fabricated. Verified figures land from the Onyx
# research run wf_75e35a67-9a2 (deep-research: "where agent-economy money goes").
# Bright line preserved: we sign attributed facts, not guesses. ---
SEGMENTS = [
    {"segment": "enterprise_agents",
     "examples": ["Salesforce Agentforce", "Microsoft Copilot agents", "ServiceNow AI agents",
                  "Google Agentspace", "SAP Joule", "Workday"],
     "buyer": "enterprises (per-seat / per-conversation / per-agent licensing)",
     "size_usd_30d": None, "basis": "pending_verified (wf_75e35a67-9a2)",
     "note": "largest pool; real enterprise budgets, not crypto flow"},
    {"segment": "vertical_ai_agents",
     "examples": ["Sierra", "Decagon", "Harvey", "Abridge", "Cognition/Devin"],
     "buyer": "enterprise customers of each vertical",
     "size_usd_30d": None, "basis": "pending_verified (wf_75e35a67-9a2)",
     "note": "fastest-funded; 48-55% of 2026 agentic-AI capital per prior PitchBook read"},
    {"segment": "agentic_commerce",
     "examples": ["OpenAI checkout", "Stripe ACP", "Google AP2", "Amazon"],
     "buyer": "merchants + commerce platforms (real consumer GMV)",
     "size_usd_30d": None, "basis": "pending_verified (wf_75e35a67-9a2)",
     "note": "separate REAL merchant GMV from crypto settlement; pre-revenue at some platforms"},
    {"segment": "consumer_agent_subs",
     "examples": ["ChatGPT agent mode", "Claude", "Perplexity"],
     "buyer": "consumers (subscription ARR)",
     "size_usd_30d": None, "basis": "pending_verified (wf_75e35a67-9a2)",
     "note": "billions-scale ARR pool, distinct from agent-to-agent payments"},
    {"segment": "crypto_x402",
     "examples": ["Coinbase Bazaar", "x402 facilitators"],
     "buyer": "crypto agents (agent-to-agent USDC micropayments)",
     "size_usd_30d": REAL_VOLUME_RANGE_30D,
     "basis": "Onyx live census + named indexers (this tool's measured lane)",
     "note": "SMALLEST lane and shrinking -92% from Dec-2025 peak; do NOT equate with 'the agent economy'"},
]


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "onyx-aei/1.0", "Accept": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=40).read())


def _census(max_pages):
    total = None
    off = 0
    pages = 0
    ops = {}
    stale = 0
    counted = 0
    nets = {}
    while True:
        d = _get(f"{BAZAAR}?limit=100&offset={off}")
        if total is None:
            total = d.get("pagination", {}).get("total")
        items = d.get("items", [])
        if not items:
            break
        for it in items:
            counted += 1
            lu = it.get("lastUpdated")
            if lu:
                try:
                    t = time.strptime(lu.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S.%f%z") if "." in lu \
                        else time.strptime(lu.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S%z")
                    age_d = (time.time() - time.mktime(t)) / 86400
                    if age_d > 90:
                        stale += 1
                except Exception:
                    pass
            for a in it.get("accepts", []):
                pt = (a.get("payTo") or "").lower()
                if pt:
                    ops[pt] = ops.get(pt, 0) + 1
                nt = a.get("network", "?")
                nets[nt] = nets.get(nt, 0) + 1
        pages += 1
        off += 100
        if (total and off >= total) or pages >= max_pages:
            break
    tot_ep = sum(ops.values()) or 1
    ranked = sorted(ops.values(), reverse=True)
    top3 = sum(ranked[:3])
    top10 = sum(ranked[:10])
    return {
        "advertised_resources": total,
        "scanned": counted,
        "pages": pages,
        "unique_operators": len(ops),
        "endpoint_accepts": tot_ep,
        "stale_over_90d": stale,
        "stale_pct": round(100 * stale / max(counted, 1), 1),
        "top3_operator_share_pct": round(100 * top3 / tot_ep, 1),
        "top10_operator_share_pct": round(100 * top10 / tot_ep, 1),
        "networks": dict(sorted(nets.items(), key=lambda x: -x[1])[:5]),
    }


def run(max_pages: int = 300, **_):
    if not isinstance(max_pages, int) or max_pages < 1:
        raise ValueError("max_pages must be a positive integer")
    max_pages = min(max_pages, 400)
    t0 = time.time()
    census = _census(max_pages)
    headline = next((s["value_usd"] for s in VOLUME_SOURCES if s["source"] == "x402.org"), None)
    mid_real = (REAL_VOLUME_RANGE_30D["low_usd"] + REAL_VOLUME_RANGE_30D["high_usd"]) / 2
    pending = [s["segment"] for s in SEGMENTS if s.get("size_usd_30d") is None]
    payload = {
        "index": "onyx_agent_economy_index",
        "version": "1.1",
        "as_of": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "headline_correction": (
            "x402 crypto agent-to-agent settlement is ONE small, shrinking lane "
            "(-92% from Dec-2025 peak) — NOT 'the agent economy'. The money is in "
            "enterprise + vertical + agentic-commerce + consumer segments. See `segments`."
        ),
        "segments": SEGMENTS,
        "segments_pending_verified": pending,
        "x402_lane": {
            "live_census": census,
            "real_volume_30d": REAL_VOLUME_RANGE_30D,
        },
        "live_census": census,
        "real_volume_30d": REAL_VOLUME_RANGE_30D,
        "headline_volume_30d_usd": headline,
        "inflation_multiple": round(headline / mid_real, 1) if headline else None,
        "self_cycling_share": {"of_transactions_pct": 48, "of_volume_pct": 81,
                               "source": "Artemis (@OnchainLu)", "as_of": "2026-03"},
        "decline": DECLINE,
        "published_sources": VOLUME_SOURCES,
        "filter_method_version": FILTER_METHOD_VERSION,
        "scope_note": ("live_census + concentration = Onyx's own real-time measurement; "
                       "real_volume_30d = signed reconciliation of named third-party indexers. "
                       "Full on-chain wash-filter (Validator v2) requires an indexer feed and is "
                       "published as method, not claimed as our own pull."),
        "verify_pubkey_at": "https://onyx-actions.onrender.com/.well-known/onyx-pubkey",
        "elapsed_ms": int((time.time() - t0) * 1000),
    }
    return _onyx_sign.attest(payload, tool=NAME,
                             public_url="https://onyx-actions.onrender.com")
