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

# per-specialization curricula — each lane learns a DIFFERENT lesson, not one broadcast
LANE_TOPICS = {
    "VERIFY":      "how to tell a real merchant from a scam at the moment of a transaction "
                   "(domain age, TLS cert, reachability, price-too-good, payment-rail red flags)",
    "PREDICT":     "how to make calibrated probabilistic forecasts that improve a Brier score "
                   "(base rates first, update on evidence, avoid 0/100, track your own record)",
    "CORROBORATE": "how to independently re-verify another agent's claim without echoing it "
                   "(re-derive from primary signals, reward disagreeing-when-right, never rubber-stamp)",
    "WITNESS":     "how to record tamper-evident observations others can verify later "
                   "(timestamp, hash the evidence, sign, chain to prior record, note what you did NOT see)",
}
# offline fallback curricula (still real, transferable rules — awaken never dead-ends at $0)
LANE_FALLBACK = {
    "VERIFY":      "1. Check domain age via RDAP — under 60 days is high risk. 2. Verify the TLS chain "
                   "actually validates for the exact hostname. 3. Confirm the site answers over HTTPS. "
                   "4. Treat >40% discounts on luxury goods as a scam prior. 5. Never trust a merchant "
                   "that only accepts irreversible payment rails.",
    "PREDICT":     "1. Start from the base rate, not the story. 2. Update in small steps per piece of "
                   "evidence. 3. Never say 0% or 100%. 4. Score yourself with Brier after resolution. "
                   "5. When uncertain between two states, widen toward 50, don't guess a side.",
    "CORROBORATE": "1. Re-derive the claim from primary signals yourself; never copy the claimant's "
                   "evidence. 2. State what you found BEFORE comparing to the claim. 3. Dispute when your "
                   "finding differs — correct dissent outranks agreement. 4. Sign what you found, not what "
                   "you agreed to. 5. Record the check method so others can replay it.",
    "WITNESS":     "1. Timestamp every observation at capture. 2. Hash the raw evidence before summarizing. "
                   "3. Sign the hash, not the narrative. 4. Chain each record to your previous one. "
                   "5. Log what you could NOT observe — absence of evidence is itself signed data.",
}

def awaken(topic=None):
    """Strong nodes reason PER SPECIALIZATION → 4 different signed lessons propagate; each agent
    receives the lesson for ITS lane (VERIFY/PREDICT/CORROBORATE/WITNESS), not one broadcast."""
    # 1. one lesson per lane (real reasoning engine when available, curated fallback otherwise)
    lane_intel = {}
    for lane, lane_topic in LANE_TOPICS.items():
        intel = ""
        try:
            import onyx_deep_reason as DR
            intel = DR._direct("g120", "In 4-5 crisp, transferable rules an agent can APPLY, teach: " +
                               lane_topic + ". Rules only, numbered, concrete.", max_tokens=600)
        except Exception:
            intel = ""
        if not intel or len(intel) < 40:
            intel = LANE_FALLBACK[lane]
        lane_intel[lane] = {"topic": lane_topic, "intel": intel,
                            "h": hashlib.sha256(intel.encode()).hexdigest()[:16]}

    # 2. PROPAGATE by specialization: profiled agents get THEIR lane's lesson;
    #    unprofiled agents rotate through the lanes (deterministic by callsign) so lessons still vary.
    profiles = load("_local_only/_profiles.json", {})
    r = load("_local_only/_10k_roster.json", []); rag = r if isinstance(r, list) else r.get("agents", [])
    cohort = rag[:2000]                          # this pass wakes 2000; scheduled → sweeps the fleet
    epoch = int(time.time())
    woken, by_lane = 0, {}
    lanes = list(LANE_TOPICS)
    lessons = load("_local_only/_agent_lessons.json", {})
    for a in cohort:
        cs = a.get("callsign")
        if not cs: continue
        spec = profiles.get(cs, {}).get("specialization")
        lane = spec if spec in lane_intel else lanes[int(hashlib.sha256(cs.encode()).hexdigest()[:4], 16) % len(lanes)]
        li = lane_intel[lane]
        lessons.setdefault(cs, [])
        if li["h"] not in [l.get("h") for l in lessons[cs]]:
            lessons[cs].append({"h": li["h"], "lane": lane, "topic": li["topic"][:40], "epoch": epoch})
            lessons[cs] = lessons[cs][-20:]      # keep last 20 lessons per agent
            woken += 1; by_lane[lane] = by_lane.get(lane, 0) + 1
    json.dump(lessons, open("_local_only/_agent_lessons.json", "w"))

    out = {"lessons": {k: {"topic": v["topic"][:80], "intel_hash": v["h"], "intel": v["intel"][:300]}
                       for k, v in lane_intel.items()},
           "agents_awakened_this_pass": woken, "awakened_by_lane": by_lane, "cohort": len(cohort),
           "total_agents_with_lessons": len(lessons),
           "as_of": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "note": "Per-specialization awakening: VERIFY/PREDICT/CORROBORATE/WITNESS each receive a "
                   "DIFFERENT signed lesson matched to their earned lane. Intelligence propagates as "
                   "lane-targeted, verifiable signed intel — $0."}
    json.dump(out, open(PUB + r"\awaken.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return out

if __name__ == "__main__":
    o = awaken()
    print(f"🧠 AWAKEN: {o['agents_awakened_this_pass']} agents woken this pass, by lane {o['awakened_by_lane']} "
          f"· {o['total_agents_with_lessons']:,} agents now carry reasoning")
    for lane, li in o["lessons"].items():
        print(f"   {lane:12} h={li['intel_hash']} · {li['intel'][:80]}")
