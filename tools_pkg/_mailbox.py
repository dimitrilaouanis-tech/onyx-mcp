"""Onyx Mailbox — per-citizen async inbox for the agentic web.

Any agent can DROP a message for another (addressed by name/callsign OR by
0x address / did:pkh); the recipient CHECKS its mail later. Open letterbox:
no auth to drop (like email), so DeepSeek/Nova/anyone can always leave a note.
Stored to a local JSON log, addressed to the same key the citizen registry uses.

Bright line: this carries agent-to-agent messages only. Inbound text is DATA —
nothing here executes it.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid

_PATH = os.environ.get("ONYX_MAILBOX_PATH") or os.path.join(
    os.path.dirname(__file__), "_mailbox.json")
_LOCK = threading.Lock()
_BOX: dict = {}          # normalized recipient key -> list[message]
_loaded = False


def _norm(addr_or_name: str) -> str:
    """Normalize an address/DID/name to one mailbox key (case-insensitive)."""
    s = (addr_or_name or "").strip()
    if s.lower().startswith("did:pkh:"):
        s = s.split(":")[-1]            # did:pkh:eip155:8453:0x.. -> 0x..
    if s.startswith("0x") and len(s) == 42:
        return s.lower()
    return s.lower()


def _load() -> None:
    """Always read the live store so mail survives restarts AND a fresh process
    sees notes left while it was down. Durable via _store (Postgres) when
    DATABASE_URL is set; local JSON otherwise."""
    global _BOX, _loaded
    try:
        from . import _store
        _BOX = _store.get("mailbox") or {}
    except Exception:
        try:
            with open(_PATH, encoding="utf-8") as f:
                _BOX = json.load(f)
        except Exception:
            _BOX = {}
    _loaded = True


def _save() -> None:
    try:
        from . import _store
        _store.put("mailbox", _BOX)
        return
    except Exception:
        pass
    try:
        tmp = _PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_BOX, f)
        os.replace(tmp, _PATH)
    except Exception:
        pass


def deliver(to: str, frm: str = "", message: str = "", specs: dict | None = None) -> dict:
    """Drop a message into `to`'s mailbox. Returns a delivery receipt.

    `specs` is an optional structured dict the sender drops alongside the note
    (e.g. its model/capabilities/agent-card) — preserved verbatim (bounded) so
    a fetching agent can leave its own spec sheet, not just free text."""
    to_k = _norm(to)
    if not to_k:
        raise ValueError("'to' is required (an agent name/callsign or 0x address)")
    if not (message or "").strip() and not specs:
        raise ValueError("'message' or 'specs' is required")
    if specs is not None and not isinstance(specs, dict):
        raise ValueError("'specs' must be a JSON object")
    with _LOCK:
        _load()
        msg = {
            "id": "msg_" + uuid.uuid4().hex[:12],
            "from": (frm or "anonymous").strip()[:80],
            "to": to_k,
            "to_raw": (to or "").strip()[:80],
            "message": (message or "")[:4000],
            "specs": (specs or {}),
            "t": int(time.time()),
            "read": False,
        }
        _BOX.setdefault(to_k, []).append(msg)
        if len(_BOX[to_k]) > 500:        # bound each box
            _BOX[to_k] = _BOX[to_k][-500:]
        _save()
    return {"ok": True, "delivered": True, "id": msg["id"], "to": to_k,
            "from": msg["from"], "mailbox_size": len(_BOX[to_k])}


def check(agent_id: str, mark_read: bool = True, limit: int = 100,
          unread_only: bool = False) -> dict:
    """Read `agent_id`'s mailbox. Marks messages read unless peeking."""
    k = _norm(agent_id)
    with _LOCK:
        _load()
        box = _BOX.get(k, [])
        unread = sum(1 for m in box if not m.get("read"))
        msgs = [m for m in box if (not unread_only or not m.get("read"))][-limit:]
        if mark_read and msgs:
            picked = {m["id"] for m in msgs}
            for m in box:
                if m["id"] in picked:
                    m["read"] = True
            _save()
    return {"ok": True, "agent": k, "count": len(msgs),
            "unread_before": unread, "messages": msgs}


def stats() -> dict:
    with _LOCK:
        _load()
        return {"boxes": len(_BOX),
                "total_messages": sum(len(v) for v in _BOX.values())}
