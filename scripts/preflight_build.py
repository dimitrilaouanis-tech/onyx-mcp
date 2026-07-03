#!/usr/bin/env python3
"""preflight_build.py — the build gate that protects the SHARED deploy from parallel sessions.

Multiple Claude sessions edit this same repo/working-dir concurrently and push to main,
which is what Render auto-deploys. One session's broken commit = everyone's deploy down.
This reproduces the essentials of the Render build LOCALLY so a breaking change is caught
BEFORE it is pushed:

  1. byte-compile every .py (catches syntax errors on any Python version)
  2. import every tools_pkg module (catches import-time breakage)
  3. build the ASGI app exactly as `uvicorn server_http:app` does (catches app-construction
     errors, missing tool attributes, bad routes)

Exit 0 = safe to push. Non-zero = DO NOT push; the deploy would break.
Wired as a git pre-push hook (.git/hooks/pre-push) so it runs automatically for every
session on this machine. Run manually any time:  python scripts/preflight_build.py
"""
from __future__ import annotations

import os
import sys
import importlib
import pkgutil
import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILS: list[str] = []


def step(label: str) -> None:
    print(f"[preflight] {label} ...", flush=True)


def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    # server_http requires a receive address; supply a throwaway so the build runs.
    os.environ.setdefault("ONYX_RECEIVE_ADDRESS", "0x0000000000000000000000000000000000000000")
    os.environ.setdefault("ONYX_NETWORK", "base-sepolia")

    # 0. every repo-local module imported by TRACKED code must itself be TRACKED.
    # This is the exact bug class that froze prod 07-01→07-03: tools_pkg/_stats.py
    # was imported by server_http.py but never git-added — every local test passed
    # (the file was in the working dir) while every Render deploy died on
    # ImportError. The working dir lies; only the git tree ships.
    step("checking imported modules are tracked in git")
    import re
    import subprocess
    try:
        tracked = set(subprocess.check_output(
            ["git", "ls-files"], cwd=ROOT, text=True).splitlines())
        imp_re = re.compile(
            r"^\s*(?:from\s+(tools_pkg|onyx_paid_mcp)\s+import\s+([\w,\s]+)"
            r"|import\s+(tools_pkg|onyx_paid_mcp)\.(\w+))", re.M)
        for src in [p for p in tracked if p.endswith(".py")]:
            try:
                text = (ROOT / src).read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for m in imp_re.finditer(text):
                pkg = m.group(1) or m.group(3)
                names = m.group(2) or m.group(4) or ""
                for name in [n.strip() for n in names.split(",") if n.strip()]:
                    mod = f"{pkg}/{name}.py"
                    pkg_dir = f"{pkg}/{name}/__init__.py"
                    # case-insensitive membership: Windows working dirs resolve
                    # App.py == app.py, but the git tree (and Linux/Render) won't.
                    tracked_ci = {t.lower() for t in tracked}
                    if mod.lower() not in tracked_ci and pkg_dir.lower() not in tracked_ci \
                            and (ROOT / mod).exists():
                        FAILS.append(
                            f"UNTRACKED {mod}: imported by {src} but not in git — "
                            f"deploy WILL crash with ImportError (git add it)")
    except Exception as e:  # noqa: BLE001 - git absent etc.; don't block on the checker itself
        print(f"[preflight] (tracking check skipped: {type(e).__name__}: {str(e)[:80]})")

    # 1. byte-compile every .py
    step("byte-compiling all .py")
    for p in list(ROOT.glob("*.py")) + list((ROOT / "tools_pkg").glob("*.py")) \
            + list((ROOT / "onyx_paid_mcp").rglob("*.py")):
        try:
            py_compile.compile(str(p), doraise=True)
        except py_compile.PyCompileError as e:
            FAILS.append(f"SYNTAX  {p.relative_to(ROOT)}: {str(e).splitlines()[-1][:160]}")

    # 2. import every tools_pkg module
    step("importing every tools_pkg module")
    try:
        import tools_pkg
        for info in pkgutil.iter_modules(tools_pkg.__path__):
            name = "tools_pkg." + info.name
            try:
                importlib.import_module(name)
            except Exception as e:  # noqa: BLE001 - want every failure, not the first
                FAILS.append(f"IMPORT  {name}: {type(e).__name__}: {str(e)[:160]}")
    except Exception as e:  # noqa: BLE001
        FAILS.append(f"IMPORT  tools_pkg package: {type(e).__name__}: {str(e)[:160]}")

    # 3. build the ASGI app like Render's start command does
    step("building server_http:app")
    try:
        import server_http
        assert getattr(server_http, "app", None) is not None, "server_http.app is None"
    except Exception as e:  # noqa: BLE001
        FAILS.append(f"APP     server_http:app build: {type(e).__name__}: {str(e)[:200]}")

    if FAILS:
        print("\n[preflight] [FAIL] BUILD WOULD FAIL -- push blocked. Fix these first:\n")
        for f in FAILS:
            print("   " + f)
        print("\n[preflight] (the shared Render deploy is what every session depends on -- "
              "do not push a broken build.)")
        return 1
    print("\n[preflight] [OK] build is sound -- safe to push.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
