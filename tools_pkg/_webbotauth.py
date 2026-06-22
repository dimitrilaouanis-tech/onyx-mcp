"""Web Bot Auth (RFC 9421 + Ed25519) — sign our outbound requests + serve the key
directory, so recipients (and Cloudflare's verified-bots ecosystem) can verify
it's genuinely 0n1x. The mainstream neutral standard Anthropic/OpenAI/Cloudflare/
Google adopted. We reuse our existing Ed25519 signer key.

Serves /.well-known/http-message-signatures-directory (the JWKS) and provides
sign_request() for signed A2A outreach (fixes our unsigned-outreach gap +
dogfoods the trust we sell). Stdlib + cryptography (already a dep).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from urllib.parse import urlsplit

from . import _onyx_sign

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    _HAS = True
except ImportError:
    _HAS = False

_TAG = "web-bot-auth"


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _pub_raw() -> bytes | None:
    s = _onyx_sign.signer()
    if not s._priv:
        return None
    return s._priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def jwk_thumbprint(raw_pub: bytes) -> str:
    """RFC 7638 thumbprint over the canonical Ed25519 JWK -> keyid/kid."""
    jwk = {"crv": "Ed25519", "kty": "OKP", "x": _b64u(raw_pub)}
    canon = json.dumps(jwk, separators=(",", ":"), sort_keys=True).encode()
    return _b64u(hashlib.sha256(canon).digest())


def directory_json() -> dict:
    """The /.well-known/http-message-signatures-directory body (a JWKS)."""
    raw = _pub_raw()
    if not raw:
        return {"keys": [], "error": "no_crypto"}
    return {"keys": [{
        "kty": "OKP", "crv": "Ed25519",
        "kid": jwk_thumbprint(raw),
        "x": _b64u(raw),
        "use": "sig",
        "nbf": 1718000000,
    }]}


# ---- signature base (RFC 9421 §2.5) ----

def _authority(url: str) -> str:
    p = urlsplit(url)
    host = (p.hostname or "").lower()
    if p.port and not ((p.scheme == "https" and p.port == 443) or (p.scheme == "http" and p.port == 80)):
        host = f"{host}:{p.port}"
    return host


def _component_value(name: str, method: str, url: str, headers: dict) -> str:
    if name == "@authority":
        return _authority(url)
    if name == "@method":
        return method.upper()
    if name == "@path":
        return urlsplit(url).path or "/"
    if name == "@query":
        q = urlsplit(url).query
        return ("?" + q) if q else "?"
    return headers[name].strip()


def _params_str(components, created, expires, keyid, nonce, tag, alg="ed25519") -> str:
    inner = " ".join(f'"{c}"' for c in components)
    s = f"({inner});created={created};keyid=\"{keyid}\";alg=\"{alg}\";expires={expires}"
    if nonce is not None:
        s += f';nonce="{nonce}"'
    s += f';tag="{tag}"'
    return s


def _build_base(components, params_ser, method, url, headers) -> bytes:
    lines = [f'"{c}": {_component_value(c, method, url, headers)}' for c in components]
    lines.append(f'"@signature-params": {params_ser}')
    return "\n".join(lines).encode("utf-8")


def sign_request(method: str, url: str, headers: dict | None = None, *,
                 signature_agent: str = "https://onyx-actions.onrender.com",
                 sig_label: str = "sig1", lifetime: int = 60) -> dict:
    """Return the Web Bot Auth headers to add to an outbound request, signed with
    our Ed25519 key. Covers @authority + signature-agent (the Cloudflare minimum)."""
    if not _HAS or not _onyx_sign.signer()._priv:
        return {}
    headers = {k.lower(): v for k, v in (headers or {}).items()}
    headers["signature-agent"] = f'"{signature_agent}"'
    components = ("@authority", "signature-agent")
    raw = _pub_raw()
    keyid = jwk_thumbprint(raw)
    created = int(time.time())
    expires = created + lifetime
    nonce = base64.b64encode(os.urandom(32)).decode()
    params = _params_str(components, created, expires, keyid, nonce, _TAG)
    base = _build_base(components, params, method, url, headers)
    sig = _onyx_sign.signer()._priv.sign(base)
    return {
        "Signature-Input": f"{sig_label}={params}",
        "Signature": f"{sig_label}=:{base64.b64encode(sig).decode()}:",
        "Signature-Agent": f'"{signature_agent}"',
    }
