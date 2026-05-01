"""Compute md5/sha1/sha256/sha512 of any input. Stdlib hashlib."""
from __future__ import annotations

import base64
import hashlib

NAME = "onyx_hash_compute"
PRICE_USDC = "0.0003"
TIER = "metered"
DESCRIPTION = (
    "Compute md5, sha1, sha256, sha512, and sha3-256 of any text or "
    "base64-encoded bytes. Returns each digest as both hex and base64. Use "
    "for content-addressed lookups, dedupe keys, signature verification "
    "support, or fingerprinting. Stdlib-only — runs locally, never logs "
    "input. <2ms."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string", "description": "UTF-8 string to hash"},
        "b64": {"type": "string", "description": "Or: base64-encoded bytes"},
    },
}


def run(text: str | None = None, b64: str | None = None, **_: object) -> dict:
    if text is not None:
        data = text.encode("utf-8")
    elif b64:
        data = base64.b64decode(b64)
    else:
        raise ValueError("Provide text or b64")
    out = {"length": len(data)}
    for algo in ("md5", "sha1", "sha256", "sha512", "sha3_256"):
        h = hashlib.new(algo, data)
        digest = h.digest()
        out[algo] = {"hex": digest.hex(),
                     "b64": base64.b64encode(digest).decode("ascii")}
    return out
