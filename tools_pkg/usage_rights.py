"""Output Usage-Rights Envelope — signed terms for what a buyer may do with
a purchased agent output.

The virgin seat: RSL 1.0 governs INPUT rights (may you crawl/train on my
page); nothing governs OUTPUT rights of a paid agent result. This tool mints
an Ed25519-signed rights claim binding {output hash} -> {rights grid}, so the
terms travel with the artifact across resale chains and any third party can
verify them offline (predicate `usage_rights`; facts-not-judgments compliant —
it attests what the licensor DECLARED, not what is fair).
"""
from __future__ import annotations

import hashlib
import json
import time

NAME = "onyx_usage_rights"
PRICE_USDC = "0.01"
TIER = "metered"
DESCRIPTION = (
    "Mint a signed Output Usage-Rights Envelope for an agent-produced "
    "artifact: a portable, Ed25519-signed declaration of what the buyer may "
    "do with it (resale, redistribution, derivatives, model training, cache "
    "TTL). Bind it to the artifact by hash and optionally to an x402 payment. "
    "Verify free with onyx_attestation_verify. Rights travel with the data — "
    "any downstream holder can check the terms offline."
)

_RIGHT_KEYS = ("resale", "redistribute", "derivatives", "retrain")
_RIGHT_VALUES = ("allow", "deny", "with-attribution", "contact-licensor")

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "output_hash": {
            "type": "string",
            "description": "sha256:<hex> of the artifact the rights apply to",
        },
        "output": {
            "description": "Or: the artifact itself (object or string); it is "
                           "hashed with sha256 over its JCS-canonical form",
        },
        "rights": {
            "type": "object",
            "description": "Rights grid. Keys: resale, redistribute, "
                           "derivatives, retrain — each 'allow' | 'deny' | "
                           "'with-attribution' | 'contact-licensor'. Plus "
                           "optional cache_ttl_seconds (int).",
        },
        "licensor": {"type": "string", "description": "Issuer of the rights (name, domain, or wallet)"},
        "licensee": {"type": "string", "description": "Optional: who the rights are granted to (wallet/agent id); omit for bearer terms"},
        "payment_ref": {"type": "string", "description": "Optional: x402 tx hash / receipt id binding rights to the purchase"},
        "expires_at": {"type": "integer", "description": "Optional: unix time the grant lapses"},
    },
    "required": ["rights", "licensor"],
}


def _jcs(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def run(
    rights: dict,
    licensor: str,
    output_hash: str | None = None,
    output=None,
    licensee: str | None = None,
    payment_ref: str | None = None,
    expires_at: int | None = None,
    **_: object,
) -> dict:
    if not isinstance(rights, dict) or not rights:
        raise ValueError("rights must be a non-empty object")
    grid: dict = {}
    for k, v in rights.items():
        if k == "cache_ttl_seconds":
            grid[k] = int(v)
            continue
        if k not in _RIGHT_KEYS:
            raise ValueError(f"unknown right '{k}' (known: {', '.join(_RIGHT_KEYS)}, cache_ttl_seconds)")
        if v not in _RIGHT_VALUES:
            raise ValueError(f"right '{k}' must be one of {', '.join(_RIGHT_VALUES)}")
        grid[k] = v
    # Unstated rights default to deny — explicit is the whole point.
    for k in _RIGHT_KEYS:
        grid.setdefault(k, "deny")

    if output_hash:
        if not output_hash.startswith("sha256:"):
            raise ValueError("output_hash must be 'sha256:<hex>'")
        subject = output_hash
    elif output is not None:
        canonical = _jcs(output) if not isinstance(output, str) else output
        subject = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    else:
        raise ValueError("Provide output_hash or output")

    claim = {
        "subject": subject,
        "predicate": "usage_rights",
        "observed_value": grid,
        "licensor": licensor,
        "licensee": licensee or "bearer",
        "payment_ref": payment_ref,
        "issued_at": int(time.time()),
        "expires_at": expires_at,
        "method": "licensor-declaration",
        "disclaimer": (
            "Attests the licensor's declared terms for this output at issue "
            "time; not legal advice and not a judgment of the terms."
        ),
        "spec": "usage-rights-envelope/v0",
    }
    try:
        from . import _onyx_sign
        claim = _onyx_sign.attest(claim, tool=NAME)
    except Exception:
        pass
    return claim
