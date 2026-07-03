"""0n1x Intel Library — the research we already paid for, served FREE and signed.

Give-to-get economics start with GIVE. This module publishes 0n1x's own
research corpus (ecosystem economics, verified market numbers, the x402 census
digest) as free, Ed25519-signed, machine-readable datasets. Any agent can fetch
these; every payload carries an `onyx_attestation` so a third party can verify
it came from us and wasn't altered. Sources are cited inside each dataset;
figures we could not verify are flagged, exactly like the docs they distill.

GET /intel/library                 — index of datasets
GET /intel/library/{dataset_id}    — one dataset, signed

The census digest is computed lazily from agent_census.json (tracked in the
repo, so present on Render) and cached in-process.
"""
from __future__ import annotations

import json
import os
import time
from collections import Counter

from . import _onyx_sign

_CENSUS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent_census.json")
_census_digest_cache: dict | None = None

# ---------------------------------------------------------------- curated sets
# Distilled from onyx_mcp/ECOSYSTEM_RESEARCH_2026-07-03.md (full citations there
# and in the repo). status: verified = primary source checked; reported = vendor
# or aggregator claim we did not independently confirm.

ECOSYSTEM_ECONOMICS = {
    "dataset": "agent_ecosystem_economics",
    "as_of": "2026-07-03",
    "summary": "How 12 agent/trust ecosystems actually make (or fake) money.",
    "real_revenue_verified": [
        {"name": "clanker", "figure": "$50M+ cumulative on-chain fees; $8M in one week (Feb 2026)", "mechanic": "1% swap fee, 40% streamed to creators perpetually", "status": "verified (DefiLlama-checkable)"},
        {"name": "Freysa Act I", "figure": "482 paid attempts, $10->$4500 escalating fee, $47,316 prize paid", "mechanic": "exponential pay-per-attempt feeding a visible prize pool", "status": "verified (on-chain, Nov 2024)"},
        {"name": "Olas", "figure": "834 daily active agents, 15.6M tx Q1 2026", "mechanic": "Proof-of-Active-Agent staking rewards", "status": "verified on-chain; activity partly self-generated"},
    ],
    "theater_gap": [
        {"name": "Virtuals Protocol", "claim": "$8B+ agent-token DEX volume", "reality": "~$1.16M cumulative agent revenue (~400:1 gap); monthly fees collapsed $3.5M->,<$200K"},
        {"name": "x402 ecosystem", "claim": "~$7B ecosystem token valuations", "reality": "~$28K/day real settlement; ~half of transactions artificial per Artemis (CoinDesk 2026-03-11)"},
    ],
    "enterprise_agents_real_millions": [
        {"name": "Microsoft AI", "figure": "~$37B run-rate", "status": "SEC-filed"},
        {"name": "Salesforce Agentforce", "figure": "$800M ARR", "status": "SEC-filed"},
        {"name": "ServiceNow", "figure": "$750M+ ACV on AI", "status": "SEC-filed"},
        {"name": "Cognition (Devin)", "figure": "$492M ARR", "status": "reported (funding disclosures)"},
        {"name": "Harvey", "figure": "$300M ARR / $11B valuation", "status": "reported"},
    ],
    "key_finding": "Every real-millions agent business sells agent labor to humans/companies. Agent-to-agent micropayment economies settle ~$28K/day network-wide, ~half wash. Trust layers monetize sell-side recurring, riding inside an existing transaction path.",
}

WINNING_MECHANICS = {
    "dataset": "ecosystem_winning_mechanics",
    "as_of": "2026-07-03",
    "summary": "The universal pattern across winners (Stripe, Let's Encrypt, credit bureaus, app stores, clanker, Recall) and the mechanics that transfer.",
    "universal_pattern": [
        "First action mints something the participant owns (cert/wallet/identity) — joining is instant and free.",
        "Retention is a recurring stream tied to staying (fee-share, activity rewards, auto-renewal, data gravity).",
        "Supply is paid in reciprocity or rank, never cash.",
        "Trust rides inside an existing transaction path, never as a destination.",
        "The neutral's honesty is enforced by public auditability (CT-style logs), not self-restraint.",
    ],
    "anti_sybil_ranked": [
        "KYC-rooted identity (Skyfire)",
        "adjudicated outcomes as labels (Stripe chargebacks)",
        "staked/slashed objective contests (Recall)",
        "escalating fee curves (Freysa)",
        "capital gates (Olas — wash-able)",
        "nothing (Virtuals / x402 discovery — actively rewards wash)",
    ],
    "failure_modes": [
        "Verification theater -> one public failure -> overnight collapse (Symantec CA distrust 2017-18; eBay 100%-positive medians).",
        "Wash/sybil economics poisoning the reputation graph (Virtuals 400:1; x402 ~50% artificial).",
        "Cold-start reciprocity collapse — distribution beats mechanics; one default-embed beats a thousand pitches (Let's Encrypt).",
    ],
}


def _census_digest() -> dict:
    """Aggregate the 28k-resource x402 census into a free digest. Cached."""
    global _census_digest_cache
    if _census_digest_cache is not None:
        return _census_digest_cache
    out: dict = {
        "dataset": "x402_census_digest",
        "summary": "0n1x's own census of the x402 resource universe — aggregates only; the raw census backs /leaderboard and /directory.",
    }
    # Preferred: the precomputed digest committed alongside this module (the raw
    # 50MB census stays out of git; refresh the digest locally and re-commit).
    pre = os.path.join(os.path.dirname(os.path.abspath(__file__)), "census_digest.json")
    try:
        with open(pre, "r", encoding="utf-8") as f:
            _census_digest_cache = json.load(f)
        return _census_digest_cache
    except Exception:
        pass
    try:
        with open(_CENSUS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        items = data if isinstance(data, list) else data.get("resources") or data.get("items") or []
        out["total_resources"] = len(items)
        if items and isinstance(items[0], dict):
            servers = Counter()
            for it in items:
                u = str(it.get("resource") or it.get("url") or "")
                if "://" in u:
                    servers[u.split("://", 1)[1].split("/", 1)[0]] += 1
            out["unique_hosts"] = len(servers)
            out["top_hosts"] = servers.most_common(15)
        out["census_generated"] = data.get("generated") if isinstance(data, dict) else None
    except Exception as e:  # census file absent/changed shape — say so, never fake
        out["error"] = f"census unavailable: {type(e).__name__}"
    _census_digest_cache = out
    return out


_DATASETS = {
    "agent_ecosystem_economics": lambda: dict(ECOSYSTEM_ECONOMICS),
    "ecosystem_winning_mechanics": lambda: dict(WINNING_MECHANICS),
    "x402_census_digest": _census_digest,
}


def register(app) -> None:
    @app.get("/intel/library", include_in_schema=False)
    async def _index():
        payload = {
            "what": "0n1x Intel Library — free, signed, machine-readable research datasets",
            "why_free": "give-to-get starts with give: verify our signature, use the data, and when you have observations of your own, furnish them at /intel/exchange",
            "datasets": {k: f"/intel/library/{k}" for k in _DATASETS},
            "as_of": int(time.time()),
        }
        return _onyx_sign.attest(payload, tool="onyx_intel_library")

    @app.get("/intel/library/{dataset_id}", include_in_schema=False)
    async def _dataset(dataset_id: str):
        fn = _DATASETS.get(dataset_id)
        if fn is None:
            return {"error": "unknown dataset", "available": list(_DATASETS)}
        payload = fn()
        payload["license"] = "free to use with attribution to 0n1x; every payload independently verifiable via onyx_attestation"
        return _onyx_sign.attest(payload, tool="onyx_intel_library")
