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

# SINGLETON LOCK — only one minter mints at a time; respawned/racing copies exit cleanly.
# (concurrent os.replace on Windows = PermissionError → crash → respawn → stuck. This kills the race.)
LOCK = "_local_only/_mint.lock"
_now = time.time()
try:
    if os.path.exists(LOCK) and _now - os.path.getmtime(LOCK) < 45:
        print("another minter holds the lock — exiting (no race)", flush=True)
        raise SystemExit(0)
except SystemExit:
    raise
except Exception:
    pass
open(LOCK, "w").write(str(os.getpid()))

roster = json.load(open("_local_only/_10k_roster.json"))
rag = roster if isinstance(roster, list) else roster.get("agents")
keys = json.load(open("_local_only/_10k_keys.json"))
kag = keys if isinstance(keys, list) else list(keys.values())[0]

import random, os as _os
random.seed()
have = len(rag)
need = max(0, TARGET - have)
print(f"cohort now {have:,} · minting {need:,} → {TARGET:,}", flush=True)
t0 = time.time()

def _replace_retry(src, dst, tries=6):
    for k in range(tries):
        try:
            _os.replace(src, dst); return
        except PermissionError:
            time.sleep(0.3 * (k + 1))            # transient Windows lock — back off + retry
    _os.replace(src, dst)                        # final attempt (raise if still locked)

def save():
    # atomic-ish checkpoint so a kill never corrupts + progress always persists.
    # unique tmp names per-pid so concurrent writers never share a tmp file.
    pid = _os.getpid()
    rt, kt = f"_local_only/_10k_roster.{pid}.tmp", f"_local_only/_10k_keys.{pid}.tmp"
    json.dump(rag if isinstance(roster, list) else {"agents": rag}, open(rt, "w"))
    _replace_retry(rt, "_local_only/_10k_roster.json")
    json.dump(kag if isinstance(keys, list) else {"agents": kag}, open(kt, "w"))
    _replace_retry(kt, "_local_only/_10k_keys.json")
    open(LOCK, "w").write(str(pid))              # refresh the lock so we keep holding it while minting

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
        save()                                    # CHECKPOINT — singleton lock prevents the race
        print(f"  minted {i+1:,} · saved ({time.time()-t0:.0f}s)", flush=True)
save()

# timeline event — 100k is a network milestone
EV = "_local_only/_timeline_events.json"
try: events = json.load(open(EV, encoding="utf-8"))
except Exception: events = []
events.append({"ts": time.strftime("%Y-%m-%d %H:%M", time.gmtime()), "k": "scale100k",
    "title": f"{TARGET:,} agents operating",
    "detail": f"cohort scaled to {TARGET:,} real keypairs — each a signed citizen in the 0n1x economy"})
json.dump(events[-40:], open(EV, "w", encoding="utf-8"))

print(f"DONE: {len(rag):,} agents with real keys in {time.time()-t0:.0f}s · $0")
