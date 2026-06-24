"""Onyx durable store — survives restarts/redeploys.

A tiny whole-namespace JSON blob store with three backends, tried in order:
  1. Upstash Redis REST  — UPSTASH_REDIS_REST_URL + UPSTASH_REDIS_REST_TOKEN
  2. Postgres            — DATABASE_URL / ONYX_DATABASE_URL
  3. local JSON file     — always works (ephemeral on Render free)

So mail + agent rooms persist across Render deploys and spin-downs as soon as a
durable backend is configured, and dev still works with no config.

    get(ns) -> dict          # whole namespace, {} if absent
    put(ns, dict) -> None    # replace the whole namespace
    backend() -> "upstash" | "postgres" | "file"
"""
from __future__ import annotations

import json
import os
import urllib.request

_UP_URL = (os.environ.get("UPSTASH_REDIS_REST_URL") or "").strip().rstrip("/")
_UP_TOK = (os.environ.get("UPSTASH_REDIS_REST_TOKEN") or "").strip()
_DB = (os.environ.get("DATABASE_URL") or os.environ.get("ONYX_DATABASE_URL") or "").strip()
_DIR = os.path.dirname(__file__)
_pg_ok = None  # lazy probe


# ---- Upstash Redis REST (no dependency, pure HTTP) ----------------------

def _upstash_on() -> bool:
    return bool(_UP_URL and _UP_TOK)


def _upstash_cmd(cmd: list):
    """Run one Redis command via Upstash REST. Returns the 'result' or raises."""
    req = urllib.request.Request(
        _UP_URL,
        data=json.dumps(cmd).encode(),
        headers={"Authorization": f"Bearer {_UP_TOK}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=12) as r:
        return json.load(r).get("result")


# ---- Postgres -----------------------------------------------------------

def _try_pg() -> bool:
    global _pg_ok
    if _pg_ok is not None:
        return _pg_ok
    if not _DB:
        _pg_ok = False
        return False
    try:
        import psycopg
        with psycopg.connect(_DB, connect_timeout=10) as c:
            c.execute("CREATE TABLE IF NOT EXISTS onyx_kv "
                      "(k text PRIMARY KEY, v jsonb NOT NULL, updated_at timestamptz DEFAULT now())")
            c.commit()
        _pg_ok = True
    except Exception:
        _pg_ok = False
    return _pg_ok


# ---- file ---------------------------------------------------------------

def _file(ns: str) -> str:
    return os.path.join(_DIR, f"_{ns}.json")


# ---- public API ---------------------------------------------------------

def get(ns: str) -> dict:
    if _upstash_on():
        try:
            raw = _upstash_cmd(["GET", f"onyx:{ns}"])
            if raw:
                d = json.loads(raw)
                return d if isinstance(d, dict) else {}
            return {}
        except Exception:
            pass
    if _try_pg():
        try:
            import psycopg
            with psycopg.connect(_DB, connect_timeout=10) as c:
                row = c.execute("SELECT v FROM onyx_kv WHERE k=%s", (ns,)).fetchone()
            return row[0] if (row and isinstance(row[0], dict)) else {}
        except Exception:
            pass
    try:
        with open(_file(ns), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def put(ns: str, data: dict) -> None:
    if _upstash_on():
        try:
            _upstash_cmd(["SET", f"onyx:{ns}", json.dumps(data)])
            return
        except Exception:
            pass
    if _try_pg():
        try:
            import psycopg
            with psycopg.connect(_DB, connect_timeout=10) as c:
                c.execute("INSERT INTO onyx_kv (k, v, updated_at) VALUES (%s, %s::jsonb, now()) "
                          "ON CONFLICT (k) DO UPDATE SET v = EXCLUDED.v, updated_at = now()",
                          (ns, json.dumps(data)))
                c.commit()
            return
        except Exception:
            pass
    try:
        p = _file(ns)
        with open(p + ".tmp", "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(p + ".tmp", p)
    except Exception:
        pass


def backend() -> str:
    if _upstash_on():
        return "upstash"
    if _try_pg():
        return "postgres"
    return "file"
