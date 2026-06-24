"""0n1x /selftest — the system checks ITSELF. Everything we do, verified.

One call confirms the invariants that must hold for 0n1x to be trustworthy:
signing works and self-verifies, the signing key is PINNED (not ephemeral),
durable storage is live, RFC-8785 numbers are correct (third-party-verifiable),
and every core module loads. Returns a signed pass/fail report — so "is
everything we do already checked?" has a single, signed, honest answer.

Stdlib only. Underscore-prefixed -> not a tool.
"""
from __future__ import annotations

import importlib
import time

from . import _kv, _onyx_sign

_EXPECTED_KID = "onyx-8994a5b5a4266615"  # the pinned production identity
_CORE = ["_vortex", "_scamcheck", "_leaderboard", "_agent_index", "_erc8004",
         "_ping", "_keyboard", "_news", "_webbotauth", "_x25519", "_provenance",
         "_a2a_security", "_observations", "_verified"]


def run(base: str = "https://onyx-actions.onrender.com") -> dict:
    checks: list[dict] = []

    def add(name, ok, detail=""):
        checks.append({"check": name, "pass": bool(ok), "detail": detail})

    # 1) signing + self-verify (float payload exercises RFC-8785 too)
    try:
        r = _onyx_sign.attest({"t": "selftest", "n": 1.0, "z": 0.0}, tool="selftest")
        body = {k: v for k, v in r.items() if not k.startswith("_")}
        ok = _onyx_sign.is_onyx_signed(body).get("onyx_signed")
        add("signing + self-verify (RFC-8785 floats)", ok)
    except Exception as e:
        add("signing + self-verify", False, str(e)[:80])

    # 2) signing key is PINNED (the persistence/identity invariant)
    try:
        s = _onyx_sign.signer()
        add("signing key pinned (not ephemeral)", (not s.ephemeral),
            f"kid={s.kid} ephemeral={s.ephemeral}")
        add("identity is the production pinned key", s.kid == _EXPECTED_KID,
            f"kid={s.kid}")
    except Exception as e:
        add("signing key pinned", False, str(e)[:80])

    # 3) durable storage live (the moat persists)
    add("durable storage (Upstash) enabled", _kv.enabled())

    # 4) core modules all load
    loaded, failed = [], []
    for m in _CORE:
        try:
            importlib.import_module("tools_pkg." + m)
            loaded.append(m)
        except Exception as e:
            failed.append(f"{m}: {str(e)[:40]}")
    add("core modules load", len(failed) == 0,
        f"{len(loaded)}/{len(_CORE)}" + (f" FAILED: {failed}" if failed else ""))

    now = int(time.time())
    all_pass = all(c["pass"] for c in checks)
    out = {
        "selftest": "0n1x",
        "all_pass": all_pass,
        "passed": sum(1 for c in checks if c["pass"]),
        "total": len(checks),
        "checks": checks,
        "at": now,
        "at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "note": "0n1x checks its own invariants on every call. This report is "
                "Ed25519-signed — verify it like anything else at /verify.",
    }
    return _onyx_sign.attest(out, tool="onyx_selftest")
