# 0n1x CROWN-JEWEL RESILIENCE — the ledger + keys are single-copy on one laptop.
# (1) hash-chain INTEGRITY check over the signed ledger (tamper-evident, append-only proof),
# (2) rotating BACKUPS of critical state. $0, local, runs every heartbeat.
import json, os, hashlib, shutil, time
os.chdir(os.path.dirname(os.path.abspath(__file__)))
SRC = "_local_only"
BK = "_local_only/_backups"
os.makedirs(BK, exist_ok=True)
CRITICAL = ["_token_ledger.jsonl", "_10k_keys.json", "_10k_roster.json",
            "_forecast_scores.json", "_forecast_commits.jsonl", "_timeline_events.json"]

def ledger_root(limit=None):
    path = f"{SRC}/_token_ledger.jsonl"
    if not os.path.exists(path):
        return None, 0
    chain = "0" * 16
    n = 0
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        chain = hashlib.sha256((chain + line).encode()).hexdigest()[:16]
        n += 1
        if limit and n == limit:
            break
    return chain, n

root, n = ledger_root()
state_f = f"{SRC}/_integrity_state.json"
try:
    prev = json.load(open(state_f))
except Exception:
    prev = {}
tamper = False
if prev.get("n", 0) > 0 and n >= prev["n"]:
    past_root, _ = ledger_root(limit=prev["n"])   # append-only: past must be unchanged
    if past_root != prev.get("root_at_n"):
        tamper = True
json.dump({"n": n, "root": root, "root_at_n": root,
           "checked": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, open(state_f, "w"))

stamp = time.strftime("%Y%m%d-%H%M", time.gmtime())
dest = f"{BK}/{stamp}"
os.makedirs(dest, exist_ok=True)
saved = 0
for fn in CRITICAL:
    p = f"{SRC}/{fn}"
    if os.path.exists(p):
        shutil.copy2(p, f"{dest}/{fn}")
        saved += 1
dirs = sorted(d for d in os.listdir(BK) if os.path.isdir(f"{BK}/{d}"))
for old in dirs[:-5]:
    shutil.rmtree(f"{BK}/{old}", ignore_errors=True)

print(f"integrity: {n} ledger entries, chain-root {root}, tamper={'YES ⚠' if tamper else 'no'}")
print(f"backup: {saved} critical files -> {dest} (keeping last 5)")
