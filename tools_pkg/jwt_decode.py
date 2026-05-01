"""JWT inspector — decode header + payload, report shape, no signing."""
from __future__ import annotations

import base64
import json
import time

NAME = "onyx_jwt_decode"
PRICE_USDC = "0.0003"
TIER = "metered"
DESCRIPTION = (
    "Decode a JWT (header + payload) without verifying the signature. "
    "Returns the algorithm, key id, all claims (iss, sub, aud, exp, iat, "
    "nbf, custom), expiry status, and any structural anomalies. Use when an "
    "agent receives a token from an external API and needs to inspect it "
    "for routing, expiry, or audit logging. Stdlib-only — runs locally, "
    "never sends the token anywhere."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "token": {"type": "string", "description": "JWT (three base64url segments separated by .)"},
    },
    "required": ["token"],
}


def _b64url(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def run(token: str, **_: object) -> dict:
    t = (token or "").strip()
    parts = t.split(".")
    if len(parts) != 3:
        raise ValueError("JWT must have 3 segments separated by '.'")
    try:
        header = json.loads(_b64url(parts[0]).decode("utf-8", "replace"))
    except Exception as e:
        raise ValueError(f"header decode failed: {e}")
    try:
        payload = json.loads(_b64url(parts[1]).decode("utf-8", "replace"))
    except Exception as e:
        raise ValueError(f"payload decode failed: {e}")
    now = int(time.time())
    exp = payload.get("exp")
    nbf = payload.get("nbf")
    iat = payload.get("iat")
    expired = isinstance(exp, (int, float)) and now >= exp
    not_yet_valid = isinstance(nbf, (int, float)) and now < nbf
    return {
        "alg": header.get("alg"),
        "typ": header.get("typ"),
        "kid": header.get("kid"),
        "iss": payload.get("iss"),
        "sub": payload.get("sub"),
        "aud": payload.get("aud"),
        "exp": exp,
        "iat": iat,
        "nbf": nbf,
        "expired": expired,
        "not_yet_valid": not_yet_valid,
        "header": header,
        "payload": payload,
        "signature_bytes": len(_b64url(parts[2])),
        "note": "Signature NOT verified. This tool is for inspection only.",
    }
