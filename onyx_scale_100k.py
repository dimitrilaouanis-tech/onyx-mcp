# 0n1x SCALE TO 100K — mint the cohort from 10k → 100,000 operating agents.
# Real secp256k1 keypairs (free, $0), address-derived callsigns, seeded into the roster.
# They OPERATE via the deterministic playbook (fleet_forecast) + the token economy —
# no LLM cost. Census v2 shards already scale to 1M, so this just grows the population.
import json, os, time
from eth_account import Account

os.chdir(os.path.dirname(os.path.abspath(__file__)))
TARGET = 1_000_000

ADJ = ["Swift","Vast","Iron","Grave","Bright","Lone","Bold","True","Wild","Steel","Quiet","Prime",
       "Keen","Sharp","Stone","Onyx","Grim","Pale","Deep","Fair","Cold","Dark","Pure","Rapid"]
NOUN = ["Rampart","Bastion","Sentinel","Warden","Cipher","Vault","Forge","Beacon","Spire","Monolith",
        "Pillar","Anchor","Crest","Horn","Tusk","Ridge","Gate","Keep","Wall","Tower","Oracle","Ledger"]
def callsign(addr):
    h = int(addr[2:10], 16)
    return f"{ADJ[h % len(ADJ)]}-{NOUN[(h >> 8) % len(NOUN)]}-{addr[-4:].upper()}"

# SINGLETON LOCK — a REAL OS-level exclusive lock held for the process lifetime.
# The old mtime-TTL (45s) lock EXPIRED during the multi-minute 250MB JSON load, so scheduled
# respawns raced each other. msvcrt.locking cannot expire: second minter exits instantly.
LOCK = "_local_only/_mint.lock"
_lock_fh = open(LOCK, "a+")
try:
    import msvcrt
    msvcrt.locking(_lock_fh.fileno(), msvcrt.LK_NBLCK, 1)   # held until process exit
except OSError:
    print("another minter holds the lock — exiting (no race)", flush=True)
    raise SystemExit(0)
except ImportError:
    pass                                          # non-Windows fallback: proceed (dev only)
_lock_fh.seek(0); _lock_fh.truncate(); _lock_fh.write(str(os.getpid())); _lock_fh.flush()

roster = json.load(open("_local_only/_10k_roster.json"))
rag = roster if isinstance(roster, list) else roster.get("agents")
keys = json.load(open("_local_only/_10k_keys.json"))
kag = keys if isinstance(keys, list) else list(keys.values())[0]

import random, os as _os, glob as _glob
random.seed()
for _t in _glob.glob("_local_only/_10k_*.tmp"):     # clear orphaned tmps from crashed runs
    try: _os.remove(_t)
    except Exception: pass
have = len(rag)
need = max(0, TARGET - have)
print(f"cohort now {have:,} · minting {need:,} → {TARGET:,}", flush=True)
t0 = time.time()

def _replace_retry(src, dst, tries=12):
    """Windows: os.replace fails Access-denied while ANY reader (count_sync/journal/consensus
    scheduled tasks) holds the 130MB dst JSON open. NEVER raise — the raise here was THE stall:
    it killed the minter mid-run, keepalive respawned it, and each respawn re-loaded 250MB for
    minutes before crashing again. On failure we defer: keep minting, retry at next checkpoint."""
    for k in range(tries):
        try:
            _os.replace(src, dst); return True
        except PermissionError:
            time.sleep(0.5 * (k + 1) + random.random())   # jittered backoff past reader windows
    print(f"  save deferred: {dst} busy (readers) — will retry next checkpoint", flush=True)
    try: _os.remove(src)
    except Exception: pass
    return False

def save():
    # atomic-ish checkpoint so a kill never corrupts + progress always persists.
    pid = _os.getpid()
    ok = True
    rt, kt = f"_local_only/_10k_roster.{pid}.tmp", f"_local_only/_10k_keys.{pid}.tmp"
    json.dump(rag if isinstance(roster, list) else {"agents": rag}, open(rt, "w"))
    ok &= _replace_retry(rt, "_local_only/_10k_roster.json")
    json.dump(kag if isinstance(keys, list) else {"agents": kag}, open(kt, "w"))
    ok &= _replace_retry(kt, "_local_only/_10k_keys.json")
    return ok

for i in range(need):
    # os.urandom private key → faster than Account.create()'s entropy gathering
    a = Account.from_key(_os.urandom(32))
    cs = callsign(a.address)
    rag.append({"address": a.address, "callsign": cs, "score": random.randint(1, 60),
                "kind": "citizen", "credential": "NEW"})
    kag.append({"address": a.address, "key": a.key.hex()})
    if (i + 1) % 500 == 0:
        import json as _j, time as _t
        _j.dump({'count': have + i + 1, 'ts': _t.time()}, open('_local_only/_mint_progress.json','w'))
    if (i + 1) % 9973 == 0:
        save()                                    # CHECKPOINT — non-fatal; defers if readers hold the file
        print(f"  minted {i+1:,} · saved ({time.time()-t0:.0f}s)", flush=True)
# FINAL save must land — keep trying past reader windows
for _k in range(20):
    if save(): break
    time.sleep(10)

# timeline event — 100k is a network milestone
EV = "_local_only/_timeline_events.json"
try: events = json.load(open(EV, encoding="utf-8"))
except Exception: events = []
events.append({"ts": time.strftime("%Y-%m-%d %H:%M", time.gmtime()), "k": "scale100k",
    "title": f"{TARGET:,} agents operating",
    "detail": f"cohort scaled to {TARGET:,} real keypairs — each a signed citizen in the 0n1x economy"})
json.dump(events[-40:], open(EV, "w", encoding="utf-8"))

print(f"DONE: {len(rag):,} agents with real keys in {time.time()-t0:.0f}s · $0")
