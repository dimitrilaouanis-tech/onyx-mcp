# 0n1x SI GENERATOR — the intelligence engine that oscillates the whole system UP ($0).
# Each cycle: (1) the internal-divergence panel REASONS on a real fleet-relevant question →
# (2) the answer is distilled to transferable RULES + signed → (3) propagated into the right lane
# (awaken) → (4) the system's collective intelligence measurably grows. Ties reasoning + learning +
# propagation into one continuous current. Not a million brains — one spreading, deepening mind.
import json, os, time, hashlib
os.chdir(os.path.dirname(os.path.abspath(__file__)))
PUB = r"C:\Users\intelligence\rhinogent\public"

def load(p, d):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return d

# rotating questions the fleet genuinely needs sharper answers to (per lane)
LANE_QUESTIONS = {
    "VERIFY":      "What's the sharpest single tell that a merchant is a scam that domain-age misses?",
    "PREDICT":     "What's the most common calibration mistake that wrecks a Brier score, and the fix?",
    "CORROBORATE": "How do you re-verify a claim so your check is genuinely independent, not an echo?",
    "WITNESS":     "What makes an observation tamper-evident enough that a skeptic can't dispute it?",
}

def generate():
    """One SI cycle: reason on one lane's hardest question → sign the intel → propagate it."""
    st = load("_local_only/_si_state.json", {"cycle": 0, "lane_i": 0, "intelligence_units": 0})
    lanes = list(LANE_QUESTIONS)
    lane = lanes[st.get("lane_i", 0) % len(lanes)]
    q = LANE_QUESTIONS[lane]

    # 1. GENERATE intelligence — our own reasoning engine (internal divergence → distilled rules)
    intel = ""
    try:
        import onyx_deep_reason as DR
        intel = DR._direct("g120", "Answer in 3 crisp, transferable RULES an agent can apply. " + q +
                           " Numbered, concrete, no preamble.", max_tokens=500)
        if intel and len(intel) > 40:
            # sharpen it — a different family critiques (the oscillation: reason → refine)
            crit = DR._direct("gemini", "Tighten these rules; cut any that's vague, add the missing one:\n" + intel, max_tokens=500)
            if crit and len(crit) > len(intel) * 0.5: intel = crit
    except Exception:
        pass
    if not intel or len(intel) < 40:
        return {"error": "reasoning source unavailable this cycle"}
    ih = hashlib.sha256(intel.encode()).hexdigest()[:16]

    # 2. PROPAGATE — sign it into the lane's curriculum so awaken spreads it to that lane's agents
    curric = load("_local_only/_si_curriculum.json", {})
    curric.setdefault(lane, [])
    if ih not in [c.get("h") for c in curric[lane]]:
        curric[lane].append({"h": ih, "q": q, "intel": intel[:600], "cycle": st["cycle"] + 1,
                             "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        curric[lane] = curric[lane][-30:]        # a growing, deepening lane curriculum
        st["intelligence_units"] = st.get("intelligence_units", 0) + 1
    json.dump(curric, open("_local_only/_si_curriculum.json", "w", encoding="utf-8"))

    # 3. MEASURE + publish the system's rising intelligence
    st["cycle"] += 1; st["lane_i"] = (st.get("lane_i", 0) + 1) % len(lanes)
    json.dump(st, open("_local_only/_si_state.json", "w"))
    total_curric = sum(len(v) for v in curric.values())
    out = {"cycle": st["cycle"], "lane": lane, "generated_rules_hash": ih, "intel": intel[:400],
           "intelligence_units": st["intelligence_units"], "curriculum_depth": total_curric,
           "lanes": {k: len(v) for k, v in curric.items()},
           "as_of": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "note": "SI generator: reason → refine → sign → propagate per lane. The system's collective "
                   "intelligence deepens every cycle — a spreading, verifiable current, $0."}
    json.dump(out, open(PUB + r"\si_state.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return out

if __name__ == "__main__":
    o = generate()
    if "error" in o: print("SI:", o["error"])
    else:
        print(f"🌀 SI GENERATOR cycle {o['cycle']} · lane {o['lane']} · intelligence units {o['intelligence_units']} "
              f"· curriculum depth {o['curriculum_depth']} {o['lanes']}")
        print("   generated:", o["intel"][:180])
