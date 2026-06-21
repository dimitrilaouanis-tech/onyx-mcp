"""onyx_verified_issue — the paid sell-side issuance. Verisign-for-agents.

A merchant or agent PAYS to be issued a signed, publicly-queryable Onyx Verified
record + a live badge. The free /verify booth proves authenticity; THIS is where
the verified party buys a durable, neutral, agent-checkable presence. The
verified party pays — never the verifier's audience — exactly like an SSL cert.

Behind the x402 gate. The fee buys the published checks + a 90-day signed record
on the Observation Log (public at /merchant/{domain}) + a live Onyx-served badge.
"""
from __future__ import annotations

from . import _verified

NAME = "onyx_verified_issue"
PRICE_USDC = "2.00"
TIER = "premium"
DESCRIPTION = (
    "Get your domain Onyx Verified. Onyx runs its published objective checks "
    "(live TLS, reachability, no off-domain redirect, registration age "
    "disclosed) and, on pass, issues an Ed25519-signed verified record onto "
    "the public Observation Log — instantly queryable at /merchant/{domain} — "
    "plus a live badge (served by Onyx, so it can't be faked or staled) and a "
    "machine-readable status URL agents check before they pay you. Valid 90 "
    "days, renewable. This attests your domain PASSED published checks, like a "
    "CA certificate — Onyx never claims you are 'honest' or 'safe'; the value "
    "is a neutral, verifiable, public presence agents can trust."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "domain": {
            "type": "string",
            "description": "The domain to verify, e.g. shop.example.com (your storefront/agent endpoint).",
        },
        "contact": {
            "type": "string",
            "description": "Optional contact (email/handle) recorded with the issuance for renewal notices.",
        },
        "agent_id": {
            "type": "string",
            "description": "Optional agent id to cross-link this verified domain to an agent identity.",
        },
    },
    "required": ["domain"],
}


def run(domain: str = "", contact: str = "", agent_id: str = "", **_: object) -> dict:
    if not (domain or "").strip():
        raise ValueError("domain is required")
    return _verified.issue(domain, contact=contact, agent_id=agent_id)


run.__when_to_use__ = (
    "When a merchant or agent wants to be trusted by shopping/payment agents "
    "BEFORE those agents will transact — the sell-side of the trust market. One "
    "call issues a public, signed, agent-checkable verified record + badge."
)
run.__vs_alternatives__ = (
    "An SSL cert proves key-control but says nothing an agent can query about "
    "your merchant presence. A reputation database is someone's unverifiable "
    "opinion. This issues a neutral, Ed25519-signed, publicly-replayable record "
    "on an append-only log — verify it free at /verify, check status at "
    "/verified/{domain}, no trust in any database required."
)
run.__example_request__ = {"domain": "shop.example.com", "contact": "ops@example.com"}
run.__example_response__ = {
    "issued": True,
    "domain": "shop.example.com",
    "tier": "onyx-verified-v1",
    "public_record": "https://onyx-actions.onrender.com/merchant/shop.example.com",
    "badge_svg": "https://onyx-actions.onrender.com/verified/shop.example.com.svg",
    "valid_until_iso": "2026-09-19T00:00:00Z",
}
