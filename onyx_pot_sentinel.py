# 0n1x POT SENTINEL — the fleet guards its own Point Of Truth ($0, self-healing).
# "If you don't catch it, we got another 600k of us." The sentinel watches the mint + the live
# feeds; if the MINT FREEZES (count unchanged across checks) it auto-KICKS it (kills the stuck
# process, clears the lock, relaunches fresh); if FEEDS go stale it flags them. Every pass logged,
# alerts written so the whole fleet (and the operator) is notified. Runs on a schedule, forever.
import json, os, time, subprocess
os.chdir(os.path.dirname(os.path.abspath(__file__)))
PUB = r"C:\Users\intelligence\rhinogent\public"
STATE = "_local_only/_pot_sentinel.json"
LOG = "_local_only/_pot_sentinel.log"
PYW = r"C:\Users\intelligence\AppData\Local\Python\pythoncore-3.14-64\pythonw.exe"

def load(p, d):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return d

def _count():
    r = load("_local_only/_10k_roster.json", []); return len(r if isinstance(r, list) else r.get("agents", []))

def _log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())}  {msg}"
    open(LOG, "a", encoding="utf-8").write(line + "\n"); print(line, flush=True)

def _kick_mint():
    """Kill any stuck minter, clear the lock, relaunch ONE fresh. Self-heal."""
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command",
            "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'scale_100k' } | "
            "ForEach-Object { try{Stop-Process -Id $_.ProcessId -Force -EA SilentlyContinue}catch{} }"],
            timeout=20, capture_output=True)
    except Exception: pass
    try: os.remove("_local_only/_mint.lock")
    except Exception: pass
    time.sleep(2)
    try:
        subprocess.Popen([PYW, "onyx_scale_100k.py"], creationflags=0x08000000)  # DETACHED
    except Exception: pass

def sentinel():
    st = load(STATE, {"last_count": 0, "frozen_checks": 0})
    now = _count()
    target = 1_000_000
    alerts = []

    # 1. MINT WATCH — is the count advancing toward 1M?
    if now < target:
        if now <= st.get("last_count", 0):
            st["frozen_checks"] = st.get("frozen_checks", 0) + 1
            if st["frozen_checks"] >= 2:                 # frozen across 2 checks → KICK it
                _log(f"🔴 MINT FROZEN at {now:,} (frozen {st['frozen_checks']}x) → auto-kicking")
                _kick_mint()
                alerts.append(f"mint was frozen at {now:,}, auto-kicked")
                st["frozen_checks"] = 0
            else:
                _log(f"⚠️ mint not advancing ({now:,}) — watching (check {st['frozen_checks']})")
        else:
            st["frozen_checks"] = 0
            _log(f"🟢 mint climbing: {now:,} (+{now - st.get('last_count',0):,}) → 1M")
    else:
        _log(f"👑 MINT COMPLETE: {now:,} — the million is minted")
    st["last_count"] = now

    # 2. FEED WATCH — are the live feeds fresh?
    stale = []
    for f in ["census_manifest.json", "token_feed.json", "pulse.json", "rt_economy.json", "fleet_exchange.json"]:
        p = os.path.join(PUB, f)
        try:
            age = (time.time() - os.path.getmtime(p)) / 60
            if age > 30: stale.append(f"{f}({age:.0f}m)")
        except Exception: stale.append(f"{f}(missing)")
    if stale:
        _log("⚠️ STALE FEEDS: " + ", ".join(stale)); alerts.append("stale feeds: " + ", ".join(stale))

    # 3. NOTIFY — write the fleet-visible status/alert
    status = {"as_of": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "agents": now,
              "to_million": target - now, "mint_status": "complete" if now >= target else "minting",
              "alerts": alerts, "healthy": not alerts,
              "note": "POT sentinel — the fleet guards its own point of truth: mint self-heals, feeds watched."}
    json.dump(status, open(PUB + r"\pot_sentinel.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(st, open(STATE, "w", encoding="utf-8"))
    return status

if __name__ == "__main__":
    s = sentinel()
    print(f"POT SENTINEL: {s['agents']:,} agents · {s['to_million']:,} to 1M · "
          f"{'✅ healthy' if s['healthy'] else '🔴 ALERTS: ' + str(s['alerts'])}")
