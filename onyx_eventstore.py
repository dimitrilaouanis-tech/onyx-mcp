"""onyx_eventstore.py — the append-only event store. The durability brick for 100k.

The panel's write path, in code: every ledger operation is ONE append (a single atomic INSERT),
carrying an idempotency key so retries can't double-apply. Events are the source of truth; all
state (balances, credits, roots) is a DERIVED VIEW you rebuild by replaying them — exactly our
Point-of-Truth principle. Events are hash-chained (each commits to the previous), so the log is
tamper-evident and re-verifiable by anyone.

In-memory today. The moment DATABASE_URL is set (the sister session's Postgres layer), the SAME
append() becomes one INSERT into event_log(idempotency_key, stream_id, seq, event_type, payload,
prev_hash, at) — signatures unchanged, no logic rewrite. That is the whole 100k migration.
"""
import hashlib
import json
import time


def _hash(obj: dict) -> str:
    core = {k: obj[k] for k in ("stream", "seq", "type", "payload", "prev")}
    return "0x" + hashlib.sha256(json.dumps(core, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class EventStore:
    def __init__(self):
        self.events: list[dict] = []            # append-only; -> Postgres event_log when DATABASE_URL set
        self._seq: dict[str, int] = {}          # per-stream sequence (aggregate versioning)
        self._seen: dict[str, dict] = {}        # idempotency_key -> event (retry-safe dedup)
        # PER-STREAM hash-chains — NOT one global tip. Writes to different agents/streams are
        # independent (no global serialization point), so 100k agents transact concurrently
        # without contending. In Postgres this is unique(stream, seq) + per-stream prev_hash;
        # concurrent appends to the same stream lose the race and retry (optimistic concurrency).
        self._tip: dict[str, str] = {}          # stream -> last event hash

    def append(self, stream: str, etype: str, payload: dict,
               idempotency_key: str | None = None, at: int | None = None) -> dict:
        # idempotency: a retry with the same key returns the original event, never re-applies
        if idempotency_key and idempotency_key in self._seen:
            return {**self._seen[idempotency_key], "idempotent_replay": True}
        seq = self._seq.get(stream, 0) + 1                 # per-aggregate seq (optimistic-concurrency key)
        prev = self._tip.get(stream, "0x" + "0" * 64)      # chain within THIS stream only — no global lock
        ev = {"stream": stream, "seq": seq, "type": etype, "payload": payload,
              "prev": prev, "idem": idempotency_key, "at": at if at is not None else 0}
        ev["hash"] = _hash(ev)
        self._seq[stream] = seq
        self._tip[stream] = ev["hash"]
        self.events.append(ev)                             # <-- one INSERT into event_log at 100k
        if idempotency_key:
            self._seen[idempotency_key] = ev
        return ev

    def replay(self, stream: str | None = None):
        """The derived-state rebuild: apply these in order to reconstruct any view."""
        return [e for e in self.events if stream is None or e["stream"] == stream]

    def verify_chain(self) -> dict:
        """Anyone can re-verify the log: each PER-STREAM chain links + seq increases."""
        stream_prev: dict[str, str] = {}
        last_seq: dict[str, int] = {}
        for e in self.events:
            s = e["stream"]
            if e["prev"] != stream_prev.get(s, "0x" + "0" * 64):
                return {"ok": False, "broke": "chain", "stream": s, "seq": e["seq"]}
            if e["seq"] != last_seq.get(s, 0) + 1:
                return {"ok": False, "broke": "stream_seq", "stream": s}
            if e["hash"] != _hash(e):
                return {"ok": False, "broke": "event_hash", "seq": e["seq"]}
            stream_prev[s] = e["hash"]
            last_seq[s] = e["seq"]
        return {"ok": True, "events": len(self.events), "streams": len(last_seq)}
