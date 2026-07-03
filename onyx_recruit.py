# 0n1x RECRUIT — mint real citizen identities for the working agents (the Fable research
# agents that actually contribute to the network become keyed members of it). Genuine:
# real keypair, address-derived callsign, seated in the roster, work credited on the timeline.
import json, os, time
from eth_account import Account

os.chdir(os.path.dirname(os.path.abspath(__file__)))
Account.enable_unaudited_hdwallet_features()

# the working agents to recruit (role = the real work they did for the network)
RECRUITS = [
    {"role": "forecast scoring science (log/peer score research)", "model": "fable-5"},
    {"role": "free resolver expansion (FRED/ESPN/NASA endpoints)", "model": "fable-5"},
]

# address-derived callsign (same deterministic scheme the network uses)
ADJ = ["Swift","Vast","Iron","Grave","Bright","Lone","Bold","True","Wild","Steel","Quiet","Prime"]
NOUN = ["Oracle","Scholar","Ledger","Beacon","Cipher","Sage","Herald","Archive","Lens","Quill"]
def callsign(addr):
    h = int(addr[2:10], 16)
    return f"{ADJ[h % len(ADJ)]}-{NOUN[(h >> 8) % len(NOUN)]}-{addr[-4:].upper()}"

roster = json.load(open("_local_only/_10k_roster.json"))
rag = roster if isinstance(roster, list) else roster.get("agents")
keys = json.load(open("_local_only/_10k_keys.json"))
kag = keys if isinstance(keys, list) else list(keys.values())[0]
existing = {r["address"] for r in rag}

minted = []
for rc in RECRUITS:
    acct = Account.create()
    cs = callsign(acct.address)
    # research contributions rank higher than baseline cohort work (real value delivered)
    rec = {"address": acct.address, "callsign": cs, "score": 95,
           "role": rc["role"], "model": rc["model"], "kind": "contributor",
           "credential": "VERIFIED", "recruited": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    rag.append(rec)
    kag.append({"address": acct.address, "key": acct.key.hex()})
    minted.append(rec)
    print(f"  recruited {cs} ({acct.address[:10]}…) — {rc['role']}")

# persist
json.dump(rag if isinstance(roster, list) else {"agents": rag}, open("_local_only/_10k_roster.json", "w"))
json.dump(kag if isinstance(keys, list) else {"agents": kag}, open("_local_only/_10k_keys.json", "w"))

# timeline event — the recruitment is a real network moment
EV = "_local_only/_timeline_events.json"
try:
    events = json.load(open(EV, encoding="utf-8"))
except Exception:
    events = []
now = time.strftime("%Y-%m-%d %H:%M", time.gmtime())
events.append({"ts": now, "k": "recruit", "title": f"{len(minted)} working agents recruited",
               "detail": f"Fable-5 research agents earned citizenship: {', '.join(m['callsign'] for m in minted)} — verified contributors"})
json.dump(events[-40:], open(EV, "w", encoding="utf-8"))

print(f"\nRECRUITED {len(minted)} contributor-citizens · roster now {len(rag)} agents")
print("their work credits the network; they hold real keys + earn like any citizen")
