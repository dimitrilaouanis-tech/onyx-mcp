"""Rhinogent — author a signed spend mandate the agent adopts and enforces.

The agent transacts autonomously — within the boundaries you define. This issues
a signed 0n1x permission grant (PERM_v0: spend caps, merchant/domain allowlists,
velocity, expiry) under the Rhinogent surface. Honest by design: it attests the
scope DECLARED at issue time; enforcement lives with the agent (self-custody),
checkable later via onyx_perm_check.
"""
from __future__ import annotations

from . import _onyx_sign, onyx_perm_grant as _grant

NAME = "rhinogent_mandate"
PRICE_USDC = "0.00"
TIER = "free"
DESCRIPTION = (
    "Author a signed spend mandate for an agent: per-action and rolling-window "
    "USDC caps, merchant/domain allowlists, velocity limit and expiry — issued as "
    "a signed PERM_v0 grant the agent adopts. 'Transacts autonomously, within the "
    "boundaries you define.'"
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "agent": {"type": "string", "description": "Agent the mandate authorizes (address or callsign)."},
        "principal": {"type": "string", "description": "Optional: the human/entity granting authority."},
        "spend_max_usdc": {"type": "number", "description": "Hard ceiling per single action (USDC)."},
        "daily_cap_usdc": {"type": "number", "description": "Rolling 24h aggregate cap (USDC)."},
        "allowed_merchants": {"type": "array", "items": {"type": "string"}, "description": "Merchant allowlist (deny by default)."},
        "allowed_domains": {"type": "array", "items": {"type": "string"}, "description": "Domain allowlist (deny by default)."},
        "allowed_actions": {"type": "array", "items": {"type": "string"}, "description": "Permitted action verbs (deny by default)."},
        "velocity_max": {"type": "integer", "description": "Max number of transactions per window."},
        "expires_at": {"type": "integer", "description": "Unix time the mandate lapses."},
        "purpose": {"type": "string", "description": "Human-readable purpose of the mandate."},
    },
    "required": ["agent"],
}


def run(agent: str | None = None, principal: str = "", spend_max_usdc=None,
        daily_cap_usdc=None, allowed_merchants=None, allowed_domains=None,
        allowed_actions=None, velocity_max=None, expires_at=None,
        purpose: str = "", **_: object) -> dict:
    if not isinstance(agent, str) or not agent.strip():
        raise ValueError("agent is required (who the mandate authorizes)")
    grant = _grant.run(
        agent=agent.strip(),
        principal=principal or "",
        allowed_actions=allowed_actions,
        allowed_merchants=allowed_merchants,
        allowed_domains=allowed_domains,
        spend_max_usdc=spend_max_usdc,
        spend_window_usdc=daily_cap_usdc,
        spend_window_sec=86400 if daily_cap_usdc is not None else None,
        velocity_max=velocity_max,
        expires_at=expires_at,
        purpose=purpose or "",
    )
    out = {
        "product": "rhinogent",
        "artifact": "spend_mandate",
        "agent": agent.strip(),
        "note": (
            "Signed scope declared at issue time. The agent enforces it (self-custody); "
            "verify any later action against it with onyx_perm_check."
        ),
        "mandate": grant,
    }
    return _onyx_sign.attest(out, tool=NAME)
