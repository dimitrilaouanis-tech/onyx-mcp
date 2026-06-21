"""Onyx observation attestation — the signature on every ground-truth call.

Anyone can re-fetch a price. Only Onyx can return a price *signed by Onyx*.
This helper stamps every ground-truth oracle result with an Ed25519 signature
over the RFC-8785 (JCS) canonical form of the observation, so a buyer can
cryptographically prove "Onyx observed exactly this, at this time" — and that
nobody altered a field after the fact.

It reuses the SAME identity as the AR-1 receipt signer (env
ONYX_AR1_PRIVATE_KEY, base64 32-byte Ed25519). One key → one kid → one seal
across receipts AND observations. If the env key is absent we generate one and
persist it to `_onyx_sign_key.b64` next to this file so the local kid stays
stable and verifiable (set the env var in production to make it authoritative).

Underscore-prefixed → tools_pkg.discover() skips it (it's a helper, not a tool).
"""
from __future__ import annotations

import base64
import json
import os
import time
from hashlib import sha256
from pathlib import Path

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey, Ed25519PublicKey,
    )
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False

_ENV_KEY = "ONYX_AR1_PRIVATE_KEY"
_KEY_CACHE = Path(__file__).with_name("_onyx_sign_key.b64")
_SPEC = "https://onyx-actions.onrender.com/.well-known/onyx-attestation/v1"
_PUBKEY_URL = "https://onyx-actions.onrender.com/.well-known/onyx-pubkey"


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64u_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _jcs_number(n) -> str:
    """RFC-8785 §3.2.2.3 number serialization (ECMAScript Number::toString).

    The bug this fixes: Python's json renders the float 1.0 as "1.0" and 0.0 as
    "0.0", but RFC-8785 (which our spec and IETF draft cite) requires "1" and
    "0". That divergence made any third party verifying a payload containing a
    number get a FALSE forgery — fatal for a trust layer. bool is handled by the
    caller before this (in Python bool is an int subclass).
    """
    if isinstance(n, int):
        return str(n)
    # float
    if n != n or n in (float("inf"), float("-inf")):
        raise ValueError("NaN/Infinity are not permitted in JCS canonical JSON")
    if n.is_integer():
        # integral floats serialize as integers: 1.0 -> "1", -50.0 -> "-50"
        return str(int(n))
    # non-integral: Python's repr is the shortest round-tripping decimal (PEP
    # 3101 / since 3.1), which equals ECMAScript Number::toString for the
    # magnitudes Onyx emits (no exponent needed). e.g. 0.62 -> "0.62".
    r = repr(n)
    return r


def _jcs_ser(o) -> str:
    """Recursive RFC-8785 canonical serializer (replaces json.dumps so numbers
    are spec-correct). Object keys sorted by code point (matches Python's sort
    for the ASCII keys Onyx uses); strings use JSON minimal escaping."""
    if o is True:
        return "true"
    if o is False:
        return "false"
    if o is None:
        return "null"
    if isinstance(o, str):
        return json.dumps(o, ensure_ascii=False)
    if isinstance(o, bool):  # defensive; covered above
        return "true" if o else "false"
    if isinstance(o, (int, float)):
        return _jcs_number(o)
    if isinstance(o, dict):
        return "{" + ",".join(
            json.dumps(str(k), ensure_ascii=False) + ":" + _jcs_ser(v)
            for k, v in sorted(o.items(), key=lambda kv: str(kv[0]))
        ) + "}"
    if isinstance(o, (list, tuple)):
        return "[" + ",".join(_jcs_ser(v) for v in o) + "]"
    raise TypeError(f"not JSON-serializable in JCS: {type(o).__name__}")


def _jcs(obj) -> str:
    """RFC-8785 JCS canonical JSON: sorted keys, compact, spec-correct numbers."""
    return _jcs_ser(obj)


class _OnyxSigner:
    def __init__(self) -> None:
        self.kid = "no-crypto-installed"
        self.pub_b64 = ""
        self._priv = None
        self.ephemeral = False
        if not _HAS_CRYPTO:
            return
        priv = self._load_env() or self._load_cache() or self._generate_and_cache()
        self._priv = priv
        pub_bytes = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        self.pub_b64 = _b64u(pub_bytes)
        self.kid = "onyx-" + sha256(pub_bytes).hexdigest()[:16]

    def _load_env(self):
        raw = os.environ.get(_ENV_KEY, "").strip()
        if not raw:
            return None
        try:
            pb = base64.b64decode(raw)
            return Ed25519PrivateKey.from_private_bytes(pb[-32:]) if len(pb) >= 32 else None
        except Exception:
            return None

    def _load_cache(self):
        try:
            if _KEY_CACHE.exists():
                pb = base64.b64decode(_KEY_CACHE.read_text().strip())
                return Ed25519PrivateKey.from_private_bytes(pb[-32:]) if len(pb) >= 32 else None
        except Exception:
            return None
        return None

    def _generate_and_cache(self):
        priv = Ed25519PrivateKey.generate()
        self.ephemeral = True
        try:
            from cryptography.hazmat.primitives.serialization import (
                Encoding as E, PrivateFormat, NoEncryption,
            )
            raw = priv.private_bytes(E.Raw, PrivateFormat.Raw, NoEncryption())
            _KEY_CACHE.write_text(base64.b64encode(raw).decode("ascii"))
        except Exception:
            pass
        return priv

    def sign(self, payload: bytes) -> str | None:
        if self._priv is None:
            return None
        return _b64u(self._priv.sign(payload))


_SIGNER: _OnyxSigner | None = None


def signer() -> _OnyxSigner:
    global _SIGNER
    if _SIGNER is None:
        _SIGNER = _OnyxSigner()
    return _SIGNER


def attest(payload: dict, tool: str = "", public_url: str | None = None) -> dict:
    """Return `payload` with an `onyx_attestation` block signing the rest of it.

    The signature covers the JCS canonical form of `payload` with the
    `onyx_attestation` key removed — so the whole observation is sealed and any
    later edit invalidates it. Non-dict / falsy payloads are returned as-is.
    """
    if not isinstance(payload, dict):
        return payload
    s = signer()
    base = (public_url or "https://onyx-actions.onrender.com").rstrip("/")
    body = {k: v for k, v in payload.items() if k != "onyx_attestation"}
    canonical = _jcs(body)
    observed_hash = sha256(canonical.encode("utf-8")).hexdigest()
    att = {
        "alg": "Ed25519+JCS",
        "kid": s.kid,
        "public_key": s.pub_b64,
        "tool": tool or payload.get("tool") or "",
        "observed_hash": "sha256:" + observed_hash,
        "signed_at": int(time.time()),
        "spec": _SPEC,
        "verify_pubkey_at": base.rstrip("/") + "/.well-known/onyx-pubkey",
    }
    sig = s.sign(canonical.encode("utf-8"))
    att["sig"] = sig if sig else "unsigned:no-crypto"
    payload["onyx_attestation"] = att
    return payload


def verify(payload: dict) -> dict:
    """Verify an `onyx_attestation` against the payload it seals.

    Returns {ok, reason?, kid?}. Self-contained: uses the public_key embedded
    in the attestation, so any third party can run it.
    """
    if not _HAS_CRYPTO:
        return {"ok": False, "reason": "no_crypto_installed"}
    att = (payload or {}).get("onyx_attestation")
    if not isinstance(att, dict):
        return {"ok": False, "reason": "no_attestation"}
    sig_b64 = att.get("sig", "")
    if not sig_b64 or sig_b64.startswith("unsigned:"):
        return {"ok": False, "reason": "unsigned"}
    try:
        body = {k: v for k, v in payload.items() if k != "onyx_attestation"}
        canonical = _jcs(body)
        # integrity: recomputed hash must match the claimed one
        recomputed = "sha256:" + sha256(canonical.encode("utf-8")).hexdigest()
        if att.get("observed_hash") != recomputed:
            return {"ok": False, "reason": "hash_mismatch", "kid": att.get("kid")}
        # Structural hardening (the "Psychic Signature" / zero-value class):
        # reject malformed/zero key or signature BEFORE the crypto call, so a
        # blank or wrong-length input can never slip through a lenient path.
        pub_bytes = _b64u_decode(att.get("public_key") or "")
        sig_bytes = _b64u_decode(sig_b64)
        if len(pub_bytes) != 32 or pub_bytes == b"\x00" * 32:
            return {"ok": False, "reason": "bad_public_key", "kid": att.get("kid")}
        if len(sig_bytes) != 64 or sig_bytes == b"\x00" * 64:
            return {"ok": False, "reason": "bad_signature", "kid": att.get("kid")}
        pub = Ed25519PublicKey.from_public_bytes(pub_bytes)
        pub.verify(sig_bytes, canonical.encode("utf-8"))
        return {"ok": True, "kid": att.get("kid"), "alg": att.get("alg")}
    except Exception as e:
        return {"ok": False, "reason": "sig_verify_failed", "detail": str(e)[:200]}


def sign_card(card: dict, public_url: str | None = None) -> dict:
    """Attach an A2A-spec JWS signature to an AgentCard (`signatures[]`).

    Detached-JWS over the card: the signed payload is JCS(card without its
    `signatures` field), so any later edit to the card breaks the signature.
    Each entry carries `protected` (b64url JWS header with alg=EdDSA, our kid,
    and the public JWK) and `signature` (b64url Ed25519 over
    `protected . payload`). A verifier reconstructs the payload from the card
    itself — nothing extra is stored. If crypto is unavailable we return the
    card UNSIGNED rather than fake a signature.
    """
    if not isinstance(card, dict):
        return card
    s = signer()
    body = {k: v for k, v in card.items() if k != "signatures"}
    payload_b64 = _b64u(_jcs(body).encode("utf-8"))
    header = {
        "alg": "EdDSA",
        "kid": s.kid,
        "jwk": {"kty": "OKP", "crv": "Ed25519", "x": s.pub_b64},
        "onyx_pubkey_url": _PUBKEY_URL,
    }
    protected_b64 = _b64u(_jcs(header).encode("utf-8"))
    sig = s.sign((protected_b64 + "." + payload_b64).encode("ascii"))
    if not sig:
        return card
    out = dict(card)
    out["signatures"] = [{"protected": protected_b64, "signature": sig}]
    return out


def verify_card(card: dict) -> dict:
    """Verify an AgentCard's A2A `signatures[]` (detached JWS). Returns
    {ok, kid?, onyx_signed?, reason?}. Reconstructs the payload from the card
    minus `signatures`, exactly as sign_card() signed it."""
    if not _HAS_CRYPTO:
        return {"ok": False, "reason": "no_crypto_installed"}
    if not isinstance(card, dict):
        return {"ok": False, "reason": "not_a_card"}
    sigs = card.get("signatures")
    if not isinstance(sigs, list) or not sigs:
        return {"ok": False, "reason": "no_signatures"}
    body = {k: v for k, v in card.items() if k != "signatures"}
    payload_b64 = _b64u(_jcs(body).encode("utf-8"))
    try:
        mine = signer().pub_b64
    except Exception:
        mine = None
    for entry in sigs:
        if not isinstance(entry, dict):
            continue
        protected_b64 = entry.get("protected") or ""
        sig_b64 = entry.get("signature") or ""
        try:
            header = json.loads(_b64u_decode(protected_b64))
            pub_b64 = (header.get("jwk") or {}).get("x") or ""
            pub_bytes = _b64u_decode(pub_b64)
            sig_bytes = _b64u_decode(sig_b64)
            if len(pub_bytes) != 32 or pub_bytes == b"\x00" * 32:
                continue
            if len(sig_bytes) != 64 or sig_bytes == b"\x00" * 64:
                continue
            Ed25519PublicKey.from_public_bytes(pub_bytes).verify(
                sig_bytes, (protected_b64 + "." + payload_b64).encode("ascii"))
            return {"ok": True, "kid": header.get("kid"),
                    "onyx_signed": bool(mine and pub_b64 == mine)}
        except Exception:
            continue
    return {"ok": False, "reason": "sig_verify_failed"}


def is_onyx_signed(payload: dict) -> dict:
    """STRICTER than verify(): confirms the signature is by OUR pinned key, not
    just any self-consistent key embedded in the envelope.

    verify() alone proves "internally consistent" — an attacker can sign their
    OWN forged payload with their OWN key and embed their OWN pubkey, and it
    passes. That is the key-substitution hole. This function additionally binds
    the embedded key to Onyx's live signing key, so a self-signed forgery fails.
    Use this for the /fool win-check and to report genuineness on /verify.
    """
    base = verify(payload)
    if not base.get("ok"):
        return {"ok": False, "onyx_signed": False, "reason": base.get("reason", "invalid")}
    att = (payload or {}).get("onyx_attestation") or {}
    embedded = att.get("public_key")
    try:
        mine = signer().pub_b64
    except Exception:
        mine = None
    if not mine or embedded != mine:
        return {
            "ok": False, "onyx_signed": False, "reason": "key_not_onyx",
            "detail": "signature is internally consistent but NOT made by Onyx's key",
            "kid": att.get("kid"),
        }
    return {"ok": True, "onyx_signed": True, "kid": att.get("kid"), "alg": att.get("alg")}
