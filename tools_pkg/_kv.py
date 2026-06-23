"""Durable KV via Upstash Redis REST — makes the moat (the signed observation
log + ledger) PERSIST across Render deploys/spin-downs.

Render's host wipes local files on every deploy. Our entire moat is the
COMPOUNDING signed track record — so it must live somewhere durable. Upstash
Redis is serverless + free + a plain REST API (no connection pooling on
ephemeral dynos). Set two env vars in the Render dashboard:

    UPSTASH_REDIS_REST_URL    (e.g. https://xxx.upstash.io)
    UPSTASH_REDIS_REST_TOKEN

If they're absent, enabled() is False and everything falls back to the local
file behavior — nothing breaks. Stdlib only (urllib).
"""
from __future__ import annotations

import json
import os
import urllib.request


def _url() -> str:
    return os.environ.get("UPSTASH_REDIS_REST_URL", "").rstrip("/")


def _token() -> str:
    return os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")


def enabled() -> bool:
    return bool(_url() and _token())


def _cmd(*args, timeout: float = 15):
    """Run one Redis command via the Upstash REST API. Returns the 'result'."""
    if not enabled():
        return None
    req = urllib.request.Request(
        _url(),
        data=json.dumps([str(a) for a in args]).encode("utf-8"),
        headers={"Authorization": "Bearer " + _token(),
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return (json.loads(r.read() or b"{}") or {}).get("result")


def rpush(key: str, value: str) -> int | None:
    try:
        return _cmd("RPUSH", key, value)
    except Exception:
        return None


def lrange(key: str, start: int = 0, stop: int = -1) -> list:
    try:
        return _cmd("LRANGE", key, start, stop) or []
    except Exception:
        return []


def llen(key: str) -> int:
    try:
        return int(_cmd("LLEN", key) or 0)
    except Exception:
        return 0


def setk(key: str, value: str) -> None:
    try:
        _cmd("SET", key, value)
    except Exception:
        pass


def getk(key: str):
    try:
        return _cmd("GET", key)
    except Exception:
        return None
