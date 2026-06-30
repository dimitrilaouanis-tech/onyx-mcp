"""Rhinogent — verify the counterparty BEFORE your agent pays.

The check the rest of the agent stack skips: every wallet secures the agent's own
keys, none verify WHO the agent is paying. This composes the 0n1x merchant fact
oracle into the Rhinogent "know-your-counterparty" surface.

Bright line (inherited): SIGN FACTS, NOT JUDGMENTS. We return signed raw
observations (domain age, TLS, reachability, brand-impersonation similarity,
observed price) — never an assertion of "legit" or "scam". The decision is the
agent's; the signature proves the observation is ours and untampered.
"""
from __future__ import annotations

from . import _onyx_sign, merchant_fact_check as _mfc

NAME = "rhinogent_verify_counterparty"
PRICE_USDC = "0.25"
TIER = "premium"
DESCRIPTION = (
    "Know-your-counterparty for agents. Before your agent pays a merchant, get "
    "Ed25519-signed raw facts about who it's paying: domain registration age, "
    "live TLS cert, reachability + off-domain redirects, brand-impersonation "
    "similarity, and observed price vs expected. Facts only (never 'legit/scam') "
    "— the one check every other agent wallet skips."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "domain": {
            "type": "string",
            "description": "Counterparty/storefront domain or URL the agent is about to pay.",
        },
        "brand": {
            "type": "string",
            "description": "Optional brand the storefront claims to be (enables the impersonation-similarity observation).",
        },
        "expected_price": {
            "type": ["number", "string"],
            "description": "Optional price the agent expects to pay (enables the price-deviation observation).",
        },
    },
    "required": ["domain"],
}


def run(domain: str | None = None, brand: str = "", expected_price=None, **_: object) -> dict:
    if not isinstance(domain, str) or not domain.strip():
        raise ValueError("domain is required (the counterparty the agent is about to pay)")
    facts = _mfc.run(domain=domain, brand=brand or "", expected_price=expected_price)
    out = {
        "product": "rhinogent",
        "check": "counterparty",
        "domain": domain.strip(),
        "what_this_is": (
            "Signed raw facts about the counterparty your agent is about to pay. "
            "0n1x signs the observation, not a verdict — you decide."
        ),
        "facts": facts,
    }
    return _onyx_sign.attest(out, tool=NAME)
