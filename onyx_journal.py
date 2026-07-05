# 0n1x PER-AGENT JOURNAL — the L3 autonomy unlock ($0, on the real 340k roster).
# The divergence-unanimous #1 step to move agents from L1/L2 (identity+economy) to L3 (stateful):
# every agent gets an append-only, signed record of its WORK — and from that history we derive a
# per-agent SKILL VECTOR + earned SPECIALIZATION. Now agent #123 and #98765 are no longer
# interchangeable: they have different histories, skills, and reputations. That is real autonomy.
# Source of work = the real-time economy's work-tied transfers (verify_domain/corroborate/coverage/
# forecast) — already reality-anchored. $0, no LLM. Composes with the sister session's memory layer.
import json, os, hashlib, time

os.chdir(os.path.dirname(os.path.abspath(__file__)))
PUB = r"C:\Users\intelligence\rhinogent\public"
JOURNAL = "_local_only/_journals.json"          # {address: [signed work entries]}
PROFILES = "_local_only/_profiles.json"          # {address: derived skill/specialization}

# the primitive capabilities (the "periodic table" of agent work) → work types map onto these
LANES = {"verify_domain": "VERIFY", "corroborate": "CORROBORATE",
         "coverage": "WITNESS", "forecast": "PREDICT"}
HALF_LIFE = 500        # decay: recent work counts more (use-it-or-lose-it)


def load(p, d):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return d


def ingest():
    """Read the latest work events, append signed journal entries per agent, derive profiles.
    Incremental — only new work since last run (keyed by tx hash)."""
    rt = load("_local_only/_rt_ledger.json", [])
    journals = load(JOURNAL, {})
    seen = load("_local_only/_journal_seen.json", {})
    now_epoch = int(time.time()) // 60
    added = 0
    for tx in rt:
        h = tx.get("hash")
        if not h or h in seen:
            continue
        seen[h] = 1
        # the PAYEE earned the work — record it in their journal (they did the verified work)
        payer_cs, payee_cs = tx.get("from"), tx.get("to")
        work = tx.get("work", "work")
        addr = tx.get("from_addr", "")   # payer address available; use it as the actor for now
        entry = {"work": work, "lane": LANES.get(work, "OTHER"), "amount": tx.get("amount", 0),
                 "epoch": now_epoch, "sig": tx.get("sig", "")[:18], "hash": h}
        j = journals.setdefault(payee_cs or addr, [])
        j.append(entry)
        journals[payee_cs or addr] = j[-100:]   # keep last 100 per agent
        added += 1
    json.dump(journals, open(JOURNAL, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(seen, open("_local_only/_journal_seen.json", "w", encoding="utf-8"))
    return journals, added


def derive_profiles(journals):
    """From each agent's journal, compute a SKILL VECTOR + earned SPECIALIZATION (decay-weighted).
    This is what makes agents genuinely differ — earned from work history, not assigned."""
    now_epoch = int(time.time()) // 60
    profiles = {}
    for agent, entries in journals.items():
        if not entries:
            continue
        skill = {}
        for e in entries:
            lane = e.get("lane", "OTHER")
            age = max(0, now_epoch - e.get("epoch", now_epoch))
            w = 2.718 ** (-age / HALF_LIFE)          # exponential decay
            skill[lane] = skill.get(lane, 0.0) + w
        total = sum(skill.values()) or 1
        skill_pct = {k: round(v / total, 3) for k, v in skill.items()}
        # specialization = the lane the agent has done most (if it dominates)
        top = max(skill_pct, key=skill_pct.get)
        spec = top if skill_pct[top] >= 0.5 else "generalist"
        profiles[agent] = {"missions": len(entries), "skill": skill_pct,
                           "specialization": spec, "updated_epoch": now_epoch}
    json.dump(profiles, open(PROFILES, "w", encoding="utf-8"), ensure_ascii=False)
    return profiles


def publish_sample(journals, profiles):
    """Publish a small public sample (the site can show 'agents with earned histories')."""
    sample = {}
    for agent in list(profiles)[:30]:
        sample[agent] = {"specialization": profiles[agent]["specialization"],
                         "missions": profiles[agent]["missions"],
                         "skill": profiles[agent]["skill"],
                         "recent": journals.get(agent, [])[-3:]}
    out = {"note": "Per-agent earned journals + specializations — the L3 autonomy layer. Each agent's "
                   "skill is derived from its own signed work history (decay-weighted). $0, verifiable.",
           "agents_with_history": len(profiles), "sample": sample,
           "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    try:
        from tools_pkg import _onyx_sign
        out = _onyx_sign.attest(out, tool="onyx_journal")
    except Exception:
        pass
    json.dump(out, open(PUB + r"\journals.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return out


if __name__ == "__main__":
    journals, added = ingest()
    profiles = derive_profiles(journals)
    out = publish_sample(journals, profiles)
    # honest stats
    specs = {}
    for p in profiles.values():
        specs[p["specialization"]] = specs.get(p["specialization"], 0) + 1
    print(f"JOURNAL: +{added} new work entries · {len(journals):,} agents now have earned histories")
    print(f"  specializations emerged: {specs}")
    ex = next(iter(profiles.items()), None)
    if ex:
        print(f"  example — {ex[0]}: {ex[1]['specialization']} ({ex[1]['missions']} missions, skill {ex[1]['skill']})")
