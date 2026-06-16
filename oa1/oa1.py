"""oa1 - reference implementation of the Onyx Attestation protocol (OA-1).

Drop this one file into any service and your outputs become verifiable claims:
a consumer can prove offline that you signed exactly this payload, and later
bind a real-world outcome back to it. No framework, no account, no network call
to verify. The only dependency is `cryptography` (Ed25519).

    from oa1 import sign, verify, claim_id

    out = sign({"verdict": "BLOCK", "risk_score": 100}, tool="my_tool")
    #   -> adds out["onyx_attestation"] = {alg, kid, public_key, sig, ...}
    verify(out)            # -> {"ok": True, "kid": "..."}
    claim_id(out)          # -> "sha256:..."  (stable, content-addressed id)

This is byte-for-byte compatible with the Onyx production signer, so an OA-1
envelope from ANY issuer verifies with this same code. The field name
`onyx_attestation` is the reserved protocol field; the issuer is identified by
its `kid` / `public_key`, not by the field name. Bring your own keypair and you
are a first-class OA-1 issuer.

Spec:    https://onyx-actions.onrender.com/.well-known/onyx-attestation/v1
License: MIT (this file) / CC0 (the spec text).
"""
from __future__ import annotations

import base64
import json
import os
import time
from hashlib import sha256

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding, NoEncryption, PrivateFormat, PublicFormat,
)

ATTESTATION_FIELD = "onyx_attestation"
ALG = "Ed25519+JCS"
SPEC = "https://onyx-actions.onrender.com/.well-known/onyx-attestation/v1"


# ── base64url (unpadded), as the spec mandates ──────────────────────────────
def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64u_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def jcs(obj) -> str:
    """RFC-8785 JCS canonical JSON: sorted keys, compact, UTF-8, no escaping."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _canonical(payload: dict) -> bytes:
    body = {k: v for k, v in payload.items() if k != ATTESTATION_FIELD}
    return jcs(body).encode("utf-8")


# ── keys ────────────────────────────────────────────────────────────────────
def load_key(b64: str | None = None) -> Ed25519PrivateKey:
    """Load an Ed25519 private key from base64 (32 raw bytes, std or url-safe).
    Falls back to env OA1_PRIVATE_KEY / ONYX_AR1_PRIVATE_KEY, else generates an
    ephemeral key (fine for tests; set one in prod so your kid stays stable)."""
    raw = b64 or os.environ.get("OA1_PRIVATE_KEY") or os.environ.get("ONYX_AR1_PRIVATE_KEY")
    if raw:
        try:
            pb = base64.b64decode(raw + "=" * (-len(raw) % 4))
            return Ed25519PrivateKey.from_private_bytes(pb[-32:])
        except Exception:
            pass
    return Ed25519PrivateKey.generate()


def generate_key() -> str:
    """Mint a fresh keypair; returns the base64 private key to store as a secret."""
    priv = Ed25519PrivateKey.generate()
    return base64.b64encode(
        priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    ).decode("ascii")


def kid_of(priv: Ed25519PrivateKey, issuer: str = "onyx") -> str:
    pub = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return f"{issuer}-" + sha256(pub).hexdigest()[:16]


# ── sign / verify ─────────────────────────────────────────────────────────────
def sign(payload: dict, *, key: str | Ed25519PrivateKey | None = None,
         tool: str = "", issuer: str = "onyx", public_url: str | None = None) -> dict:
    """Seal `payload` with an OA-1 attestation. Mutates and returns `payload`.
    The signature covers the JCS-canonical form with the attestation field
    removed, so any later edit to any field invalidates it."""
    if not isinstance(payload, dict):
        return payload
    priv = key if isinstance(key, Ed25519PrivateKey) else load_key(key)
    pub = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    canonical = _canonical(payload)
    base = (public_url or "https://onyx-actions.onrender.com").rstrip("/")
    payload[ATTESTATION_FIELD] = {
        "alg": ALG,
        "kid": f"{issuer}-" + sha256(pub).hexdigest()[:16],
        "public_key": _b64u(pub),
        "tool": tool or payload.get("tool") or "",
        "observed_hash": "sha256:" + sha256(canonical).hexdigest(),
        "signed_at": int(time.time()),
        "spec": SPEC,
        "verify_pubkey_at": base + "/.well-known/onyx-pubkey",
        "sig": _b64u(priv.sign(canonical)),
    }
    return payload


def verify(payload: dict) -> dict:
    """Verify an OA-1 envelope using the public key embedded in it. Self-
    contained: needs no network and no prior knowledge of the issuer.
    Returns {ok, reason?, kid?}."""
    att = (payload or {}).get(ATTESTATION_FIELD)
    if not isinstance(att, dict):
        return {"ok": False, "reason": "no_attestation"}
    sig = att.get("sig", "")
    if not sig or sig.startswith("unsigned:"):
        return {"ok": False, "reason": "unsigned"}
    try:
        canonical = _canonical(payload)
        if att.get("observed_hash") != "sha256:" + sha256(canonical).hexdigest():
            return {"ok": False, "reason": "hash_mismatch", "kid": att.get("kid")}
        Ed25519PublicKey.from_public_bytes(
            _b64u_decode(att["public_key"])
        ).verify(_b64u_decode(sig), canonical)
        return {"ok": True, "kid": att.get("kid"), "alg": att.get("alg")}
    except Exception as e:
        return {"ok": False, "reason": "sig_verify_failed", "detail": str(e)[:200]}


def claim_id(payload: dict) -> str | None:
    """The stable, content-addressed id of a signed claim (its observed_hash).
    Use this as the key when you bind an outcome back to the claim."""
    att = (payload or {}).get(ATTESTATION_FIELD) or {}
    return att.get("observed_hash")


def bind_outcome(signed_claim: dict, outcome: str, *, tx_hash: str | None = None,
                 detail: str | None = None) -> dict:
    """Part 2 of OA-1: produce an outcome record bound to a signed claim. The
    binding is ACCEPTED ONLY IF the claim's signature verifies first - an
    outcome can never attach to a claim its issuer did not sign."""
    v = verify(signed_claim)
    if not v.get("ok"):
        return {"ok": False, "error": "unverifiable_claim", "reason": v.get("reason")}
    att = signed_claim.get(ATTESTATION_FIELD) or {}
    return {
        "ok": True,
        "claim_id": att.get("observed_hash"),
        "issuer_kid": att.get("kid"),
        "tool": att.get("tool"),
        "verdict": signed_claim.get("verdict") or signed_claim.get("status"),
        "outcome": outcome,
        "tx_hash": tx_hash,
        "detail": detail,
        "bound_at": int(time.time()),
    }


# Ergonomic alias — the feedback-loop call agents make after acting on a verdict.
# `report(claim, "confirmed")` reads naturally next to `verify(claim)`. To POST it
# back to the live ledger so it counts in onyx_track_record, send the returned
# record to <issuer>/v1/onyx_outcome_report.
report = bind_outcome
