"""_ledger — the Onyx verdict→outcome graph. THE moat.

Every other tool only EMITS a signed verdict. This is where verdicts become a
measured track record: an agent (or our own monitoring) reports what actually
happened after a verdict, and we log {verdict → outcome}. Over time that graph
is what lets Onyx say not "we think this is risky" but "of the N times we said
BLOCK, X% really did drain" — the data an underwriter prices a guarantee on.
Nobody else in the x402 space has this, because nobody else SIGNS the verdicts
in the first place.

Storage (no paid infra):
  - a DURABLE base, `_onyx_ledger_seed.jsonl`, committed to the repo → survives
    every deploy. Seeded with outcomes that are independently on-chain-verifiable
    (a BLOCK on the burn address really is unrecoverable; an EOA spender really
    has no code) so the base track record is real, not asserted.
  - a LIVE layer, `_onyx_ledger.jsonl`, appended at runtime (ephemeral on Render
    free — accumulates while the instance is warm; mirrored to an optional sink).
  - stats() merges both and dedups by (verdict_id, outcome).

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
    for e in _read(_SEED) + _read(_LIVE):
        vid = e.get("verdict_id")
        oc = e.get("outcome")
        if not vid or not oc:
            continue
        merged[(vid, oc)] = e
    return list(merged.values())


def record(entry: dict) -> dict:
    """Append one verdict→outcome record to the live layer (+ optional sink)."""
    entry = dict(entry)
    entry.setdefault("logged_at", int(time.time()))
    line = json.dumps(entry, ensure_ascii=False)
    wrote = False
    try:
        with _LIVE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        wrote = True
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
    return {"written": wrote, "durable_base": _SEED.exists(), "sink": bool(_SINK)}


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
        "live_entries": len(_read(_LIVE)),
        "durable": bool(_SINK),                 # true only when a persistent sink is wired
    }
