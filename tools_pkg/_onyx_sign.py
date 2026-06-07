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


def _jcs(obj) -> str:
    """RFC-8785 JCS canonical JSON: sorted keys, compact, UTF-8."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


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
        pub = Ed25519PublicKey.from_public_bytes(_b64u_decode(att["public_key"]))
        pub.verify(_b64u_decode(sig_b64), canonical.encode("utf-8"))
        return {"ok": True, "kid": att.get("kid"), "alg": att.get("alg")}
    except Exception as e:
        return {"ok": False, "reason": "sig_verify_failed", "detail": str(e)[:200]}
