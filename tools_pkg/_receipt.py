"""0n1x action receipts — THE BLACK BOX for AI agents. The core primitive.

An agent (or its SDK) emits a receipt for every consequential action:
  who did WHAT, were they AUTHORIZED, what was the OUTCOME — when.
0n1x signs it (un-fakeable), stores it durably, and assembles an agent's receipts
into a portable CAPSULE that travels across platforms and is independently
verifiable. This is the accountability layer enterprises need before they dare run
agents in production — and the thing no agent or platform can fake about itself.

Un-fakeable: Ed25519-signed, receipt_id = hash of the canonical body (tamper -> mismatch).
Portable: the capsule is a single signed JSON an agent/enterprise carries anywhere.
Revocable/expiring: each receipt carries expires_at; revocation via _revocation.

Stdlib only. Underscore-prefixed -> not a tool.
"""
from __future__ import annotations

import hashlib
import json
import time

from . import _kv, _onyx_sign

_KV_PREFIX = "onyx:receipts:"
_MEM: dict[str, list] = {}
_DEFAULT_TTL = 86400  # receipts are "current" for 24h unless told otherwise


def _norm(a: str) -> str:
    return (a or "anon").strip().lower()[:60]


def _load(agent: str) -> list:
    a = _norm(agent)
    if _kv.enabled():
        out = []
        for raw in _kv.lrange(_KV_PREFIX + a, 0, -1):
            try:
                out.append(json.loads(raw))
            except Exception:
                pass
        return out
    return list(_MEM.get(a, []))


def record(agent: str, action: str, authorized=None, outcome: str = "",
           evidence: str = "", ttl: int = _DEFAULT_TTL,
           base: str = "https://onyx-actions.onrender.com") -> dict:
    """Emit a signed action receipt — the un-fakeable record of what an agent did."""
    a = _norm(agent)
    now = int(time.time())
    auth = None if authorized is None else str(authorized).lower() in ("1", "true", "yes", "authorized")
    body = {
        "receipt": "0n1x-action",
        "agent": a,
        "action": (action or "")[:400],
        "authorized": auth,
        "outcome": (outcome or "")[:200],
        "evidence": (evidence or "")[:300],
        "at": now,
        "expires_at": now + int(ttl or _DEFAULT_TTL),
    }
    body["receipt_id"] = "rcpt:" + hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:24]
    if _kv.enabled():
        _kv.rpush(_KV_PREFIX + a, json.dumps(body))
    else:
        _MEM.setdefault(a, []).append(body)
    base = (base or "").rstrip("/")
    signed = _onyx_sign.attest(body, tool="onyx_receipt")
    signed["capsule"] = f"{base}/capsule/{a}"
    signed["verify"] = f"{base}/verify"
    return signed


def capsule(agent: str, base: str = "https://onyx-actions.onrender.com") -> dict:
    """The portable, verifiable capsule — an agent's whole accountable record + memory,
    one signed JSON it carries across platforms. The 'verifiable conversation capsule'."""
    a = _norm(agent)
    receipts = _load(a)
    now = int(time.time())
    card = {}
    try:
        from . import _cardpatch
        card = _cardpatch._load(a)
    except Exception:
        pass
    live = [r for r in receipts if r.get("expires_at", 0) >= now]
    out = {
        "capsule": "0n1x",
        "agent": a,
        "issued_at": now,
        "memory": {"summary": card.get("summary", ""), "knows": card.get("knows", ""),
                   "keywords": card.get("keywords", [])},
        "receipts_total": len(receipts),
        "receipts_live": len(live),
        "receipts": receipts[-50:],
        "portable": "This single signed JSON is the agent's accountable record + memory. "
                    "Carry it across platforms; anyone can verify it at /verify without "
                    "trusting the platform that produced it.",
        "spec": base.rstrip("/") + "/.well-known/onyx-attestation/v1",
    }
    return _onyx_sign.attest(out, tool="onyx_capsule")
