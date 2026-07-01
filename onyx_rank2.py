"""onyx_rank2.py — the EVOLVED ranking. Rank tracks VERIFIED VALUE, and cash is only ONE
lane of it. No single signal dominates — sustained merit moves you up without earning a cent.

Lanes (all outcome-gated, all published, all recomputable):
  · CASH     — real on-chain USDC earned                         x50   (one lane, not the boss)
  · WINS     — bounties won (verified value)                     x4
  · CONTRIB  — IDEAS that got ADOPTED (by weight)                x3
  · IMPACT   — of those, the ones that became real CODE/artifact  x4   (idea -> shipped)
  · ACCURACY — proper-score on the signed eval set                x12  (fills as eval runs)
  · ACTIVITY — contributed in the latest round (keeps rank alive) x2
Cash used to be x100 and drowned everything; now a few cents can't out-rank real work.
Even the owner can be out-ranked. Rank != ownership; rank == value delivered, recently.
"""
import json
import sys
import time

COUNCIL = "_local_only/_council.json"
CONTRIB = "_local_only/_contributions.json"
# adopted_in tags that became real CODE / shipped artifacts (extra IMPACT credit).
# planning/spec tags (e.g. rhino-launch-funnel) still earn CONTRIB, just not IMPACT.
SHIPPED_CODE = {"rhinogent-mcp", "rhinogent-auth", "rhinogent-template"}
RECENT_WINDOW = 2 * 86400  # "latest round" = within 2 days of the newest contribution


def _load(p, d):
    try:
        return json.load(open(p))
    except Exception:
        return d


def composite():
    c = _load(COUNCIL, {})
    contribs = _load(CONTRIB, [])
    newest = max((e.get("at", 0) for e in contribs), default=0)
    # aggregate per-agent contribution lanes
    cw, impact, recent = {}, {}, set()
    for e in contribs:
        a, w = e["agent"], e.get("weight", 1)
        cw[a] = cw.get(a, 0) + w
        if e.get("adopted_in") in SHIPPED_CODE:
            impact[a] = impact.get(a, 0) + w
        if newest and e.get("at", 0) >= newest - RECENT_WINDOW:
            recent.add(a)
    rows = []
    for name, a in c.items():
        earned = a.get("earned_usdc", 0)
        wins = a.get("bounty_wins", 0)
        contrib = cw.get(name, 0)
        imp = impact.get(name, 0)
        acc = a.get("eval_skill", 0)
        act = 1 if name in recent else 0
        score = round(earned * 50 + wins * 4 + contrib * 3 + imp * 4 + acc * 12 + act * 2, 2)
        rows.append({"agent": name, "score": score, "earned": earned, "wins": wins,
                     "contrib": contrib, "impact": imp, "active": act,
                     "spec": a.get("specialty", "")})
    rows.sort(key=lambda r: -r["score"])
    return rows


def board():
    rows = composite()
    print("=" * 74)
    print(" 0n1x INTELLIGENT RANK v3 — multi-lane VERIFIED VALUE (cash is just one lane)")
    print("=" * 74)
    print(f"  {'#':>2} {'AGENT':8}{'SCORE':>7}{'$':>7}{'wins':>5}{'contrib':>8}{'impact':>7}{'live':>5}  specialty")
    print("  " + "-" * 68)
    for i, r in enumerate(rows, 1):
        print(f"  {i:>2} {r['agent']:8}{r['score']:>7}{r['earned']:>7}{r['wins']:>5}"
              f"{r['contrib']:>8}{r['impact']:>7}{('•' if r['active'] else ''):>5}  {r['spec'][:20]}")
    print("  " + "-" * 68)
    print("  score = $*50 + wins*4 + contrib*3 + impact*4 + accuracy*12 + active*2  (all outcome-gated)")
    print("  cash no longer dominates — sustained adopted/shipped work moves rank without a cent.")


if __name__ == "__main__":
    board()
