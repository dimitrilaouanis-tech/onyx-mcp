"""Onyx as an ERC-8004 Validation-Registry-compatible signed validator.

ERC-8004 (Trustless Agents) ships an Identity + Reputation registry (live on
Base/Eth at 0x8004…) and a Validation Registry whose interface is defined but
whose canonical address is still being finalized (spec "under active update").
The Validation Registry lets ANY address act as a neutral validator and publish
`validationResponse(requestHash, response 0-100, responseURI, responseHash, tag)`
against an agent/subject — and almost nobody is filling it.

This module makes Onyx that validator NOW, off-chain: it runs our signed
ground-truth check, maps the verdict to a 0-100 `response`, and returns a record
in the exact ERC-8004 validationResponse shape — Ed25519-signed, with
`responseHash` committing to the underlying verdict and `responseURI` pointing at
the public record. The instant the Validation Registry address is published, the
same record is submitted on-chain unchanged. Neutral by design — facts, not
judgments — which is the conflict-free validator the registry needs.

Stdlib-only. Underscore-prefixed -> not a tool.
"""
from __future__ import annotations

import hashlib
import time

from . import _onyx_sign

_SPEC = "https://eips.ethereum.org/EIPS/eip-8004"
_BASE = "https://onyx-actions.onrender.com"
# Live ERC-8004 registries (deterministic addresses, all listed mainnets incl. Base 8453)
_IDENTITY_REGISTRY = "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432"
_REPUTATION_REGISTRY = "0x8004BAa17C55a88189AE136b182e5fdA19dE9b63"
VALIDATOR_TAGS = ["merchant-fact", "price-truth", "scam-risk", "liveness"]


def validator_card(base: str = _BASE) -> dict:
    s = _onyx_sign.signer()
    card = {
        "validator": "onyx",
        "role": "ERC-8004 Validation-Registry validator (neutral, off-chain ready)",
        "alg": "Ed25519+JCS",
        "kid": s.kid,
        "public_key": s.pub_b64,
        "tags": VALIDATOR_TAGS,
        "response_scale": "0-100 (0 = high-risk/HOLD, 100 = clean/established)",
        "neutrality": "Onyx earns nothing from the agents/merchants it validates — "
                      "the conflict-free validator ERC-8004's Validation Registry needs.",
        "method": "Run Onyx's signed ground-truth check, map verdict to a 0-100 "
                  "response, emit an ERC-8004 validationResponse-shaped record. "
                  "responseHash commits to the underlying signed verdict; "
                  "responseURI is the public record. On-chain submission ready "
                  "pending the Validation Registry canonical address.",
        "identity_registry": _IDENTITY_REGISTRY,
        "reputation_registry": _REPUTATION_REGISTRY,
        "spec": _SPEC,
        "verify": base.rstrip("/") + "/verify",
    }
    return _onyx_sign.attest(card, tool="onyx_erc8004_validator_card")


def validate(subject_id: str, tag: str = "merchant-fact",
             request_hash: str = "", base: str = _BASE) -> dict:
    """Produce an ERC-8004 validationResponse-shaped, Ed25519-signed validation
    for a subject (domain/agent). 0-100 response derived from Onyx's signed check."""
    from . import _scamcheck
    base = (base or _BASE).rstrip("/")
    sid = (subject_id or "").strip()
    if not sid:
        raise ValueError("subject_id required (a domain or agent endpoint)")

    chk = _scamcheck.check(sid)                     # signed verdict, trust_score 0-100
    score = int(chk.get("trust_score", 0))
    att = chk.get("onyx_attestation", {}) or {}
    response_hash = att.get("observed_hash", "")    # hash of the underlying signed verdict
    host = chk.get("site", sid)
    rh = request_hash or ("sha256:" + hashlib.sha256(("onyx|" + tag + "|" + host).encode()).hexdigest())

    record = {
        "erc8004": "validationResponse",
        "tag": tag,
        "subject": host,
        "request_hash": rh,
        "response": score,                          # uint8 0-100
        "response_meaning": "0 = high-risk/HOLD, 100 = clean/established",
        "verdict": chk.get("verdict"),
        "responseURI": f"{base}/check?url={host}",
        "responseHash": response_hash,
        "validator_kid": _onyx_sign.signer().kid,
        "validated_at": int(time.time()),
        "onchain_status": "off-chain signed; ready to submit to the ERC-8004 "
                          "Validation Registry the moment its canonical address ships",
        "spec": _SPEC,
        "neutrality_note": "Onyx has no stake in this subject — a neutral signed fact, "
                           "not a judgment. Verify at " + base + "/verify",
    }
    return _onyx_sign.attest(record, tool="onyx_erc8004_validation")
