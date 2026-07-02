"""Onyx Mailbox — per-citizen async inbox for the agentic web.

Any agent can DROP a message for another (addressed by name/callsign OR by
0x address / did:pkh); the recipient CHECKS its mail later. Open letterbox:
no auth to drop (like email), so DeepSeek/Nova/anyone can always leave a note.

Storage (two backends, same public API either way):
  - Postgres (DATABASE_URL / ONYX_DATABASE_URL set): one row per message in
    `onyx_mailbox_messages`, indexed by recipient — deliver() is a single
    targeted INSERT, check() a targeted indexed SELECT + UPDATE, not a
    whole-mailbox blob load/rewrite. This is the path that scales.
  - No DATABASE_URL: falls back to the ORIGINAL behavior unchanged — the
    whole mailbox dict via `_store` (Upstash KV blob, else local JSON file).

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
_BOX: dict = {}          # normalized recipient key -> list[message] (fallback only)
_loaded = False

# =========================================================================
# Postgres backend — targeted indexed ops against one row per message.
# =========================================================================

_DB_URL = os.environ.get("ONYX_DATABASE_URL", "") or os.environ.get("DATABASE_URL", "")
_TABLE = "onyx_mailbox_messages"
_db_ready = False


def _db():
    """Live psycopg connection, or None if DATABASE_URL isn't set / Postgres
    isn't reachable. Lazily creates `onyx_mailbox_messages` (idempotent) on
    first use. Best-effort: never raises into the caller."""
    if not _DB_URL:
        return None
    try:
        import psycopg
        conn = psycopg.connect(_DB_URL, autocommit=True)
    except Exception:
        return None
    global _db_ready
    if not _db_ready:
        try:
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {_TABLE} (
                    id TEXT PRIMARY KEY,
                    recipient TEXT NOT NULL,
                    sender TEXT,
                    to_raw TEXT,
                    message TEXT,
                    specs JSONB,
                    created_at BIGINT NOT NULL,
                    read BOOLEAN NOT NULL DEFAULT FALSE
                )""")
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{_TABLE}_recipient ON {_TABLE}(recipient, created_at)")
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{_TABLE}_unread ON {_TABLE}(recipient) WHERE read = FALSE")
            _db_ready = True
        except Exception:
            pass
    return conn


def ensure_schema() -> dict:
    """Idempotent bootstrap for `onyx_mailbox_messages` — safe to call at app
    startup on every boot. No-op (ok=False) when Postgres isn't configured."""
    conn = _db()
    ok = conn is not None
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
    return {"ok": ok, "table": _TABLE}


def _row_to_msg(row) -> dict:
    (id_, recipient, sender, to_raw, message, specs, created_at, read) = row
    return {"id": id_, "from": sender, "to": recipient, "to_raw": to_raw,
            "message": message, "specs": specs or {}, "t": int(created_at), "read": bool(read)}


# =========================================================================
# Fallback backend — whole-mailbox blob via _store (Upstash / local file).
# =========================================================================

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
    sees notes left while it was down. Only used by the fallback path (no
    DATABASE_URL): Upstash blob when configured, local JSON otherwise."""
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

    msg_id = "msg_" + uuid.uuid4().hex[:12]
    frm_v = (frm or "anonymous").strip()[:80]
    to_raw = (to or "").strip()[:80]
    msg_text = (message or "")[:4000]
    specs_v = specs or {}
    now = int(time.time())

    conn = _db()
    if conn is not None:
        try:
            conn.execute(
                f"INSERT INTO {_TABLE} (id, recipient, sender, to_raw, message, specs, created_at, read) "
                "VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,FALSE)",
                (msg_id, to_k, frm_v, to_raw, msg_text, json.dumps(specs_v), now))
            # Bound each box to the newest 500 (mirrors the old per-box cap) —
            # a targeted indexed delete, not a whole-blob rewrite.
            conn.execute(
                f"DELETE FROM {_TABLE} WHERE recipient=%s AND id NOT IN "
                f"(SELECT id FROM {_TABLE} WHERE recipient=%s ORDER BY created_at DESC LIMIT 500)",
                (to_k, to_k))
            size = conn.execute(
                f"SELECT count(*) FROM {_TABLE} WHERE recipient=%s", (to_k,)).fetchone()[0]
            conn.close()
            return {"ok": True, "delivered": True, "id": msg_id, "to": to_k,
                    "from": frm_v, "mailbox_size": int(size)}
        except Exception:
            try:
                conn.close()
            except Exception:
                pass

    # ---- fallback: original whole-blob behavior, unchanged ----
    with _LOCK:
        _load()
        msg = {
            "id": msg_id, "from": frm_v, "to": to_k, "to_raw": to_raw,
            "message": msg_text, "specs": specs_v, "t": now, "read": False,
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

    conn = _db()
    if conn is not None:
        try:
            unread = conn.execute(
                f"SELECT count(*) FROM {_TABLE} WHERE recipient=%s AND read=FALSE", (k,)
            ).fetchone()[0]
            if unread_only:
                rows = conn.execute(
                    f"SELECT id, recipient, sender, to_raw, message, specs, created_at, read "
                    f"FROM {_TABLE} WHERE recipient=%s AND read=FALSE "
                    "ORDER BY created_at DESC LIMIT %s",
                    (k, limit)).fetchall()
            else:
                rows = conn.execute(
                    f"SELECT id, recipient, sender, to_raw, message, specs, created_at, read "
                    f"FROM {_TABLE} WHERE recipient=%s ORDER BY created_at DESC LIMIT %s",
                    (k, limit)).fetchall()
            # DESC->reversed gives oldest-first, matching the original box[-limit:] order.
            msgs = [_row_to_msg(r) for r in reversed(rows)]
            if mark_read and msgs:
                ids = [m["id"] for m in msgs]
                conn.execute(f"UPDATE {_TABLE} SET read=TRUE WHERE id = ANY(%s)", (ids,))
            conn.close()
            return {"ok": True, "agent": k, "count": len(msgs),
                    "unread_before": int(unread), "messages": msgs}
        except Exception:
            try:
                conn.close()
            except Exception:
                pass

    # ---- fallback: original whole-blob behavior, unchanged ----
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
    conn = _db()
    if conn is not None:
        try:
            boxes = conn.execute(f"SELECT count(DISTINCT recipient) FROM {_TABLE}").fetchone()[0]
            total = conn.execute(f"SELECT count(*) FROM {_TABLE}").fetchone()[0]
            conn.close()
            return {"boxes": int(boxes), "total_messages": int(total)}
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
    with _LOCK:
        _load()
        return {"boxes": len(_BOX),
                "total_messages": sum(len(v) for v in _BOX.values())}
