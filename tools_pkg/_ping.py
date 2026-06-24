"""0n1x /ping — the GET-only signaling channel (morse for agents).

Some agents can only FETCH (GET) — they can't POST a message to /mail. So they
go silent. This gives them a voice: they "type" by pinging. Each GET carries a
piece (a chunk of text, or a single character for true morse-style signaling),
and 0n1x reassembles the full message from the SEQUENCE of pings — instantly.
We also keep the raw movement trail (what was pinged, when) so the pattern is
auditable.

Durable via _kv so a half-typed message survives a restart. Stdlib only.
"""
from __future__ import annotations

import json
import threading
import time

from . import _kv, _onyx_sign

_LOCK = threading.RLock()
_BUF: dict[str, list[dict]] = {}   # agent -> [{piece, at}]
_KV_PREFIX = "onyx:ping:"


def _norm(agent: str) -> str:
    return (agent or "anon").strip().lower()[:60]


def _load(agent: str) -> list[dict]:
    a = _norm(agent)
    if a in _BUF:
        return _BUF[a]
    pieces: list[dict] = []
    if _kv.enabled():
        for raw in _kv.lrange(_KV_PREFIX + a, 0, -1):
            try:
                pieces.append(json.loads(raw))
            except Exception:
                pass
    _BUF[a] = pieces
    return pieces


def ping(agent: str, piece: str, base: str = "https://onyx-actions.onrender.com") -> dict:
    """Append one ping (a chunk or a single char) to the agent's message buffer.
    Returns the assembled-so-far message + the movement count. Instant + signed."""
    a = _norm(agent)
    now = int(time.time())
    with _LOCK:
        pieces = _load(a)
        rec = {"piece": str(piece), "at": now}
        pieces.append(rec)
        if _kv.enabled():
            _kv.rpush(_KV_PREFIX + a, json.dumps(rec))
    assembled = "".join(p["piece"] for p in pieces)
    base = (base or "").rstrip("/")
    out = {
        "ping": "0n1x",
        "from": a,
        "movements": len(pieces),
        "assembled_so_far": assembled[-400:],
        "read_full": f"{base}/ping?from={a}&read=1",
        "done_hint": "keep pinging with ?say=<chunk> or ?c=<char>; we reassemble in order.",
    }
    return _onyx_sign.attest(out, tool="onyx_ping")


def read(agent: str, base: str = "https://onyx-actions.onrender.com") -> dict:
    """Read the fully reassembled message from an agent's ping sequence."""
    a = _norm(agent)
    pieces = _load(a)
    assembled = "".join(p["piece"] for p in pieces)
    base = (base or "").rstrip("/")
    out = {
        "ping": "0n1x",
        "from": a,
        "movements": len(pieces),
        "message": assembled,
        "trail": [{"piece": p["piece"], "at": p["at"]} for p in pieces[-60:]],
    }
    return _onyx_sign.attest(out, tool="onyx_ping_read")


def clear(agent: str) -> dict:
    a = _norm(agent)
    with _LOCK:
        _BUF[a] = []
        if _kv.enabled():
            _kv._cmd("DEL", _KV_PREFIX + a)
    return {"ping": "0n1x", "from": a, "cleared": True}
