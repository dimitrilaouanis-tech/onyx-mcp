"""Independent OATP verifier — written from the spec, zero Onyx imports.

Proves §4.2: any third party can verify an envelope offline.
Run: py spec/verify_example.py
"""
import base64
import hashlib
import json
import urllib.request

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def _num(n) -> str:
    """RFC 8785 §3.2.2.3 number serialization. Integral floats -> integer form
    (1.0 -> "1", 0.0 -> "0"); this is what makes third-party verification of
    numeric payloads succeed. (json.dumps gets this WRONG: it emits "1.0".)"""
    if isinstance(n, bool):
        return "true" if n else "false"
    if isinstance(n, int):
        return str(n)
    if n != n or n in (float("inf"), float("-inf")):
        raise ValueError("NaN/Infinity not permitted in JCS")
    return str(int(n)) if float(n).is_integer() else repr(n)


def jcs(obj) -> str:
    """RFC 8785 canonical JSON: sorted keys, minimal separators, spec-correct
    numbers (the float-as-integer rule json.dumps omits)."""
    if obj is None:
        return "null"
    if isinstance(obj, bool):
        return "true" if obj else "false"
    if isinstance(obj, str):
        return json.dumps(obj, ensure_ascii=False)
    if isinstance(obj, (int, float)):
        return _num(obj)
    if isinstance(obj, dict):
        return "{" + ",".join(
            json.dumps(str(k), ensure_ascii=False) + ":" + jcs(v)
            for k, v in sorted(obj.items(), key=lambda kv: str(kv[0]))
        ) + "}"
    if isinstance(obj, (list, tuple)):
        return "[" + ",".join(jcs(v) for v in obj) + "]"
    raise TypeError("not JCS-serializable")


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
