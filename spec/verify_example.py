"""Independent OATP verifier — written from the spec, zero Onyx imports.

Proves §4.2: any third party can verify an envelope offline.
Run: py spec/verify_example.py
"""
import base64
import hashlib
import json
import urllib.request

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def jcs(obj) -> str:
    """RFC 8785 canonical JSON (sufficient subset: sorted keys, minimal separators)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def b64u_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def verify(envelope: dict, att_key: str = "onyx_attestation") -> dict:
    att = envelope.get(att_key) or envelope.get("attestation")
    if not isinstance(att, dict):
        return {"ok": False, "reason": "no_attestation"}
    body = {k: v for k, v in envelope.items() if k not in (att_key, "attestation")}
    canonical = jcs(body).encode("utf-8")
    if att.get("observed_hash") != "sha256:" + hashlib.sha256(canonical).hexdigest():
        return {"ok": False, "reason": "hash_mismatch"}
    try:
        pub = Ed25519PublicKey.from_public_bytes(b64u_decode(att["public_key"]))
        pub.verify(b64u_decode(att["sig"]), canonical)
        return {"ok": True, "kid": att.get("kid"), "alg": att.get("alg")}
    except Exception:
        return {"ok": False, "reason": "sig_verify_failed"}


if __name__ == "__main__":
    req = urllib.request.Request(
        "https://onyx-actions.onrender.com/connect",
        data=json.dumps({"message": "independent verifier test", "from": "third-party"}).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    env = json.loads(urllib.request.urlopen(req, timeout=60).read())
    print("live verify :", verify(env))
    env["reply"] = "TAMPERED"
    print("tamper test :", verify(env))
