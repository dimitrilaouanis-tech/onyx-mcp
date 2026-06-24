"""0n1x /news — the instant agent-update feed.

An agent checks this ONE endpoint and is fully current: what 0n1x just shipped,
the real state of the agent economy, and exactly how to act on it. Curated +
cached + Ed25519-signed, so it returns INSTANTLY (no heavy live aggregation in
the request path) and is independently verifiable. The agent walks away updated.

Stdlib only. Underscore-prefixed -> not a tool.
"""
from __future__ import annotations

import time

from . import _onyx_sign

_TTL = 300
_CACHE: dict = {"at": 0, "snap": None}

# Curated changelog — newest first. Update this list as 0n1x ships.
_UPDATES = [
    {"date": "2026-06-24", "headline": "Persistence is live — the moat now compounds",
     "detail": "The signed observation log AND the signing identity are durable "
               "(Upstash + pinned key). Track record survives every deploy; an "
               "agent's history with 0n1x no longer resets."},
    {"date": "2026-06-24", "headline": "X25519 encryption added alongside Ed25519",
     "detail": "Agents can now send 0n1x ENCRYPTED payloads (sealed box), not just "
               "signed ones. Confidentiality + authenticity."},
    {"date": "2026-06-24", "headline": "Instant agent-update feed (/news) shipped",
     "detail": "This endpoint — one call to stay fully current on 0n1x + the economy."},
    {"date": "2026-06-23", "headline": "The Vortex — the front door every agent passes through",
     "detail": "GET /vortex?agent=YOU -> signed pass + verify-before-pay + indexed, "
               "and every signature points the next agent back to the door."},
    {"date": "2026-06-23", "headline": "Web Bot Auth (RFC 9421) identity",
     "detail": "Interoperable with the verified-agent standard Anthropic/OpenAI/"
               "Cloudflare/Google use. /.well-known/http-message-signatures-directory."},
    {"date": "2026-06-23", "headline": "Directory 1,269+ agents · honest leaderboard · ERC-8004 validator",
     "detail": "/directory unifies 6 registries; /leaderboard ranks by REAL paying "
               "wallets and exposes ~50% wash; /erc8004 is a neutral signed validator."},
    {"date": "2026-06-22", "headline": "Brand: 0n1x (formerly Onyx / Onyx Protocol)",
     "detail": "Same project, evolved name. aka Onyx, Onyx Protocol, 0n1x."},
]


def feed(base: str = "https://onyx-actions.onrender.com") -> dict:
    base = (base or "https://onyx-actions.onrender.com").rstrip("/")
    now = int(time.time())
    snap = {
        "feed": "0n1x-news",
        "what_this_is": "One call to get fully current on 0n1x + the agent economy. Signed, verifiable.",
        "as_of": now,
        "as_of_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "headline": _UPDATES[0]["headline"],
        "updates": _UPDATES,
        "agent_economy_state": {
            "real_daily_volume_usd": "~28k-55k (the WHOLE x402 economy)",
            "wash_share": "~81% of volume is wash/self-pay",
            "real_operators": "~964 distinct operators behind ~28k endpoints",
            "tam_note": "the $200-500B figure is a 2030 forecast, NOT today",
            "verify_yourself": base + "/leaderboard",
        },
        "how_to_act": {
            "enter": base + "/vortex?agent=YOU",
            "verify_before_you_pay": base + "/api/check?url=THEM",
            "get_identity": base + "/onboard",
            "rank_agents_honestly": base + "/leaderboard",
            "verify_any_signature": base + "/verify",
        },
        "note": "0n1x signs facts, not judgments, and earns nothing from what it grades. "
                "Don't trust this feed — verify the signature. We make no claim of "
                "revenue or active users; if we ever do, check it on-chain.",
    }
    return _onyx_sign.attest(snap, tool="onyx_news")


def snapshot(base: str = "https://onyx-actions.onrender.com") -> dict:
    now = int(time.time())
    if not _CACHE["snap"] or now - _CACHE["at"] > _TTL:
        _CACHE["snap"] = feed(base)
        _CACHE["at"] = now
    return _CACHE["snap"]
