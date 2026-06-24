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
     "examples": ["Salesforce Agentforce", "Microsoft Copilot agents", "ServiceNow Now Assist",
                  "Google Agentspace", "SAP Joule", "Workday"],
     "buyer": "enterprises (per-seat / per-conversation / per-agent licensing)",
     "data_basis": "verified (wf_75e35a67-9a2)",
     "anchors": [
         {"company": "Salesforce Agentforce", "metric": "ARR", "value_usd": 800_000_000,
          "growth": "+169% YoY", "as_of": "2026-02", "source": "Salesforce Q4 FY2026 SEC 8-K"},
         {"company": "Microsoft AI business", "metric": "annual run-rate (Copilot+Azure AI bundled)",
          "value_usd": 37_000_000_000, "growth": "+123% YoY", "as_of": "2026-Q3 FY26",
          "source": "Microsoft IR / SEC, Apr 29 2026", "note": "not agent-only"},
         {"company": "ServiceNow Now Assist", "metric": "ACV", "value_usd": 750_000_000,
          "target_eoy_usd": 1_500_000_000, "as_of": "2026-Q1", "source": "ServiceNow FY Analyst Day / earnings"},
     ],
     "note": "LARGEST real-revenue pool; tens of $B recurring; enterprise budgets, not crypto flow"},
    {"segment": "vertical_ai_agents",
     "examples": ["Cognition/Devin", "Harvey", "Sierra", "Decagon", "Abridge"],
     "buyer": "enterprise customers (Mercedes-Benz, Goldman, Santander, 50% of Am Law 100)",
     "data_basis": "verified (wf_75e35a67-9a2)",
     "anchors": [
         {"company": "Cognition (Devin)", "metric": "annualized run-rate", "value_usd": 492_000_000,
          "raise": "$1B at $25B pre", "as_of": "2026-05", "source": "Cognition Series D / TechCrunch"},
         {"company": "Harvey (legal)", "metric": "ARR (Sacra est.)", "value_usd": 300_000_000,
          "valuation_usd": 11_000_000_000, "as_of": "2026-05", "source": "Sacra / CNBC"},
     ],
     "note": "substantial enterprise recurring SaaS; run-rates are forward-annualized, not audited GAAP"},
    {"segment": "agentic_commerce",
     "examples": ["OpenAI+Stripe ACP", "Google AP2", "Visa Intelligent Commerce", "Mastercard Agent Pay", "Amazon", "Shopify"],
     "buyer": "merchants + payment providers (real card-rail GMV, not crypto)",
     "data_basis": "verified (wf_75e35a67-9a2)",
     "anchors": [
         {"metric": "McKinsey 2030 orchestrated retail — US B2C", "value_usd_range": [900_000_000_000, 1_000_000_000_000],
          "as_of": "forecast 2030", "source": "McKinsey QuantumBlack Oct 2025", "note": "forecast, goods only, 'orchestrated' not net-new"},
         {"metric": "McKinsey 2030 orchestrated retail — global", "value_usd_range": [3_000_000_000_000, 5_000_000_000_000],
          "as_of": "forecast 2030", "source": "McKinsey QuantumBlack Oct 2025"},
         {"detail": "ACP Instant Checkout live in ChatGPT, 4% merchant fee; runs on standard card rails", "source": "Stripe/OpenAI"},
     ],
     "note": "real GMV on mainstream rails; 2030 figures are consultancy forecasts, not measured GMV"},
    {"segment": "agent_infrastructure",
     "examples": ["LangChain", "Stainless (->Anthropic $300M)", "LlamaIndex", "eval/observability"],
     "buyer": "enterprises building agents (35% of Fortune 500 use LangChain)",
     "data_basis": "verified (wf_75e35a67-9a2)",
     "anchors": [
         {"company": "LangChain", "metric": "Series B valuation", "value_usd": 1_250_000_000,
          "raise": "$125M", "as_of": "2025-10", "source": "LangChain blog / Fortune"},
     ],
     "note": "picks-and-shovels; bought by enterprises, not crypto agents"},
    {"segment": "consumer_agent_subs",
     "examples": ["ChatGPT agent mode", "Claude", "Perplexity", "Gemini"],
     "buyer": "consumers (subscription ARR)",
     "data_basis": "unsized_gap (no verified figure survived adversarial check)",
     "anchors": [
         {"company": "Perplexity", "metric": "ARR (reported, unverified here)", "value_usd": 450_000_000,
          "as_of": "2026", "source": "Yahoo Finance — NOT independently verified in this run"},
     ],
     "note": "billions-scale pool but segment produced no surviving verified claim; OPEN GAP, do not cite as Onyx-verified"},
    {"segment": "crypto_x402",
     "examples": ["Coinbase Bazaar", "x402 facilitators"],
     "buyer": "crypto agents (agent-to-agent USDC micropayments)",
     "data_basis": "Onyx live census + named indexers (this tool's measured lane)",
     "size_usd_30d": REAL_VOLUME_RANGE_30D,
     "note": ("SMALLEST lane and shrinking; Chainalysis: mass adoption 'remains distant', participants "
              "'crypto-native'; >100M cumulative Base txns inflated by PING meme pay-to-mint (150K txns ~= $140K); "
              "adjusted volume -77% Nov-2025->May-2026. Do NOT equate with 'the agent economy'.")},
]

# Where a signed real-world-FACT verification index/oracle has a paying buyer.
# VERIFIED nuance (wf_75e35a67-9a2): McKinsey names an unsolved "know your agent"
# (KYA) need with LIVE paying buyers (Trulioo/Worldpay, Skyfire/Experian, Visa,
# Mastercard) — but KYA is agent IDENTITY, a DISTINCT market from real-world
# fact (price/merchant/product) verification. The fact-oracle buyer is the SAME
# set (merchants / PSPs / risk-&-compliance vendors) but demand is inferred, not
# yet directly demonstrated. Honest: target the commerce/PSP/risk stack, not the
# crypto x402 lane; identity demand is proven, fact demand is the open bet.
FACT_VERIFICATION_BUYER = {
    "target_segment": "agentic_commerce + enterprise risk/compliance",
    "buyer_set": ["merchants", "payment service providers", "risk/compliance/identity vendors"],
    "proven_adjacent_demand": ["Trulioo/Worldpay KYA", "Skyfire/Experian KYA", "Visa", "Mastercard"],
    "caveat": "Proven demand is for agent IDENTITY (KYA); real-world FACT verification is adjacent and not yet directly demonstrated.",
    "not_the_buyer": "crypto x402 lane",
}


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
    open_gaps = [s["segment"] for s in SEGMENTS if "gap" in s.get("data_basis", "")]
    payload = {
        "index": "onyx_agent_economy_index",
        "version": "1.2",
        "as_of": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "headline_correction": (
            "x402 crypto agent-to-agent settlement is ONE small, shrinking lane "
            "(-92% from Dec-2025 peak) — NOT 'the agent economy'. The real money: "
            "ENTERPRISE agents (Salesforce Agentforce $800M ARR, MS AI $37B run-rate, "
            "ServiceNow Now Assist $750M ACV), VERTICAL agents (Cognition $492M, Harvey "
            "$300M ARR), and AGENTIC COMMERCE (McKinsey $3-5T global orchestrated retail "
            "by 2030, on card rails). Tens of $B real recurring revenue. See `segments`."
        ),
        "total_economy": "tens of $B real recurring revenue (mid-2026); crypto x402 = a rounding error within it",
        "biggest_segments": ["enterprise_agents", "vertical_ai_agents", "agentic_commerce"],
        "fact_verification_buyer": FACT_VERIFICATION_BUYER,
        "segments": SEGMENTS,
        "segments_open_gap": open_gaps,
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
