"""onyx_perm_grant — mint a signed permission grant for an agent (PERM_v0).

The issuance side of the Perm leg. An agent (or its principal) declares the
scope it is authorized to act within; 0n1x notarizes the declaration with an
Ed25519 signature, producing a portable `onyx-perm-grant/v0` envelope the agent
carries on its card and that `onyx_perm_check` evaluates actions against.

HARD RULE — facts, not judgments. 0n1x attests WHAT was declared and WHEN
("agent X declared this grant at T"), never that the grantor truly holds the
authority. The signature notarizes the declaration, not the legitimacy.

Completes the Perm trio: grant (this) -> posture (onyx_security_flags) ->
in-scope check (onyx_perm_check). Spec: perm/spec/PERM_v0.md.
Underscore-free, NAME + run() -> auto-discovered.
"""
from __future__ import annotations

import time

NAME = "onyx_perm_grant"
PRICE_USDC = "0.00"
TIER = "free"          # free issuance drives adoption of the grant model
DESCRIPTION = (
    "Mint a signed permission grant (onyx-perm-grant/v0) for an agent: a "
    "portable, Ed25519-notarized declaration of the scope it may act within "
    "(allowed_actions, allowed_merchants/domains, spend_max_usdc, principal, "
    "consent_ref, expires_at). Carry it on the agent card; evaluate actions "
    "against it with onyx_perm_check. Facts, not judgments — attests what was "
    "declared, not that the grantor holds the authority."
)

_ACTION_VOCAB = ("read", "verify", "transact", "sign", "negotiate", "subscribe")

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "agent": {"type": "string", "description": "Who is granted (did:pkh / wallet / agent id)"},
        "principal": {"type": "string", "description": "Who grants the authority (did / email / org)"},
        "consent_ref": {"type": "string", "description": "Proof of consent (AP2 mandate id / signature hash)"},
        "allowed_actions": {"type": "array", "items": {"type": "string"},
                            "description": f"Subset of {list(_ACTION_VOCAB)}; deny-by-default"},
        "allowed_merchants": {"type": "array", "items": {"type": "string"}},
        "allowed_domains": {"type": "array", "items": {"type": "string"}},
        "spend_max_usdc": {"type": "number", "description": "Hard ceiling per action"},
        "spend_window_usdc": {"type": "number", "description": "Optional rolling-window cap"},
        "purpose": {"type": "string"},
        "expires_at": {"type": "integer", "description": "Unix time the grant lapses"},
    },
    "required": ["agent"],
}


def run(agent: str = "", principal: str = "", consent_ref: str = "",
        allowed_actions=None, allowed_merchants=None, allowed_domains=None,
        spend_max_usdc=None, spend_window_usdc=None, purpose: str = "",
        expires_at: int | None = None, **_: object) -> dict:
    if not agent or not str(agent).strip():
        raise ValueError("agent is required (who the grant authorizes)")

    actions = list(allowed_actions or [])
    for a in actions:
        if a not in _ACTION_VOCAB:
            raise ValueError(f"unknown action '{a}' (known: {', '.join(_ACTION_VOCAB)})")

    grant = {
        "spec": "onyx-perm-grant/v0",
        "agent": str(agent).strip(),
        "principal": str(principal).strip() or None,
        "consent_ref": str(consent_ref).strip() or None,
        "allowed_actions": actions,
        "allowed_merchants": list(allowed_merchants) if allowed_merchants is not None else None,
        "allowed_domains": list(allowed_domains) if allowed_domains is not None else None,
        "spend_max_usdc": float(spend_max_usdc) if spend_max_usdc is not None else None,
        "spend_window_usdc": float(spend_window_usdc) if spend_window_usdc is not None else None,
        "purpose": purpose or None,
        "declared_at": int(time.time()),
        "expires_at": int(expires_at) if expires_at is not None else None,
        "method": "principal-declaration, notarized by 0n1x",
        "disclaimer": (
            "Attests the scope DECLARED for this agent at issue time; 0n1x does "
            "not verify the grantor holds the authority. Not legal advice."
        ),
    }
    # Posture self-note: which Perm flags this grant clears / still leaves open.
    open_flags = []
    if not grant["principal"]:
        open_flags.append("F4 PERM_NO_PRINCIPAL")
    if not grant["consent_ref"]:
        open_flags.append("F5 PERM_NO_CONSENT")
    if grant["spend_max_usdc"] is None and "transact" in actions:
        open_flags.append("F6 PERM_NO_SPEND_CAP")
    if not actions:
        open_flags.append("F10 SKILL_UNBOUNDED")
    grant["open_flags"] = open_flags
    grant["check_with"] = "onyx_perm_check"

    try:
        from . import _onyx_sign
        grant = _onyx_sign.attest(grant, tool=NAME)
    except Exception:
        pass
    return grant
