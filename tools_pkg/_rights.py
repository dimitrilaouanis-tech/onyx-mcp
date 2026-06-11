"""Automatic usage-rights stamp — the reference implementation of the x402
binding described in spec/USAGE_RIGHTS_v0.md §"x402 binding".

Every PAID Onyx output ships a signed `usage-rights-envelope/v0` in the
`X-Onyx-Rights` response header, minted through the SAME codepath as the
`onyx_usage_rights` tool (one envelope shape, one spec). The tool is the
custom-terms path; this is the zero-effort default that rides every sale.

Underscore-prefixed → tools_pkg.discover() skips it (helper, not a tool).
"""
from __future__ import annotations

from . import _onyx_sign, usage_rights

# Default terms on every paid Onyx output. "with-attribution" on redistribute/
# derivatives lets our signed facts spread WITH our name attached (free reach);
# resale/retrain stay denied. The onyx_usage_rights tool sets custom terms.
DEFAULT_RIGHTS = {
    "resale": "deny",
    "redistribute": "with-attribution",
    "derivatives": "with-attribution",
    "retrain": "deny",
    "cache_ttl_seconds": 3600,
}

SPEC = "usage-rights-envelope/v0"


def stamp(output, *, licensor: str, payment_ref: str | None = None) -> dict:
    """Mint the canonical usage-rights envelope for a paid output (hash-bound)."""
    return usage_rights.run(
        rights=dict(DEFAULT_RIGHTS),
        licensor=licensor,
        output=output,
        payment_ref=payment_ref,
    )


def policy_card(*, issuer: str, public_url: str | None = None) -> dict:
    """Signed server-level rights card → /.well-known/rights.json. The public
    'what buying from this agent grants you' declaration."""
    base = (public_url or "https://onyx-actions.onrender.com").rstrip("/")
    card = {
        "spec": SPEC,
        "issuer": issuer,
        "default_rights": dict(DEFAULT_RIGHTS),
        "custom_terms_tool": "onyx_usage_rights",
        "per_output_header": "X-Onyx-Rights — base64url of the signed envelope, "
                             "hash-bound to the response body.",
        "verify_free": f"{base}/verify",
        "spec_doc": "https://github.com/dimitrilaouanis-tech/onyx-mcp/blob/main/spec/USAGE_RIGHTS_v0.md",
        "pubkey": f"{base}/.well-known/onyx-pubkey",
    }
    return _onyx_sign.attest(card, tool="usage_rights_policy", public_url=base)
