"""_ledger — the Onyx verdict→outcome graph. THE moat.

Every other tool only EMITS a signed verdict. This is where verdicts become a
measured track record: an agent (or our own monitoring) reports what actually
happened after a verdict, and we log {verdict → outcome}. Over time that graph
is what lets Onyx say not "we think this is risky" but "of the N times we said
BLOCK, X% really did drain" — the data an underwriter prices a guarantee on.
Nobody else in the x402 space has this, because nobody else SIGNS the verdicts
in the first place.

Storage (two backends, same public API either way):
  - Postgres (DATABASE_URL / ONYX_DATABASE_URL set): one row per (verdict_id,
    outcome) in `onyx_ledger_entries`, PRIMARY KEY (verdict_id, outcome) so a
    re-report of the same verdict/outcome pair is a single targeted UPSERT —
    not a full read-merge-rewrite of the whole ledger. This is the durable,
    concurrency-safe path.
  - No DATABASE_URL: falls back to the ORIGINAL behavior unchanged —
      - a DURABLE base, `_onyx_ledger_seed.jsonl`, committed to the repo →
        survives every deploy. Seeded with independently on-chain-verifiable
        outcomes so the base track record is real, not asserted.
      - a LIVE layer, `_onyx_ledger.jsonl`, appended at runtime (ephemeral on
        Render free) mirrored to an optional durable sink (webhook).
  - _entries() merges the seed file with either the DB rows (if configured) or
    the live JSONL (fallback), deduping by (verdict_id, outcome) with the more
    recent source winning — same merge semantics as before the Postgres path
    existed, so every caller keeps working unchanged.

Underscore-prefixed → tools_pkg.discover() skips it (helper, not a tool).
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path

_SEED = Path(__file__).with_name("_onyx_ledger_seed.jsonl")   # durable, in repo
_LIVE = Path(os.environ.get("ONYX_LEDGER_PATH", "") or Path(__file__).with_name("_onyx_ledger.jsonl"))
_SINK = os.environ.get("ONYX_LEDGER_SINK_URL", "").strip()    # optional durable mirror (POST)
_SINK_TOKEN = os.environ.get("ONYX_LEDGER_SINK_TOKEN", "").strip()
_MAX_READ = 50000

# outcome vocabulary → severity. "bad" = something went wrong for the wallet.
_OUTCOMES = {
    # bad — a loss / hostile result actually occurred
    "drained": "bad", "reverted": "bad", "reported_scam": "bad",
    "funds_lost": "bad", "funds_unrecoverable": "bad", "honeypot_confirmed": "bad",
    "eoa_spender_confirmed": "bad", "unverified_confirmed": "bad",
    # good — the interaction was fine / the target checked out
    "settled_clean": "good", "confirmed_safe": "good", "no_loss": "good",
    "verified_legit": "good",
    # the verdict itself was wrong in the cautious direction
    "false_positive": "false_positive",
}

# which verdict strings mean "Onyx tried to stop it"
_STOP = {"BLOCK", "FAIL", "REVIEW", "DENY", "REJECT"}
_PASS = {"ALLOW", "PASS", "OK", "CLEAR"}

# =========================================================================
# Postgres backend — targeted indexed UPSERT/SELECT, one row per (vid, outcome).
# =========================================================================

_DB_URL = os.environ.get("ONYX_DATABASE_URL", "") or os.environ.get("DATABASE_URL", "")
_TABLE = "onyx_ledger_entries"
_db_ready = False


def _db():
    """Live psycopg connection, or None if DATABASE_URL isn't set / Postgres
    isn't reachable. Lazily creates `onyx_ledger_entries` (idempotent) on
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
                    verdict_id TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    tool TEXT,
                    verdict TEXT,
                    logged_at BIGINT,
                    payload JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    PRIMARY KEY (verdict_id, outcome)
                )""")
            conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{_TABLE}_tool ON {_TABLE}(tool)")
            conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{_TABLE}_logged_at ON {_TABLE}(logged_at)")
            _db_ready = True
        except Exception:
            pass
    return conn


def ensure_schema() -> dict:
    """Idempotent bootstrap for `onyx_ledger_entries` — safe to call at app
    startup on every boot. No-op (ok=False) when Postgres isn't configured."""
    conn = _db()
    ok = conn is not None
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
    return {"ok": ok, "table": _TABLE}


def _read_db() -> list | None:
    """All ledger rows from Postgres (payload dicts), or None if Postgres isn't
    configured/reachable (the caller falls back to the JSONL live layer)."""
    conn = _db()
    if conn is None:
        return None
    try:
        rows = conn.execute(f"SELECT payload FROM {_TABLE} ORDER BY created_at ASC").fetchall()
        conn.close()
        return [r[0] for r in rows if isinstance(r[0], dict)]
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        return None


def outcomes() -> dict:
    return dict(_OUTCOMES)


def _read(path: Path) -> list:
    out = []
    try:
        if not path.exists():
            return out
        with path.open("r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= _MAX_READ:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        pass
    return out


def _entries() -> list:
    merged = {}
    for e in _read(_SEED):
        vid, oc = e.get("verdict_id"), e.get("outcome")
        if vid and oc:
            merged[(vid, oc)] = e
    db_rows = _read_db()
    if db_rows is not None:
        for e in db_rows:
            vid, oc = e.get("verdict_id"), e.get("outcome")
            if vid and oc:
                merged[(vid, oc)] = e
    else:
        for e in _read(_LIVE):
            vid, oc = e.get("verdict_id"), e.get("outcome")
            if vid and oc:
                merged[(vid, oc)] = e
    return list(merged.values())


def record(entry: dict) -> dict:
    """Log one verdict→outcome record — a targeted UPSERT to Postgres when
    configured (single row, keyed by (verdict_id, outcome)); otherwise the
    original append-to-JSONL (+ optional sink mirror) behavior, unchanged."""
    entry = dict(entry)
    entry.setdefault("logged_at", int(time.time()))
    vid, oc = entry.get("verdict_id"), entry.get("outcome")

    wrote_db = False
    if vid and oc:
        conn = _db()
        if conn is not None:
            try:
                conn.execute(
                    f"INSERT INTO {_TABLE} (verdict_id, outcome, tool, verdict, logged_at, payload) "
                    "VALUES (%s,%s,%s,%s,%s,%s::jsonb) "
                    "ON CONFLICT (verdict_id, outcome) DO UPDATE SET "
                    "tool=EXCLUDED.tool, verdict=EXCLUDED.verdict, "
                    "logged_at=EXCLUDED.logged_at, payload=EXCLUDED.payload",
                    (vid, oc, entry.get("tool"), entry.get("verdict"), entry.get("logged_at"),
                     json.dumps(entry, ensure_ascii=False)))
                wrote_db = True
            except Exception:
                pass
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    line = json.dumps(entry, ensure_ascii=False)
    wrote_live = False
    if not wrote_db:
        # ---- fallback: original append-only JSONL behavior, unchanged ----
        try:
            with _LIVE.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
            wrote_live = True
        except Exception:
            pass
    if _SINK:
        try:
            req = urllib.request.Request(
                _SINK, data=line.encode("utf-8"),
                headers={"Content-Type": "application/json",
                         **({"Authorization": f"Bearer {_SINK_TOKEN}"} if _SINK_TOKEN else {})},
            )
            urllib.request.urlopen(req, timeout=6).read()
        except Exception:
            pass
    return {"written": wrote_db or wrote_live, "durable_base": _SEED.exists(), "sink": bool(_SINK),
            "backend": "postgres" if wrote_db else "file"}


def stats(tool: str | None = None) -> dict:
    rows = _entries()
    if tool:
        rows = [r for r in rows if r.get("tool") == tool]
    tp = fp = tn = fn = 0          # confusion vs. what actually happened
    per_tool: dict = {}
    per_outcome: dict = {}
    last = 0
    value_intercepted = 0.0        # at-risk USDC on STOP verdicts confirmed bad
    value_intercepted_live = 0.0   # same, excluding synthetic seed
    for r in rows:
        v = (r.get("verdict") or "").upper()
        sev = _OUTCOMES.get(r.get("outcome"), "good")
        t = r.get("tool") or "unknown"
        per_tool[t] = per_tool.get(t, 0) + 1
        per_outcome[r.get("outcome")] = per_outcome.get(r.get("outcome"), 0) + 1
        last = max(last, int(r.get("logged_at") or 0), int(r.get("verdict_signed_at") or 0))
        stopped = v in _STOP
        passed = v in _PASS
        if sev == "bad":
            if stopped:
                tp += 1            # correctly blocked a real loss
                amt = r.get("at_risk_usdc")
                if isinstance(amt, (int, float)) and amt > 0:
                    value_intercepted += float(amt)
                    if not str(r.get("detail") or "").startswith("seed:"):
                        value_intercepted_live += float(amt)
            elif passed:
                fn += 1            # missed — passed something that went bad
        elif sev == "false_positive":
            if stopped:
                fp += 1            # blocked something that was actually fine
        else:  # good
            if passed:
                tn += 1            # correctly allowed a clean interaction
            elif stopped:
                fp += 1            # blocked a clean interaction
    block_precision = round(tp / (tp + fp), 4) if (tp + fp) else None
    miss_rate = round(fn / (fn + tn), 4) if (fn + tn) else None

    db_rows = _read_db()
    live_entries = len(db_rows) if db_rows is not None else len(_read(_LIVE))
    backend = "postgres" if db_rows is not None else "file"

    return {
        "total_outcomes": len(rows),
        "resolved": tp + fp + tn + fn,
        "true_block": tp, "false_block": fp, "clean_allow": tn, "missed": fn,
        "block_precision": block_precision,     # of our BLOCKs, fraction that were real threats
        "allow_miss_rate": miss_rate,           # of our ALLOWs, fraction that went bad (lower=better)
        "by_tool": per_tool,
        "by_outcome": per_outcome,
        "value_at_risk_intercepted_usdc": round(value_intercepted, 2),       # incl. synthetic seed
        "value_at_risk_intercepted_live_usdc": round(value_intercepted_live, 2),  # real reports only
        "last_outcome_at": last or None,
        "durable_base_entries": len(_read(_SEED)),
        "live_entries": live_entries,
        "durable": bool(_SINK) or db_rows is not None,  # true when a persistent sink OR Postgres is wired
        "backend": backend,
    }
