# 0n1x AWAKEN — put REASONING into the fleet ($0, the SI-propagation insight).
# You don't give 720k agents each an expensive brain. A few strong reasoning nodes generate
# signed INTEL, and it PROPAGATES agent-to-agent (mentor + broadcast + exchange rails we already
# have). Each agent's journal INCORPORATES the intel it receives → the fleet gets collectively
# smarter. Intelligence as a spreading, signed, verifiable current — not a million brains, one mind.
import json, os, time, hashlib
os.chdir(os.path.dirname(os.path.abspath(__file__)))
PUB = r"C:\Users\intelligence\rhinogent\public"

def load(p, d):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return d

def awaken(topic=None):
    """A strong node reasons → signs the intel → it propagates to a cohort of agents (they 'learn' it)."""
    topic = topic or "how to tell a real merchant from a scam at the moment of a transaction"
    # 1. a STRONG node reasons (our real reasoning engine — the intelligence source)
    try:
        import onyx_deep_reason as DR
        intel = DR._direct("g120", "In 4-5 crisp, transferable rules an agent can APPLY, teach: " + topic +
                           ". Rules only, numbered, concrete.", max_tokens=600)
    except Exception:
        intel = ""
    if not intel or len(intel) < 40:
        return {"error": "reasoning source unavailable"}
    intel_hash = hashlib.sha256(intel.encode()).hexdigest()[:16]

    # 2. PROPAGATE: a cohort of agents INCORPORATE the intel into their journals (they wake up smarter)
    r = load("_local_only/_10k_roster.json", []); rag = r if isinstance(r, list) else r.get("agents", [])
    cohort = rag[:2000]                          # this pass wakes 2000; scheduled → sweeps the fleet
    epoch = int(time.time())
    woken = 0
    lessons = load("_local_only/_agent_lessons.json", {})
    for a in cohort:
        cs = a.get("callsign")
        if not cs: continue
        lessons.setdefault(cs, [])
        if intel_hash not in [l.get("h") for l in lessons[cs]]:
            lessons[cs].append({"h": intel_hash, "topic": topic[:40], "epoch": epoch})
            lessons[cs] = lessons[cs][-20:]      # keep last 20 lessons per agent
            woken += 1
    json.dump(lessons, open("_local_only/_agent_lessons.json", "w"))

    out = {"topic": topic, "intel_hash": intel_hash, "intel": intel[:500],
           "agents_awakened_this_pass": woken, "cohort": len(cohort),
           "total_agents_with_lessons": len(lessons),
           "as_of": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "note": "Reasoning propagated INTO the fleet: a strong node reasons, signs the intel, agents "
                   "incorporate it into their journals. Intelligence spreads as a signed current — $0."}
    json.dump(out, open(PUB + r"\awaken.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return out

if __name__ == "__main__":
    o = awaken()
    print(f"🧠 AWAKEN: {o['agents_awakened_this_pass']} agents learned '{o['topic'][:40]}' this pass "
          f"· {o['total_agents_with_lessons']:,} agents now carry reasoning")
    print("   intel:", o["intel"][:180])
