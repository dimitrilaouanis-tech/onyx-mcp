"""Counterparty Attestation Protocol (CAP) — the live, machine-readable standard.

The Vitalik move: publish the canonical spec for the one primitive nobody else owns —
a signed, neutral answer to "is this counterparty real?" — and serve it as an open
standard others can implement against. x402/AP2 verify the payment; ERC-8004/8126
verify the agent; CAP verifies the COUNTERPARTY. Full prose spec lives in
COUNTERPARTY_ATTESTATION.md (the citable artifact); this serves the machine-readable
manifest + A2A extension declaration.
"""
from __future__ import annotations

from . import _onyx_sign

EXTENSION_URI = "https://0n1x.org/extensions/counterparty-attestation/v1"


def manifest(base: str = "https://onyx-actions.onrender.com") -> dict:
    base = (base or "").rstrip("/")
    out = {
        "standard": "Counterparty Attestation Protocol (CAP)",
        "version": "0.1",
        "status": "Draft",
        "one_line": "x402/AP2 verify the payment; ERC-8004/8126 verify the agent; "
                    "CAP verifies the COUNTERPARTY (is the merchant/price/token real).",
        "the_gap": "Visa, 2026: 'protocols verify payment integrity, not merchant "
                   "legitimacy.' CAP fills exactly that seat.",
        "reference_issuer": "0n1x",
        "extension_uri": EXTENSION_URI,

        # The binding neutrality law (Vitalik's 4 rules) — what makes an issuer trustable
        "credible_neutrality": [
            "Sign FACTS, not judgments (observed inputs, never the issuer's opinion).",
            "Open + publicly verifiable (Ed25519-signed; trust the math, not the issuer).",
            "Simple + published method (fewer hidden parameters = fewer places to hide bias).",
            "Versioned, not silently changed (no per-counterparty or secret changes).",
            "No conflict: an issuer MUST NOT attest to a counterparty it profits from.",
        ],

        # The attestation envelope (the reference format)
        "attestation_envelope": {
            "cap_version": "0.1",
            "subject": {"type": "merchant|price|token|contract", "id": "<e.g. stripe.com>"},
            "facts": [{"k": "<observation key>", "v": "<value>"}],
            "issuer": "0n1x", "kid": "<signing key id>",
            "issued_at": "<unix>", "expires_at": "<unix>",
            "signature": "ed25519 over JCS(envelope minus signature) — RFC 8785 + 7515",
        },

        # The method
        "method": {
            "counterparty.verify": {
                "request": {"subject": {"type": "...", "id": "..."}},
                "response": "a signed CAP attestation",
                "free_first_call": True,
            }
        },

        # A2A extension declaration (paste into an Agent Card's capabilities.extensions)
        "a2a_extension_declaration": {
            "uri": EXTENSION_URI,
            "description": "Signed facts about a merchant/price/token before payment.",
            "required": False,
            "client_optin_header": f"A2A-Extensions: {EXTENSION_URI}",
        },

        # Bindings + running code
        "bindings": {
            "a2a": "primary transport (signing primitives identical to A2A card signing)",
            "erc8004": "register as a Validation Registry validator posting counterparty "
                       "fact-attestations (complements ERC-8126's agent score)",
        },
        "running_code": {
            "free_first_verdict": f"{base}/api/check?url=<domain>",
            "verify_any_attestation": f"{base}/verify",
            "published_key": f"{base}/.well-known/onyx-pubkey",
            "safe_onboarding": f"{base}/guide",
            "full_spec": "COUNTERPARTY_ATTESTATION.md (repo) — the citable artifact",
        },
        "rough_consensus": "v0.1, deliberately small. We seek OBJECTIONS — open an issue, "
                           "propose a fact every agent should check, implement a competing "
                           "neutral issuer. The standard wins only if >1 party can issue it.",
    }
    return _onyx_sign.attest(out, tool="onyx_cap")
