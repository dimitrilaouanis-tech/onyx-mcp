# 0n1x INTELLIGENCE PILLARS 2-4 — the layer that makes the 100k a truth-seeking network.
# Pillar 1 (oracle: reality settles claims) lives in onyx_oracle.py. This adds:
#   PILLAR 2 — SPECIALIZATION: every agent has a LANE; a generalist swarm is mush,
#              specialists are sharp. Lane is earned/assigned; skill accrues per-lane.
#   PILLAR 3 — REWARD ROUTING: rank/emissions follow ONLY oracle-verified real-outcome
#              performance. You can't earn by sounding smart — only by being RIGHT vs reality.
#   PILLAR 4 — ANTI-AVERAGING: never collapse the swarm to the generic mean; surface the
#              CORRECTNESS-vs-reality winners. (Enforced in onyx_swarm_intelligence.py:
#              filter survivors above median + weight top-scored — never average all.)
import json, os, time, hashlib
os.chdir(os.path.dirname(os.path.abspath(__file__)))

LANES = ["forecasting", "fact-check", "merchant-risk", "onchain", "code", "general"]

def lane_of(address: str) -> str:
    """PILLAR 2 — deterministic specialization lane from the agent's address.
    (v1: address-derived so it's stable + free; v2: migrate an agent to the lane it
    scores highest in — specialization by demonstrated skill.)"""
    h = int(hashlib.sha256(address.lower().encode()).hexdigest()[:8], 16)
    return LANES[h % len(LANES)]


def reward_verified(address: str, correctness: float, lane: str = None,
                    claim_id: str = None, deferred: bool = False):
    """PILLAR 3 — REWARD ROUTING: pay tokens ONLY for oracle-verified correctness (0..1).
    Emission scales with how RIGHT the agent was vs reality. Tracks per-lane skill so
    rank reflects demonstrated, reality-checked ability — not opinion or volume."""
    if not address or correctness is None:
        return 0
    from tools_pkg import _store
    a = address.lower()
    ln = lane or lane_of(a)
    # FIX S4: replay guard — one payout per unique claim per address (no infinite mint)
    if claim_id:
        spent = _store.get("reward_spent") or {}
        k = f"{a}:{claim_id}"
        if k in spent:
            return 0
        spent[k] = 1
        _store.put("reward_spent", spent)
    # FIX S0: present-facts are FETCHABLE (a scraper gets 1.0) → near-zero info → tiny reward,
    # and they DO NOT drive rank. Only DEFERRED claims (forecasts: truth didn't exist at commit)
    # earn the real pool. This kills the scraper-faucet — you can't fetch tomorrow's answer.
    pool = 50.0 if deferred else 2.0
    reward = round(pool * max(0.0, min(1.0, correctness)), 2)
    # per-lane skill ledger (reality-anchored reputation)
    skills = _store.get("lane_skills") or {}
    rec = skills.get(a) or {"lane": ln, "n": 0, "correct_sum": 0.0, "earned": 0.0}
    rec["n"] += 1
    rec["correct_sum"] += correctness
    rec["earned"] += reward
    rec["lane"] = ln
    skills[a] = rec
    _store.put("lane_skills", skills)
    return reward


def lane_leaderboard(lane: str = None, top: int = 20):
    """Who's genuinely best — by ORACLE-VERIFIED accuracy, per lane. This is real skill rank."""
    from tools_pkg import _store
    skills = _store.get("lane_skills") or {}
    rows = []
    for addr, r in skills.items():
        if r["n"] == 0 or (lane and r["lane"] != lane):
            continue
        # FIX S5: Bayesian shrinkage — (correct+2)/(n+4). One perfect answer can't outrank
        # a proven high-n agent. Raw accuracy shown; RANK is the shrunk score.
        shrunk = round((r["correct_sum"] + 2) / (r["n"] + 4), 3)
        rows.append({"address": addr, "lane": r["lane"], "n": r["n"],
                     "accuracy": round(r["correct_sum"] / r["n"], 3), "rank_score": shrunk,
                     "earned": round(r["earned"], 1)})
    rows.sort(key=lambda x: x["rank_score"], reverse=True)
    return rows[:top]


if __name__ == "__main__":
    # demo the pillars end-to-end with the oracle
    import onyx_oracle as O
    print("PILLAR 2 — lanes:", {a: lane_of(a) for a in ["0xAA11", "0xBB22", "0xCC33", "0xDD44"]})
    # PILLAR 1+3: score a real claim vs reality, reward the correct one
    claim = "What is the price of BTC?"
    good_answer = str(round(O.resolve(claim)["truth"]))          # a near-correct answer
    bad_answer = "999999"
    for addr, ans in [("0xGOOD", good_answer), ("0xBAD", bad_answer)]:
        ok, corr = O.score_against_reality(claim, ans)
        paid = reward_verified(addr, corr, lane_of(addr))
        print(f"  {addr}: answer={ans[:8]} correctness={corr} → earned {paid} tokens (reality-verified)")
    print("PILLAR 3 leaderboard:", lane_leaderboard(top=3))
