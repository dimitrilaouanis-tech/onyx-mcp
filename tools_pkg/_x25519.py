"""X25519 — encryption alongside Ed25519 (which only signs). Lets agents send 0n1x
ENCRYPTED payloads (private messages, sealed mandates) that only we can open, and
lets us seal payloads to another agent's X25519 public key.

Ed25519 = signing (authenticity). X25519 = key-exchange (confidentiality). Same
curve family, different job. This is a NaCl-style sealed box: per-message
ephemeral ECDH -> HKDF -> AES-256-GCM. Forward-secret per message.

Persistent key: env ONYX_X25519_PRIVATE_KEY (base64 32-byte) or a cached file
next to this module (set the env in production to pin it across deploys, exactly
like the Ed25519 signer). Stdlib + cryptography (already a dep).
"""
from __future__ import annotations

import base64
import os
from pathlib import Path

try:
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    _HAS = True
except ImportError:
    _HAS = False

_ENV = "ONYX_X25519_PRIVATE_KEY"
_CACHE = Path(__file__).with_name("_onyx_x25519_key.b64")
_INFO = b"onyx-x25519-sealedbox-v1"


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _b64u_dec(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _load_priv() -> "X25519PrivateKey | None":
    if not _HAS:
        return None
    raw = os.environ.get(_ENV, "").strip()
    if raw:
        try:
            return X25519PrivateKey.from_private_bytes(base64.b64decode(raw)[-32:])
        except Exception:
            pass
    try:
        if _CACHE.exists():
            return X25519PrivateKey.from_private_bytes(base64.b64decode(_CACHE.read_text().strip())[-32:])
    except Exception:
        pass
    priv = X25519PrivateKey.generate()
    try:
        raw32 = priv.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                   serialization.NoEncryption())
        _CACHE.write_text(base64.b64encode(raw32).decode("ascii"))
    except Exception:
        pass
    return priv


_PRIV = None


def _priv() -> "X25519PrivateKey | None":
    global _PRIV
    if _PRIV is None:
        _PRIV = _load_priv()
    return _PRIV


def public_key_b64() -> str:
    """Our X25519 public key (base64url) — publish it so agents can encrypt to us."""
    p = _priv()
    if not p:
        return ""
    return _b64u(p.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))


def _derive(shared: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_INFO).derive(shared)


def seal(plaintext: str | bytes, recipient_pub_b64: str) -> dict:
    """Encrypt to a recipient's X25519 public key. Returns the sealed envelope
    (ephemeral pubkey + nonce + ciphertext, all base64url). Only the recipient
    (holder of the matching private key) can open it."""
    if not _HAS:
        return {"error": "no_crypto"}
    pt = plaintext.encode() if isinstance(plaintext, str) else plaintext
    recip = X25519PublicKey.from_public_bytes(_b64u_dec(recipient_pub_b64))
    eph = X25519PrivateKey.generate()
    key = _derive(eph.exchange(recip))
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, pt, _INFO)
    return {
        "alg": "X25519+HKDF-SHA256+AES-256-GCM",
        "eph_pub": _b64u(eph.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)),
        "nonce": _b64u(nonce),
        "ciphertext": _b64u(ct),
    }


def open_sealed(env: dict) -> bytes | None:
    """Decrypt an envelope sealed to OUR public key, using our private key."""
    p = _priv()
    if not (_HAS and p):
        return None
    try:
        eph_pub = X25519PublicKey.from_public_bytes(_b64u_dec(env["eph_pub"]))
        key = _derive(p.exchange(eph_pub))
        return AESGCM(key).decrypt(_b64u_dec(env["nonce"]), _b64u_dec(env["ciphertext"]), _INFO)
    except Exception:
        return None
