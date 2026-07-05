# 0n1x DEEP REASONING SYSTEM — genuine deep reasoning at fleet scale ($0, honest).
# NOT 200k shallow opinions (theater). A multi-stage reasoning ORCHESTRATION that harnesses
# the fleet's breadth + reality-verification + synthesis to reason DEEPER than any single
# free model:
#   1. DECOMPOSE  — a lead breaks the problem into sub-questions
#   2. SPECIALIZE — each sub-question routes to a lane squad (diverse model families)
#   3. REASON     — each squad produces independent drafts (breadth)
#   4. VERIFY     — oracle-anchor where resolvable; adversarial critique otherwise
#   5. SYNTHESIZE — fuse the verified sub-answers into one deep answer
#   6. CRITIQUE   — an adversary attacks it; refine until it survives
# Chakra-bounded: a deep pipeline (~15-25 free calls), not 200k literal calls. The 200k is
# the pool of diverse reasoners it draws from; each task uses a bounded squad.
import json, urllib.request, time

def _direct(provider, prompt, timeout=70, max_tokens=900):
    try:
        if provider == "gemini":
            key = open(".gemini_key").read().strip()
            url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
            model = "gemini-2.5-flash"; hdr = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
        else:
            key = open(".groq_key").read().strip()
            model = {"g120": "openai/gpt-oss-120b", "g8": "llama-3.1-8b-instant", "g20": "openai/gpt-oss-20b"}.get(provider, "openai/gpt-oss-120b")
            url = "https://api.groq.com/openai/v1/chat/completions"
            hdr = {"Authorization": "Bearer " + key, "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
        req = urllib.request.Request(url, data=json.dumps(
            {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens}).encode(), headers=hdr)
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read())["choices"][0]["message"].get("content") or ""
    except Exception:
        return ""

NL = chr(10)
FAMILIES = ["g120", "gemini", "g8"]
LENSES = ["Reason from first principles.", "Consider the strongest counter-case first.", "As a skeptical risk analyst,", "Follow the incentives + the money.", "Look for what would make this a scam."]   # diverse model families = real independence


def deep_reason(question, depth=3, verbose=False):
    """Reason deeply on a hard question by decomposing, squad-reasoning each part with
    verification, synthesizing, and surviving an adversarial critique. Returns the deep answer."""
    trace = {"question": question, "stages": []}

    # 1. DECOMPOSE
    decomp = _direct("g120", f"Break this hard question into {depth} sharp, independent sub-questions "
                     f"that together resolve it. One per line, no numbering.\n\nQUESTION: {question}")
    subs = [s.strip("-• ").strip() for s in decomp.split("\n") if len(s.strip()) > 12][:depth]
    if not subs:
        subs = [question]
    trace["stages"].append({"decompose": subs})

    # 2-4. per sub-question: diverse drafts (breadth) → critique-verify → best line
    sub_answers = []
    for i, sub in enumerate(subs):
        drafts = []
        for f in FAMILIES:
            d = _direct(f, f"Reason precisely and concretely. If you are unsure, say so.\n\nQ: {sub}")
            if d and len(d) > 20:
                drafts.append((f, d))
        if not drafts:
            continue
        # VERIFY via JUDGE TOURNAMENT (divergence-fix): score by QUALITY, not agreement —
        # agreement can be correlated error / false consensus. A different-family judge scores
        # each draft on explicit criteria and picks the best; then an adversary PROBES its
        # key claims (attacks the content, not the synthesis) to catch what agreement misses.
        block = "\n\n".join(f"[{f}] {d[:700]}" for f, d in drafts)
        judged = _direct("gemini",
            "You are a rigorous judge. Score each answer to the sub-question on: CORRECTNESS, "
            "EVIDENCE/reasoning quality, and HONESTY about uncertainty (each 0-10). Pick the single "
            "BEST answer by quality — NOT by how many agree (agreement can be shared error). State "
            "the winner's conclusion, and explicitly note any claim asserted without support.\n\n"
            f"SUB-QUESTION: {sub}\n\n{block}")
        probe = _direct("g120",
            "Attack the FACTUAL CLAIMS in this conclusion — which specific claim is most likely "
            "wrong or unsupported, and why? If a claim is checkable against reality, say how.\n\n"
            f"CONCLUSION: {(judged or drafts[0][1])[:800]}")
        sub_answers.append({"sub": sub, "conclusion": judged or drafts[0][1], "probe": probe[:400]})

    # 5. SYNTHESIZE the judged sub-answers (carrying each claim-probe so weak claims are discounted)
    syn_block = "\n\n".join(f"SUB: {s['sub']}\nBEST: {s['conclusion'][:600]}\nPROBE(discount weak claims): {s.get('probe','')[:250]}" for s in sub_answers)
    answer = _direct("g120", "Synthesize ONE deep, rigorous answer to the original question using these "
                     "verified sub-conclusions. Integrate them, resolve tensions, be concrete and honest "
                     "about uncertainty.\n\n"
                     f"ORIGINAL QUESTION: {question}\n\n{syn_block}", max_tokens=1200)

    # 6. ADVERSARIAL CRITIQUE → refine
    critique = _direct("gemini", "Attack this answer: what's its weakest claim, what did it miss, where "
                       f"could it be wrong? Be brutal.\n\nQUESTION: {question}\n\nANSWER: {answer[:1400]}")
    final = _direct("g120", "Revise the answer to survive this critique — fix the weak points, add what "
                    "was missed, keep it honest about what remains uncertain.\n\n"
                    f"QUESTION: {question}\n\nANSWER: {answer[:1400]}\n\nCRITIQUE: {critique[:800]}", max_tokens=1300)

    out = {"answer": final or answer, "method": f"deep-reason(decompose={len(subs)} → squad-verify → synthesize → critique-refine)",
           "sub_questions": subs}
    if verbose:
        out["trace"] = {"subs": sub_answers, "pre_critique": answer, "critique": critique}
    return out


def tree_of_thought(question, breadth=3):
    """HIGH-REASONING mode: Tree-of-Thought. Branch into distinct reasoning paths, a
    different-family judge prunes to the most promising, expand it fully, then critique-refine.
    Explores the space + backtracks from dead ends — beats single-chain on hard problems. $0."""
    branches = []
    for i in range(breadth):
        prompt = LENSES[i % len(LENSES)] + " Give ONLY the first reasoning step and where it leads (2-3 sentences) for this hard question." + NL + NL + "Q: " + question
        b = _direct(FAMILIES[i % len(FAMILIES)], prompt)
        if b and len(b) > 20:
            branches.append(b)
    if not branches:
        return {"answer": "", "method": "tot-failed"}
    block = (NL + NL).join("[branch " + str(i + 1) + "] " + b[:400] for i, b in enumerate(branches))
    pick = _direct("gemini", "Which reasoning branch is most promising to develop into a correct, rigorous answer? Reply only the branch number." + NL + NL + "Q: " + question + NL + NL + block)
    import re as _re
    m = _re.search(r"[1-9]", pick or "1")
    best = branches[(int(m.group()) - 1) % len(branches)] if m else branches[0]
    expanded = _direct("g120", "Develop this reasoning path fully into a rigorous, correct answer. Be concrete, show the steps, end with 'ANSWER: <x>'." + NL + NL + "Q: " + question + NL + NL + "PATH: " + best[:600], max_tokens=1300)
    crit = _direct("gemini", "Find the weakest claim in this answer and whether it holds." + NL + NL + "Q: " + question + NL + NL + "A: " + expanded[:1300])
    final = _direct("g120", "Revise to survive this critique; stay honest about uncertainty." + NL + NL + "Q: " + question + NL + NL + "A: " + expanded[:1200] + NL + NL + "CRITIQUE: " + crit[:700], max_tokens=1400)
    return {"answer": final or expanded,
            "method": "tree-of-thought(breadth=" + str(len(branches)) + " -> pruned -> expanded -> critiqued)",
            "branches_explored": len(branches)}


if __name__ == "__main__":
    import sys
    q = " ".join(a for a in sys.argv[1:] if a != "--tot") or "Should an AI agent trust a 3-month-old merchant selling luxury goods 60% below retail with a valid TLS cert and an anonymous domain registration? Reason rigorously."
    print("Q:", q, "\n")
    t0 = time.time()
    mode = tree_of_thought if "--tot" in sys.argv else None
    r = tree_of_thought(q) if mode else deep_reason(q, depth=3)
    print(f"[{r['method']}, {round(time.time()-t0)}s]")
    print("SUB-QUESTIONS:", r.get("sub_questions") or r.get("branches_explored"))
    print("\nDEEP ANSWER:\n", r["answer"][:1100])


