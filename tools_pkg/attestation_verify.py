"""onyx_attestation_verify — prove an Onyx security verdict is real and untampered.

Every Onyx security tool signs its verdict (onyx_attestation, Ed25519+JCS). This
tool closes the loop: paste back any Onyx-signed result and get a cryptographic
yes/no — was it genuinely signed by Onyx, and has any field been altered since?

FREE (no x402). Verification must be free, or "signed" is just a word. This is
what turns the whole suite from "trust us" into "check it yourself": an auditor,
a counterparty agent, or a funder can independently prove every verdict Onyx
ever issued. Self-contained — uses the public key embedded in the attestation,
cross-checkable against /.well-known/onyx-pubkey.
"""
from __future__ import annotations

from . import _onyx_sign

NAME = "onyx_attestation_verify"
PRICE_USDC = "0"
TIER = "free"
DESCRIPTION = (
    "Verify an Onyx-signed security verdict. Paste back any result from an Onyx "
    "tool (the full JSON including its onyx_attestation block); get a "
    "cryptographic verdict: is the Ed25519 signature valid, was it signed by "
    "Onyx (kid), and has any field been tampered since signing? FREE. Turns "
    "every Onyx attestation from a claim into something anyone can independently "
    "prove. Cross-check the kid against /.well-known/onyx-pubkey."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "payload": {
            "type": "object",
            "description": "The full Onyx-signed result to verify, including its onyx_attestation block (exactly as returned by an Onyx tool).",
        },
    },
    "required": ["payload"],
}


def run(payload: dict | None = None, **_: object) -> dict:
    if not isinstance(payload, dict):
        return {"ok": False, "verified": False, "reason": "payload must be the full Onyx-signed JSON object"}
    att = payload.get("onyx_attestation")
    if not isinstance(att, dict):
        return {"ok": False, "verified": False, "reason": "no_attestation",
                "note": "This payload carries no onyx_attestation — it was not signed by Onyx."}

    result = _onyx_sign.verify(payload)
    verified = bool(result.get("ok"))
    return {
        "ok": True,
        "verified": verified,
        "reason": result.get("reason") if not verified else None,
        "kid": att.get("kid"),
        "alg": att.get("alg"),
        "signed_tool": att.get("tool"),
        "signed_at": att.get("signed_at"),
        "observed_hash": att.get("observed_hash"),
        "pubkey_source": att.get("verify_pubkey_at"),
        "summary": (
            f"VERIFIED ✓ — genuinely signed by Onyx ({att.get('kid')}), untampered, "
            f"from tool '{att.get('tool')}'."
            if verified else
            f"NOT VERIFIED ✗ — {result.get('reason')}. Do not trust this as an Onyx verdict."
        ),
    }


run.__when_to_use__ = (
    "When you receive an Onyx-signed result (your own or one a counterparty agent "
    "handed you claiming Onyx cleared it) and want to PROVE it's authentic and "
    "unaltered before relying on it. Also for auditors/funders independently "
    "validating that Onyx's security verdicts are cryptographically sound."
)
run.__vs_alternatives__ = (
    "Trusting a 'this was audited/screened' claim at face value is how forged "
    "approvals slip through. This re-derives the JCS canonical form, re-checks "
    "the hash, and verifies the Ed25519 signature against the embedded public key "
    "— a counterfeit or edited verdict fails instantly. Free, so there's no "
    "excuse not to verify."
)
run.__example_request__ = {"payload": {"verdict": "ALLOW", "onyx_attestation": {"kid": "onyx-...", "sig": "...", "...": "..."}}}
run.__example_response__ = {
    "ok": True, "verified": True, "kid": "onyx-febe855db1d43031",
    "signed_tool": "onyx_tx_guard",
    "summary": "VERIFIED — genuinely signed by Onyx, untampered, from tool 'onyx_tx_guard'.",
}
