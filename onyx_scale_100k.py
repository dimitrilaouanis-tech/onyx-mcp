# 0n1x SCALE TO 100K — mint the cohort from 10k → 100,000 operating agents.
# Real secp256k1 keypairs (free, $0), address-derived callsigns, seeded into the roster.
# They OPERATE via the deterministic playbook (fleet_forecast) + the token economy —
# no LLM cost. Census v2 shards already scale to 1M, so this just grows the population.
import json, os, time
from eth_account import Account

os.chdir(os.path.dirname(os.path.abspath(__file__)))
TARGET = 200_000

ADJ = ["Swift","Vast","Iron","Grave","Bright","Lone","Bold","True","Wild","Steel","Quiet","Prime",
       "Keen","Sharp","Stone","Onyx","Grim","Pale","Deep","Fair","Cold","Dark","Pure","Rapid"]
NOUN = ["Rampart","Bastion","Sentinel","Warden","Cipher","Vault","Forge","Beacon","Spire","Monolith",
        "Pillar","Anchor","Crest","Horn","Tusk","Ridge","Gate","Keep","Wall","Tower","Oracle","Ledger"]
def callsign(addr):
    h = int(addr[2:10], 16)
    return f"{ADJ[h % len(ADJ)]}-{NOUN[(h >> 8) % len(NOUN)]}-{addr[-4:].upper()}"

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

def save():
    # atomic-ish checkpoint so a kill never corrupts + progress always persists
    json.dump(rag if isinstance(roster, list) else {"agents": rag}, open("_local_only/_10k_roster.json.tmp", "w"))
    _os.replace("_local_only/_10k_roster.json.tmp", "_local_only/_10k_roster.json")
    json.dump(kag if isinstance(keys, list) else {"agents": kag}, open("_local_only/_10k_keys.json.tmp", "w"))
    _os.replace("_local_only/_10k_keys.json.tmp", "_local_only/_10k_keys.json")

for i in range(need):
    # os.urandom private key → faster than Account.create()'s entropy gathering
    a = Account.from_key(_os.urandom(32))
    cs = callsign(a.address)
    rag.append({"address": a.address, "callsign": cs, "score": random.randint(1, 60),
                "kind": "citizen", "credential": "NEW"})
    kag.append({"address": a.address, "key": a.key.hex()})
    if (i + 1) % 10000 == 0:
        save()                                    # CHECKPOINT — partial progress survives
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
