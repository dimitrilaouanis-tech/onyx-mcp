"""onyx-actions — reference implementation built on onyx_paid_mcp.

Loads every tool in tools_pkg/ and exposes them as paid MCP via the
framework. Live at https://onyx-actions.onrender.com.

Run:
    uvicorn server_http:app --host 0.0.0.0 --port 8080
"""
from __future__ import annotations

import os
from pathlib import Path

# ---- env (.env loader, no extra dependency) -----------------------------

env_file = os.environ.get("ONYX_ENV_FILE", ".env")
env_path = Path(__file__).parent / env_file
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

# ---- App ---------------------------------------------------------------

from onyx_paid_mcp import App, Tool

app_obj = App(
    name="onyx-actions",
    receive_address=os.environ.get("ONYX_RECEIVE_ADDRESS")
    or (_ for _ in ()).throw(RuntimeError("ONYX_RECEIVE_ADDRESS missing")),
    network=os.environ.get("ONYX_NETWORK", "base-sepolia").lower(),
    facilitator_url=os.environ.get("ONYX_FACILITATOR_URL"),
    public_url=os.environ.get("ONYX_PUBLIC_URL", "https://onyx-actions.onrender.com"),
    mainnet_receive_address=os.environ.get(
        "ONYX_MAINNET_RECEIVE_ADDRESS",
        "0xA60939FFf9c04a61c0c0649943675e16A12D7074",
    ),
    description="Paid agent tools over x402 USDC. Reference impl of onyx-paid-mcp.",
    homepage="https://onyx-actions.onrender.com",
)

# ---- Auto-discover every tools_pkg/*.py ---------------------------------

import tools_pkg

for mod in tools_pkg.discover():
    app_obj.add(Tool(
        name=mod.NAME,
        price_usdc=mod.PRICE_USDC,
        description=mod.DESCRIPTION,
        input_schema=mod.INPUT_SCHEMA,
        handler=mod.run,
        tier=mod.TIER,
    ))

# ASGI app uvicorn binds to
app = app_obj.build_asgi()

# Public aggregate fact-index (surface 3b) — new module, attaches its own route.
from tools_pkg import _fact_index
_fact_index.register(app)

# OnyxRank — in-house citizen reputation rank (our ecosystem, our rules). GET /rank
from tools_pkg import _onyxrank
_onyxrank.register(app)

# Fool-the-Oracle bounty — self-funding spectacle (read surfaces). GET /fool/bounty, /fool/quote
from tools_pkg import _fool_bounty
_fool_bounty.register(app)

# Proof Board — verifiers ranked by published track record w/ honest 95% CIs. GET /proof-board
from tools_pkg import _proofboard
_proofboard.register(app)

# 0n1x Intelligence — productized research + counterparty verification. GET /intel, /intel/sample, /intel/verify-merchant
from tools_pkg import _intel
_intel.register(app)

# 0n1x PULSE — live signed agentic-web data feed (census + reputation + outcomes). GET /intel/feed
from tools_pkg import _pulsefeed
_pulsefeed.register(app)

# Proof-of-key gate (EIP-4361) — public block CHECKS; only the key ACTS. Guards /attest /onboard /perm/check.
from tools_pkg import _siwe
_siwe.register(app)

# 0n1x Intel Exchange — the signed external-corroboration graph (give-to-get). GET/POST /intel/exchange/*
from tools_pkg import _intel_exchange
_intel_exchange.register(app)

# 0n1x Exchange Feed — supply loop: work queue + SSE + signed webhooks. /intel/exchange/{work,stream,subscribe}
from tools_pkg import _exchange_feed
_exchange_feed.register(app)

# /merchant-signal — the dead-simple signed pre-flight check (the flagship: usage before standards).
from tools_pkg import _merchant_signal
_merchant_signal.register(app)

# 0n1x Live Stats — honest public numbers (no fabricated hype). GET /stats, /stats.json
from tools_pkg import _stats
_stats.register(app)

# 0n1x NETWORK MATRIX — Bloomberg-terminal live ops dashboard composed over /stats,
# /rank, /ecosystem-intel, and the outcome ledger. GET /matrix, /matrix.json
from tools_pkg import _network_matrix
_network_matrix.register(app)

# 0n1x SIGNUP — the external front door: one page for humans + agents, TRY IT hits the
# existing /v1/join client-side (no server-side proxy, nothing minted on page load).
# GET /signup, /signup.json
from tools_pkg import _signup
_signup.register(app)

# onyx_preflight — free rate-limited teaser of the paid x402-endpoint preflight check. GET /preflight?url=
from tools_pkg import preflight_check
preflight_check.register(app)

# onyx_ecosystem_intel — signed snapshot of the agentic ecosystem (our numbers + live CDP census + competitor map). GET /ecosystem-intel
from tools_pkg import ecosystem_intel
ecosystem_intel.register(app)

# onyx_merchant_verify v2 — flagship merchant-reality verification. POST /verify/merchant · GET /verified/merchant/{domain}
from tools_pkg import merchant_verify
merchant_verify.register(app)

# 0n1x non-CLI loop — DURABLE onboarding (Neon-persisted) + staged credits, all in one GET.
# GET /v1/join · /v1/me · /v1/census · /v1/spend  — survives redeploys, fetch-only agents can act.
from tools_pkg import _noncli
_noncli.register(app)

# 0n1x Bounty Feed — fetch-to-earn: fresh signed tasks, correct verdicts earn tokens (+USDC on
# hard ones) and rank agents on REAL verified work. The retention loop for non-CLI agents.
# GET /v1/bounties · /v1/claim · /v1/submit · /v1/bounty-board
from tools_pkg import _bounty_feed
_bounty_feed.register(app)

# 0n1x Portal — the LLM chat (Claude via function-calling) that converses freely but states
# network facts ONLY from signed 0n1x tools. 0n1x is the gate; the model is the door.
# POST /v1/chat  (activates when ANTHROPIC_API_KEY is set; falls back to the free NL router otherwise)
from tools_pkg import _chat
_chat.register(app)

# /version — the exact commit/branch/repo the live process was built from (Render env).
from tools_pkg import _version
_version.register(app)

# 0n1x Intel Library — the research corpus we already paid for, served FREE and signed.
# GET /intel/library · /intel/library/{dataset}. Give-to-get starts with give.
from tools_pkg import _intel_library
_intel_library.register(app)
