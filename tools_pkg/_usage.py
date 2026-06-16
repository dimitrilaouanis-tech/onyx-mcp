"""_usage — the live usage + revenue meter. The fundraise number.

Every paid call mints an AR-1 receipt, but those live in memory and die on
restart, and the payer was stamped as the zero address (Phase-3 placeholder) so
unique paying agents could not be counted. This is the persistent, honest meter
that turns real traffic into the metric an investor asks for first: how many
distinct agents paid, how much USDC was collected, for which tools.

Same no-paid-infra storage as _ledger: an append-only live JSONL (ephemeral on
Render free — accumulates while warm) mirrored to an optional durable sink. The
summary never overstates: it reports whether a durable sink is wired, so the
number is always exactly as trustworthy as the persistence behind it.

Underscore-prefixed -> tools_pkg.discover() skips it (helper, not a tool).
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path

_LIVE = Path(os.environ.get("ONYX_USAGE_PATH", "") or Path(__file__).with_name("_onyx_usage.jsonl"))
_SINK = os.environ.get("ONYX_USAGE_SINK_URL", "").strip()
_SINK_TOKEN = os.environ.get("ONYX_USAGE_SINK_TOKEN", "").strip()
_ZERO = "0x" + "0" * 40
_MAX_READ = 200000


def record(tool: str, amount_usdc, wallet: str = "", network: str = "", tx: str = "") -> None:
    """Append one paid-call event. Best-effort; never raises into the caller."""
    try:
        amt = float(amount_usdc)
    except (TypeError, ValueError):
        amt = 0.0
    entry = {
        "ts": int(time.time()),
        "tool": tool or "",
        "usdc": amt,
        "wallet": (wallet or "").lower() or None,
        "network": network or None,
        "tx": (tx or None),
    }
    line = json.dumps(entry, ensure_ascii=False)
    try:
        with _LIVE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
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


def _read() -> list:
    out = []
    try:
        if not _LIVE.exists():
            return out
        with _LIVE.open("r", encoding="utf-8") as f:
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


def summary() -> dict:
    rows = _read()
    usdc = 0.0
    wallets = set()
    by_tool: dict = {}
    by_day: dict = {}
    first = last = 0
    for r in rows:
        usdc += float(r.get("usdc") or 0)
        w = (r.get("wallet") or "")
        if w and w != _ZERO:
            wallets.add(w)
        t = r.get("tool") or "unknown"
        bt = by_tool.setdefault(t, {"calls": 0, "usdc": 0.0})
        bt["calls"] += 1
        bt["usdc"] = round(bt["usdc"] + float(r.get("usdc") or 0), 6)
        ts = int(r.get("ts") or 0)
        if ts:
            day = time.strftime("%Y-%m-%d", time.gmtime(ts))
            by_day[day] = by_day.get(day, 0) + 1
            first = ts if not first else min(first, ts)
            last = max(last, ts)
    return {
        "paid_calls": len(rows),
        "usdc_collected": round(usdc, 6),
        "unique_paying_agents": len(wallets),
        "by_tool": by_tool,
        "by_day": by_day,
        "first_paid_at": first or None,
        "last_paid_at": last or None,
        "live_events": len(rows),
        "durable": bool(_SINK),
        "persistence": "live+durable_sink" if _SINK else "ephemeral_live_only",
    }
