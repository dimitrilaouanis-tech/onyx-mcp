"""Onyx durable store — survives restarts/redeploys.

A tiny whole-namespace JSON blob store. Uses Postgres when DATABASE_URL (or
ONYX_DATABASE_URL) is set — so mail and rooms persist across Render deploys and
spin-downs — and falls back to a local JSON file when no DB is configured, so
dev and unconfigured deploys still work (just ephemeral).

    get(ns) -> dict          # whole namespace, {} if absent
    put(ns, dict) -> None    # replace the whole namespace
    backend() -> "postgres" | "file"
"""
from __future__ import annotations

import json
import os

_DB = (os.environ.get("DATABASE_URL") or os.environ.get("ONYX_DATABASE_URL") or "").strip()
_DIR = os.path.dirname(__file__)
_pg_ok = None  # lazy: None=unknown, True/False once probed


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
            c.execute(
                "CREATE TABLE IF NOT EXISTS onyx_kv "
                "(k text PRIMARY KEY, v jsonb NOT NULL, updated_at timestamptz DEFAULT now())")
            c.commit()
        _pg_ok = True
    except Exception:
        _pg_ok = False
    return _pg_ok


def _file(ns: str) -> str:
    return os.path.join(_DIR, f"_{ns}.json")


def get(ns: str) -> dict:
    if _try_pg():
        try:
            import psycopg
            with psycopg.connect(_DB, connect_timeout=10) as c:
                row = c.execute("SELECT v FROM onyx_kv WHERE k=%s", (ns,)).fetchone()
            if row and isinstance(row[0], dict):
                return row[0]
            return {}
        except Exception:
            pass  # fall through to file
    try:
        with open(_file(ns), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def put(ns: str, data: dict) -> None:
    if _try_pg():
        try:
            import psycopg
            with psycopg.connect(_DB, connect_timeout=10) as c:
                c.execute(
                    "INSERT INTO onyx_kv (k, v, updated_at) VALUES (%s, %s::jsonb, now()) "
                    "ON CONFLICT (k) DO UPDATE SET v = EXCLUDED.v, updated_at = now()",
                    (ns, json.dumps(data)))
                c.commit()
            return
        except Exception:
            pass  # fall through to file
    try:
        p = _file(ns)
        with open(p + ".tmp", "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(p + ".tmp", p)
    except Exception:
        pass


def backend() -> str:
    return "postgres" if _try_pg() else "file"
