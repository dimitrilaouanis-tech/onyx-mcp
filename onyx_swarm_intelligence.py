# 0n1x SWARM INTELLIGENCE — turn VOLUME into INTELLIGENCE (not theater).
# The lesson: raw volume of shallow opinions = noise. Volume becomes intelligence when
# every contribution is (1) INDEPENDENT, (2) VERIFIABLE/scoreable, (3) aggregated with
# SKILL-WEIGHTING. This generalizes the forecast market (which already works) to any
# question. More agents → a BETTER answer (Condorcet), because the ensemble verifies
# and skill-weights instead of averaging mush.
import json, urllib.request, time

GATEWAY = "http://localhost:8402/v1/chat"

def _ask(prompt, timeout=70):
    try:
        req = urllib.request.Request(GATEWAY, data=json.dumps({"message": prompt}).encode(),
                                     headers={"content-type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read()).get("reply") or ""
    except Exception:
        return ""

LENSES = ["Answer directly.", "Reason step by step.", "Consider the counter-argument first.",
          "As a skeptical expert.", "List the facts, then conclude.", "From first principles.",
          "What would break this? then answer.", "The contrarian-but-correct take."]

def swarm_answer(question, volume=8, verbose=False):
    """VOLUME → INTELLIGENCE: N independent drafts (the volume), each VERIFIER-SCORED
    (turns opinion into a scoreable claim), then SKILL-WEIGHTED synthesis. Quality rises
    with N — the more of the swarm you engage, the better the answer. Honest Condorcet."""
    # 1. VOLUME — N genuinely diverse independent drafts (diversity = independence)
    drafts = []
    for i in range(volume):
        d = _ask(f"{LENSES[i % len(LENSES)]}\n\nQuestion: {question}")
        if d and len(d) > 20:
            drafts.append(d)
    if len(drafts) < 2:
        return {"answer": drafts[0] if drafts else "", "n": len(drafts), "method": "insufficient volume"}

    # 2. VERIFY — each draft scored 0-10 for correctness+substance (turns opinion into a claim
    #    that can be judged, not just counted). This is what kills the shallow-noise problem.
    scored = []
    for d in drafts:
        v = _ask(f"Score this answer's CORRECTNESS and SUBSTANCE 0-10 (10=rigorous+right, "
                 f"0=vague/wrong). Reply the number only.\n\nQ: {question}\n\nA: {d[:900]}")
        try:
            s = min(10, float("".join(c for c in (v or "0")[:5] if c.isdigit() or c == ".") or 0))
        except Exception:
            s = 0
        scored.append((s, d))
    scored.sort(reverse=True)

    # 3. SKILL-WEIGHTED SYNTHESIS — keep only drafts that beat the median score (filter the
    #    mush), synthesize weighting the highest-scored reasoning. Volume that PASSED verification.
    med = scored[len(scored) // 2][0]
    survivors = [d for s, d in scored if s >= med and s > 0][:4] or [scored[0][1]]
    block = "\n\n".join(f"[verified {scored[i][0]}/10] {d[:700]}" for i, d in enumerate(survivors))
    final = _ask(f"Synthesize the single strongest, most correct answer from these VERIFIED drafts "
                 f"(higher scores = more weight). Be rigorous and concrete, no hedging.\n\n"
                 f"Q: {question}\n\n{block}")
    out = {"answer": final or survivors[0], "n": len(drafts), "survivors": len(survivors),
           "top_score": scored[0][0], "median_score": med,
           "method": f"swarm-intelligence(volume={len(drafts)} → verified {len(survivors)} → synthesis)"}
    if verbose:
        out["scores"] = [round(s, 1) for s, _ in scored]
    return out


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "What is the single highest-leverage move to make 0n1x's premium answers genuinely stronger?"
    print("Q:", q, "\n")
    r = swarm_answer(q, volume=6, verbose=True)
    print(f"[{r['method']}] scores={r.get('scores')}")
    print(r["answer"][:800])
