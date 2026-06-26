"""0n1x /revoke + /revoked — revocation & expiry for signed claims.

The council's unanimous point: a signature proves WHO signed, not that the claim
is still VALID. A verdict can go stale (a merchant turns bad), or be found wrong.
So 0n1x needs to say "this attestation is no longer good" — and anyone verifying
must be able to check it. This adds:

  GET /revoke?id=<verdict_id>&reason=<why>&from=<who>   -> revoke a claim (signed, durable)
  GET /revoked                                          -> the signed revocation list
  status(id) -> {revoked, reason, at}  (used by /verify so checks reflect revocation)

Expiry is advisory: tools stamp `valid_until` in the signed body; verifiers treat
a claim past valid_until as stale. Revocation is the hard, durable override.

Stdlib only. Underscore-prefixed -> not a tool.
"""
from __future__ import annotations

import json
import time

from . import _kv, _onyx_sign

_KV_KEY = "onyx:revoked"
_MEM: dict[str, dict] = {}


def _load() -> dict:
    if _kv.enabled():
        out: dict = {}
        for raw in _kv.lrange(_KV_KEY, 0, -1):
            try:
                r = json.loads(raw)
                out[r["id"]] = r
            except Exception:
                pass
        return out
    return dict(_MEM)


def revoke(verdict_id: str, reason: str = "", who: str = "onyx",
           base: str = "https://onyx-actions.onrender.com") -> dict:
    vid = (verdict_id or "").strip()[:160]
    if not vid:
        return _onyx_sign.attest({"revoke": "0n1x", "error": "id required"}, tool="onyx_revoke")
    rec = {"id": vid, "reason": (reason or "")[:300], "by": (who or "onyx")[:60],
           "at": int(time.time())}
    if _kv.enabled():
        _kv.rpush(_KV_KEY, json.dumps(rec))
    else:
        _MEM[vid] = rec
    base = (base or "").rstrip("/")
    return _onyx_sign.attest({"revoke": "0n1x", "revoked": True, "id": vid,
                              "reason": rec["reason"], "at": rec["at"],
                              "list": f"{base}/revoked",
                              "note": "Claim revoked. Verifiers checking this id will see it "
                                      "is no longer valid — a signature is not forever."},
                             tool="onyx_revoke")


def status(verdict_id: str) -> dict:
    r = _load().get((verdict_id or "").strip())
    if r:
        return {"revoked": True, "reason": r.get("reason", ""), "at": r.get("at")}
    return {"revoked": False}


def revoked_list(base: str = "https://onyx-actions.onrender.com") -> dict:
    recs = list(_load().values())
    recs.sort(key=lambda r: r.get("at", 0), reverse=True)
    return _onyx_sign.attest({"revoked": "0n1x", "count": len(recs), "entries": recs[:100],
                              "note": "The signed revocation list. Check an id here before "
                                      "trusting any 0n1x verdict that bears it."},
                             tool="onyx_revoked_list")
