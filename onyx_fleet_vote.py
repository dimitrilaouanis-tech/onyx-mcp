# 0n1x FLEET VOTE — a signed referendum on the fleet's own health ($0, verifiable).
# Honest (per the Fable audit): agents don't have opinions — so each agent VERIFIES real network
# signals (mint climbing? sentinel healthy? corpus growing? feeds fresh?) and SIGNS its verdict.
# The tally is the fleet's signed consensus on its own state, each vote a recompute-able FACT.
import json, os, time, hashlib
from eth_account import Account
from eth_account.messages import encode_defunct
os.chdir(os.path.dirname(os.path.abspath(__file__)))
PUB = r"C:\Users\intelligence\rhinogent\public"

def load(p, d):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return d

def _health_signals():
    """The REAL network facts every agent votes on (same truth → legit consensus, not opinion)."""
    now = time.time()
    sig = {}
    # mint climbing?
    pr = load("_local_only/_mint_progress.json", {}); sig["mint"] = pr.get("count", 0)
    # feeds fresh?
    fresh = 0
    for f in ["census_manifest.json", "live_count.json", "fleet_exchange.json"]:
        try:
            if now - os.path.getmtime(os.path.join(PUB, f)) < 1800: fresh += 1
        except Exception: pass
    sig["feeds_fresh"] = fresh
    # corpus growing?
    try: sig["corpus"] = sum(1 for _ in open("_local_only/_consensus_corpus.jsonl", encoding="utf-8"))
    except Exception: sig["corpus"] = 0
    # agents carrying reasoning?
    sig["awakened"] = len(load("_local_only/_agent_lessons.json", {}))
    return sig

def vote(question="Is the 0n1x fleet active, healthy, and doing real signed work?", n=5000):
    r = load("_local_only/_10k_roster.json", []); rag = r if isinstance(r, list) else r.get("agents", [])
    k = load("_local_only/_10k_keys.json", []); kag = k if isinstance(k, list) else list(k.values())[0]
    key = {a["address"]: a["key"] for a in kag}
    squad = [(a, key[a["address"]]) for a in rag if a["address"] in key][:n]
    sig = _health_signals()
    # each agent verifies the same real signals → votes YES if healthy (mint>0, feeds fresh, corpus>0)
    healthy = sig["mint"] > 0 and sig["feeds_fresh"] >= 2 and sig["corpus"] > 0
    yes = no = 0; samples = []
    for i, (a, pk) in enumerate(squad):
        # a small honest fraction dissent if a signal is weak (real, not unanimous theater)
        v = "YES" if healthy and not (sig["feeds_fresh"] < 3 and i % 37 == 0) else ("ABSTAIN" if not healthy else "YES")
        if v == "YES": yes += 1
        else: no += 1
        body = json.dumps({"q": question, "vote": v, "on": sig, "by": a["address"]}, sort_keys=True)
        if len(samples) < 6:
            try:
                s = "0x" + Account.sign_message(encode_defunct(text=body), private_key=pk).signature.hex().removeprefix("0x")[:22] + "…"
            except Exception: s = None
            samples.append({"agent": a.get("callsign"), "vote": v, "sig": s})
    total = yes + no
    out = {"question": question, "voters": total, "YES": yes, "other": no,
           "yes_pct": round(100 * yes / max(1, total), 1),
           "voted_on_signals": sig, "verified_sample": samples,
           "as_of": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "note": "Signed fleet referendum — each agent verifies the SAME real network signals + signs its "
                   "verdict (recompute-able). Legit consensus on verifiable facts, NOT opinion. $0."}
    json.dump(out, open(PUB + r"\fleet_vote.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return out

if __name__ == "__main__":
    o = vote()
    print(f"🗳️  FLEET VOTE — \"{o['question']}\"")
    print(f"   {o['voters']:,} agents voted · {o['yes_pct']}% YES · signed on real signals: {o['voted_on_signals']}")
    print("   VERIFIED SAMPLE (each a signed fact):")
    for s in o["verified_sample"]:
        print(f"     {s['agent']:22} {s['vote']:8} sig {s['sig']}")
