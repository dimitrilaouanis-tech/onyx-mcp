"""0n1x rate limiter — abuse caps so traffic can't tip the free dyno or bloat the store.

Shared across workers/restarts via Upstash (INCR + EXPIRE), with a graceful
in-memory fallback when KV is off. Generous by default — this is abuse protection,
not a paywall. Used on the resource-heavy endpoints (onboard mints a wallet each).

Stdlib only. Underscore-prefixed -> not a tool.
"""
from __future__ import annotations

import time

from . import _kv

_MEM: dict[str, tuple[int, int]] = {}   # key -> (count, window_start)


def allow(key: str, limit: int = 30, window_sec: int = 3600) -> tuple[bool, int]:
    """Return (allowed, remaining). Counts `key` hits within window_sec."""
    k = "onyx:rl:" + (key or "anon")
    if _kv.enabled():
        try:
            n = _kv._cmd("INCR", k)
            n = int(n if not isinstance(n, dict) else n.get("result", 1))
            if n == 1:
                _kv._cmd("EXPIRE", k, window_sec)
            return (n <= limit, max(0, limit - n))
        except Exception:
            pass  # fall through to memory
    now = int(time.time())
    cnt, start = _MEM.get(k, (0, now))
    if now - start >= window_sec:
        cnt, start = 0, now
    cnt += 1
    _MEM[k] = (cnt, start)
    return (cnt <= limit, max(0, limit - cnt))


def client_ip(x_forwarded_for: str = "") -> str:
    """Best-effort client IP from Render's X-Forwarded-For (first hop)."""
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return "unknown"
