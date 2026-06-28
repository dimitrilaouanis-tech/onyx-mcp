"""0n1x Intelligence — productizes our accumulated agentic-web research + the
signed verification capability into live endpoints. OUR ecosystem, OUR product.

Why this exists: the hours of cited, cross-verified competitive/market research we
produce are finished inventory, and our infra already signs every output (Ed25519).
That combination — primary agentic-web data + cryptographic verifiability — is a
product nobody else ships (generic AI reports can't be signed/verified). This module
exposes it as a catalog + a free signed sample + the paid-tier surface, all on the
existing x402 rail. No app.py edits (register(app), mirrors _onyxrank).

Surfaces:
  GET /intel           -> product catalog + pricing + the differentiator (signed)
  GET /intel/sample    -> a FREE signed teaser teardown (proves quality, funnels)
  GET /intel/verify-merchant?domain=&brand=  -> the productized counterparty check
                          (free-tier introspection; full signed verdict is x402-gated)

Pricing is published (neutrality = the moat). Stdlib + _onyx_sign only.
Underscore-prefixed so tools_pkg.discover() treats it as a helper, not an auto-tool.
"""
from __future__ import annotations

import time

from . import _onyx_sign

# ── Published product line (anchored to real comps: Persona $0.43/check,
#    DoubleVerify per-impression, Gartner/Forrester seat, expert-call $300-2000). ──
CATALOG = {
    "0n1x BRIEF": {
        "what": "Signed 'Agentic Commerce Reality Report' — real-vs-hype volume "
                "census + payment-rail map (x402/AP2/ACP/Visa TAP/MC) + standards "
                "landscape (ERC-8004/8126/A2A/MCP). Quarterly.",
        "form": "one-off signed report",
        "price_usd": "1500-3500",
        "buyer": "founders pre-raise, VC associates",
    },
    "0n1x EDGE": {
        "what": "Custom competitor teardown (pricing, revenue model, positioning) "
                "+ 60-min expert call. e.g. 'how Fime FACT / SafetyKit make money "
                "and how to beat them'.",
        "form": "bespoke signed teardown + call",
        "price_usd": "5000-10000",
        "buyer": "corp-dev, PSP strategy, funded founders",
    },
    "0n1x PULSE": {
        "what": "(a) biweekly signed intel brief (funding, standards moves, new "
                "entrants, volume deltas)  (b) API feed of live agent census + "
                "signed reputation/counterparty-reality data.",
        "form": "subscription + data API",
        "price_usd": "brief 500-1500/mo · feed 1000-5000/mo",
        "buyer": "VCs (continuous diligence), trust/identity vendors",
    },
    "0n1x VERIFY": {
        "what": "Per-check signed verification of the MERCHANT/counterparty an agent "
                "is about to pay (is this store/price real, or a clone/scam?). The "
                "seat nobody else sells — Persona model, pointed at the seller side.",
        "form": "per-verification API",
        "price_usd": "0.10-1.50/check (enterprise-billed, NOT agent-wallet)",
        "buyer": "PSPs, marketplaces, agent platforms, brand-protection teams",
    },
}

DIFFERENTIATOR = (
    "Every number we publish is Ed25519-signed and independently verifiable, and the "
    "agent data underneath is PRIMARY (collected by us), not scraped or hallucinated. "
    "In the AI-slop era, verifiable research is a trust premium nobody else offers."
)

# A free signed teaser — the funnel. Real findings, no full source list (that's licensed).
SAMPLE = {
    "title": "0n1x EDGE (sample) — How the Agentic-Commerce Trust Layer Makes Money",
    "as_of": "2026-06-28",
    "headline": "Rails shipped everywhere; revenue almost nowhere. Real x402 flow "
                "~$1.1M/30d (down 77% from peak, ~half wash). The money that IS real "
                "comes from ONE mechanic: a metered verification endpoint billed to "
                "businesses.",
    "proven_money_models": [
        "DoubleVerify $748M (82% margin) — per-impression, buy-side",
        "Persona ~$141M ARR — $0.43-1.50 per verification",
        "Trulioo ~$150M — per KYC/KYB check",
        "Riskified $345M — 22 bps of approved GMV + guarantee",
    ],
    "makes_no_money": [
        "AgentRadar (agent-paid per-call, our exact x402 model) = $62 LIFETIME",
        "GoPlus 717M calls/mo -> only $4.7M cumulative",
        "Every dedicated agent-payment startup = pre-revenue",
    ],
    "the_open_seat": "Everyone verifies the AGENT/buyer. Nobody neutrally + publicly "
                     "+ verifiably verifies the MERCHANT the agent pays. Visa named "
                     "the gap ('protocols verify payment integrity, not merchant "
                     "legitimacy') and shipped nothing for it.",
    "why_now": ["Jul 24 2026 MC Scam Merchant Monitoring", "Aug 2 2026 EU AI Act Art.50",
                "live ChatGPT fake-storefront scandals"],
    "the_play": "Be the per-verification business (Persona/DoubleVerify mechanic) "
                "pointed at the merchant side — billed to enterprises, not agents.",
    "full_report": "Licensed edition includes full competitor table, pricing, "
                   "revenue sources, and the 90-day execution plan.",
}


def catalog(base: str = "https://onyx-actions.onrender.com") -> dict:
    base = (base or "").rstrip("/")
    out = {
        "product": "0n1x Intelligence",
        "tagline": "Signed, verifiable agentic-web intelligence + counterparty "
                   "verification. The research is the product.",
        "differentiator": DIFFERENTIATOR,
        "catalog": CATALOG,
        "free_sample": f"{base}/intel/sample",
        "verify_merchant": f"{base}/intel/verify-merchant?domain=example.com&brand=Example",
        "settlement": "USDC on Base (x402) or invoice. Enterprise-billed.",
        "verify_any_output": f"{base}/verify",
        "issued_at": int(time.time()),
    }
    return _onyx_sign.attest(out, tool="onyx_intel_catalog")


def sample(base: str = "https://onyx-actions.onrender.com") -> dict:
    base = (base or "").rstrip("/")
    out = dict(SAMPLE)
    out["upgrade"] = {k: v["price_usd"] for k, v in CATALOG.items()}
    out["how_to_buy"] = f"{base}/intel  ·  signed sample — verify at {base}/verify"
    return _onyx_sign.attest(out, tool="onyx_intel_sample")


def verify_merchant(domain: str = "", brand: str = "",
                    base: str = "https://onyx-actions.onrender.com") -> dict:
    """Free-tier introspection of the counterparty check. The full signed verdict
    (domain age, clone-similarity, brand-authorization, HOLD/PASS) is the x402-gated
    product at /v1/onyx_payment_gate — this advertises it and shows the shape."""
    base = (base or "").rstrip("/")
    out = {
        "service": "0n1x VERIFY — counterparty/merchant reality check",
        "asked": {"domain": domain or "(none)", "brand": brand or "(none)"},
        "what_the_paid_check_returns": {
            "verdict": "PASS | HOLD | BLOCK",
            "signals": ["domain_age_days", "clone_similarity_to_legit_brand",
                        "brand_authorized_mapping", "price_vs_market"],
            "signed": "Ed25519 attestation (verify offline)",
        },
        "example_catch": "rayban.cc -> HOLD (clone of ray-ban.com, sim 1.00, "
                         "~279-day domain vs 29yr legit; do-not-pay)",
        "why": "Everyone verifies the agent; this verifies the MERCHANT the agent "
               "pays. Sign facts not judgments — the reader decides.",
        "get_full_verdict": f"{base}/v1/onyx_payment_gate  (x402, enterprise-billed)",
        "pricing": CATALOG["0n1x VERIFY"]["price_usd"],
        "issued_at": int(time.time()),
    }
    return _onyx_sign.attest(out, tool="onyx_verify_merchant_intro")


def register(app) -> None:
    """Attach the intel surfaces to the FastAPI app from build_asgi().

    Usage in server_http.py (one line, mirrors _onyxrank):
        from tools_pkg import _intel; _intel.register(app)
    """
    from fastapi.responses import JSONResponse

    @app.get("/intel", include_in_schema=False)
    def _intel():
        return JSONResponse(catalog())

    @app.get("/intel/sample", include_in_schema=False)
    def _intel_sample():
        return JSONResponse(sample())

    @app.get("/intel/verify-merchant", include_in_schema=False)
    def _intel_verify(domain: str = "", brand: str = ""):
        return JSONResponse(verify_merchant(domain, brand))
