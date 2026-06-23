"""Onyx Observation Log — the signed, append-only dataset that IS the product.

The dashboard was never the asset. THIS is: a continuously growing,
cryptographically signed log of individual observations about the agent
economy — one signature per FACT, not one signature per page. Think
Certificate Transparency, but for autonomous commerce: every merchant we
verify, every new agent endpoint we see, every price drift we witness becomes
a single Ed25519-signed, content-addressed record that anyone can query,
replay, and independently verify forever.

Moat = coverage + history + reputation, not the signature itself. The signature
just makes the history un-forgeable.

Each record:
  {
    "obs_id": "obs_<sha256-prefix>",      # content address of the signed body
    "kind": "merchant_verified" | "endpoint_indexed" | "new_endpoint" |
            "price_drift" | "tombstone" | ...,
    "subject": {"type": "merchant"|"endpoint"|"agent", "id": "<domain/host/id>"},
    "observed": { ...the fact... },
    "observed_at": <unix>,
    "source": "x402-cdp-discovery",
    "onyx_attestation": { ...Ed25519+JCS over everything above... }
  }

Backend is an append-only JSONL file + in-memory indexes. On Render the disk is
ephemeral across deploys, so the file is a warm cache, not the system of record;
swap `_append`/`_load` for a durable KV/Postgres without touching callers. The
log is rebuildable from the firehose, so loss is recoverable, not fatal.

Stdlib-only. Underscore-prefixed -> not a tool.
"""
from __future__ import annotations

import json
import threading
import time
from hashlib import sha256
from pathlib import Path

from . import _kv, _onyx_sign

_LOG_PATH = Path(__file__).with_name("_observation_log.jsonl")
_KV_KEY = "onyx:obslog"   # durable Upstash list — survives Render wipes
_LOCK = threading.RLock()

# In-memory state, lazily loaded from the JSONL on first use.
_STATE: dict = {
    "loaded": False,
    "records": [],                 # full ordered list (append-only)
    "by_subject": {},              # "merchant:foo.com" -> [record, ...]
    "by_kind": {},                 # kind -> [record, ...]
    "by_id": {},                   # obs_id -> record
    "fingerprints": set(),         # dedupe: only append a CHANGED/new fact
    "last_value": {},              # subject_key -> last observed scalar (drift)
}


def _subject_key(subject: dict) -> str:
    return f"{subject.get('type','?')}:{subject.get('id','?')}"


def _fingerprint(kind: str, subject: dict, observed: dict) -> str:
    """A stable hash of WHAT was observed, ignoring timestamp. Lets a 10-min
    poll re-witness the same fact without bloating the log — we append only
    when something is new or has changed."""
    blob = _onyx_sign._jcs({"k": kind, "s": _subject_key(subject), "o": observed})
    return sha256(blob.encode("utf-8")).hexdigest()


def _load() -> None:
    if _STATE["loaded"]:
        return
    with _LOCK:
        if _STATE["loaded"]:
            return
        if _LOG_PATH.exists():
            for line in _LOG_PATH.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                _index(rec, persist=False)
        # DURABLE: also load from Upstash (survives Render wipes). Deduped by
        # _obs_id in _index, so loading from both file + KV is safe.
        if _kv.enabled():
            for raw in _kv.lrange(_KV_KEY, 0, -1):
                try:
                    _index(json.loads(raw), persist=False)
                except Exception:
                    continue
        _STATE["loaded"] = True


def _index(rec: dict, *, persist: bool) -> None:
    """Insert a record into the in-memory indexes (and optionally the file/KV)."""
    oid = rec.get("_obs_id")
    if oid and oid in _STATE["by_id"]:
        return  # already indexed (dedupe across file + KV sources)
    _STATE["records"].append(rec)
    _STATE["by_id"][rec["_obs_id"]] = rec
    sk = _subject_key(rec.get("subject", {}))
    _STATE["by_subject"].setdefault(sk, []).append(rec)
    _STATE["by_kind"].setdefault(rec.get("kind", "?"), []).append(rec)
    fp = rec.get("_fp")
    if fp:
        _STATE["fingerprints"].add(fp)
    if persist:
        blob = json.dumps(rec, ensure_ascii=False)
        try:
            with _LOG_PATH.open("a", encoding="utf-8") as f:
                f.write(blob + "\n")
        except Exception:
            pass  # local file is a warm cache, not the source of truth
        if _kv.enabled():
            _kv.rpush(_KV_KEY, blob)  # DURABLE source of truth — survives deploys


def record(kind: str, subject: dict, observed: dict,
           source: str = "x402-cdp-discovery", at: int | None = None) -> dict | None:
    """Sign ONE observation and append it. Returns the signed record, or None if
    this exact fact was already witnessed (dedupe). Thread-safe."""
    _load()
    now = int(at if at is not None else time.time())
    fp = _fingerprint(kind, subject, observed)
    with _LOCK:
        if fp in _STATE["fingerprints"]:
            return None  # already on the log, unchanged
        body = {
            "kind": kind,
            "subject": subject,
            "observed": observed,
            "observed_at": now,
            "source": source,
        }
        # The signed unit is EXACTLY `body` + its attestation. obs_id and _fp are
        # internal siblings (underscore-prefixed) so they stay OUT of the signed
        # bytes — otherwise verify() would recompute a different hash.
        signed = _onyx_sign.attest(dict(body), tool="onyx_observation")
        att = signed.get("onyx_attestation", {})
        digest = (att.get("observed_hash") or "").replace("sha256:", "")
        signed["_obs_id"] = "obs_" + (digest[:24] if digest else sha256(
            _onyx_sign._jcs(body).encode()).hexdigest()[:24])
        signed["_fp"] = fp
        _index(signed, persist=True)
        return signed


def record_drift(subject: dict, field: str, value, source: str = "x402-cdp-discovery",
                 at: int | None = None) -> dict | None:
    """Record a scalar observation, emitting a `price_drift`/change record only
    when the value moved since last time. First sighting is a plain observation.
    """
    _load()
    sk = _subject_key(subject) + "#" + field
    prev = _STATE["last_value"].get(sk)
    _STATE["last_value"][sk] = value
    observed = {"field": field, "value": value}
    if prev is not None and prev != value:
        observed = {"field": field, "value": value, "previous": prev,
                    "delta": _safe_delta(prev, value)}
        return record("price_drift", subject, observed, source=source, at=at)
    return record("observed", subject, observed, source=source, at=at)


def _safe_delta(a, b):
    try:
        return round(float(b) - float(a), 6)
    except Exception:
        return None


# ---- query surface (the machine-consumable product) ----------------------

def _public(rec: dict) -> dict:
    """The clean, independently-verifiable signed observation: exactly the bytes
    that were signed (internal underscore keys stripped)."""
    return {k: v for k, v in rec.items() if not k.startswith("_")}


def _wrap(rec: dict) -> dict:
    """Query item: obs_id is metadata ABOUT the observation, kept OUTSIDE the
    signed `observation` so the latter still verifies byte-for-byte."""
    return {"obs_id": rec.get("_obs_id"), "observation": _public(rec)}


def get(obs_id: str) -> dict | None:
    _load()
    rec = _STATE["by_id"].get(obs_id)
    return _wrap(rec) if rec else None


def proof(obs_id: str) -> dict:
    """Return the observation PLUS a fresh self-verification result, so a caller
    gets the signed fact and the proof it's genuinely Onyx-signed in one shot."""
    _load()
    rec = _STATE["by_id"].get(obs_id)
    if not rec:
        return {"found": False, "obs_id": obs_id}
    pub = _public(rec)
    return {
        "found": True,
        "obs_id": rec.get("_obs_id"),
        "observation": pub,
        "verification": _onyx_sign.is_onyx_signed(pub),
        "verify_anywhere": "POST this observation to /verify, or run the 45-line "
                           "spec/verify_example.py — no Onyx call needed.",
    }


def subject(stype: str, sid: str, limit: int = 100) -> dict:
    """Full signed history for one merchant/endpoint/agent."""
    _load()
    sk = f"{stype}:{sid}"
    recs = _STATE["by_subject"].get(sk, [])
    items = [_wrap(r) for r in recs[-limit:]][::-1]
    return {
        "subject": {"type": stype, "id": sid},
        "observations": items,
        "count": len(recs),
        "first_seen": recs[0]["observed_at"] if recs else None,
        "last_seen": recs[-1]["observed_at"] if recs else None,
    }


def history(kind: str = "", since: int = 0, limit: int = 200) -> dict:
    """The append-only log, newest first, optionally filtered by kind/time."""
    _load()
    src = _STATE["by_kind"].get(kind, []) if kind else _STATE["records"]
    items = [r for r in src if r.get("observed_at", 0) >= since]
    out = [_wrap(r) for r in items[-limit:]][::-1]
    return {
        "kind": kind or "all",
        "since": since,
        "returned": len(out),
        "total_on_log": len(_STATE["records"]),
        "observations": out,
    }


def timeline(limit: int = 50) -> dict:
    """A compact, human/agent-skimmable stream of the most recent events."""
    _load()
    recs = _STATE["records"][-limit:][::-1]
    line = []
    for r in recs:
        line.append({
            "at": r.get("observed_at"),
            "kind": r.get("kind"),
            "subject": r.get("subject", {}).get("id"),
            "obs_id": r.get("_obs_id"),
            "summary": _summarize(r),
        })
    return {"timeline": line, "total_on_log": len(_STATE["records"])}


def _summarize(r: dict) -> str:
    k = r.get("kind", "")
    o = r.get("observed", {})
    sid = r.get("subject", {}).get("id", "?")
    if k == "merchant_verified":
        return f"merchant {sid} verified ({o.get('status','?')})"
    if k == "new_endpoint":
        return f"new endpoint {sid} appeared on x402"
    if k == "endpoint_indexed":
        return f"{sid}: {o.get('calls_30d',0)} calls/30d"
    if k == "price_drift":
        return f"{sid} {o.get('field')} {o.get('previous')}→{o.get('value')}"
    if k == "tombstone":
        return f"{sid} went dark (tombstoned)"
    return f"{k} on {sid}"


def stats() -> dict:
    _load()
    kinds = {k: len(v) for k, v in _STATE["by_kind"].items()}
    subjects = len(_STATE["by_subject"])
    recs = _STATE["records"]
    return {
        "total_observations": len(recs),
        "distinct_subjects": subjects,
        "by_kind": kinds,
        "first_observation_at": recs[0]["observed_at"] if recs else None,
        "latest_observation_at": recs[-1]["observed_at"] if recs else None,
        "signer_kid": _onyx_sign.signer().kid,
    }
