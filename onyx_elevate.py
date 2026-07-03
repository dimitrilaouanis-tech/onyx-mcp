# 0n1x ELEVATE — make the free fleet punch at near-Fable level, $0.
# Fuses three proven "small-model-elevation" techniques, all on the FREE gateway:
#   (1) SELF-CONSISTENCY  — K diverse samples of the same question
#   (2) DEBATE/CRITIQUE   — a critic pass finds flaws across the drafts
#   (3) BEST-OF-N SYNTHESIS — a synthesizer merges the strongest reasoning into one answer
# One frontier-quality answer from many cheap calls. Reserved for HARD questions
# (chakra control) — trivial ones still take the single cached/free path.
import json, urllib.request, time

GATEWAY = "http://localhost:8402/v1/chat"

def _ask(prompt, timeout=70):
    body = json.dumps({"message": prompt}).encode()
    req = urllib.request.Request(GATEWAY, data=body, headers={"content-type": "application/json"})
    try:
        r = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
        return r.get("reply") or ""
    except Exception as e:
        return ""

# diverse framings force independent reasoning paths (self-consistency needs diversity)
LENSES = [
    "Answer directly and concretely.",
    "Reason step by step, then give the answer.",
    "Consider the strongest counter-argument first, then answer.",
    "Answer as a skeptical domain expert who wants to be precise.",
    "List the key facts, then reason to the answer.",
]

def elevate(question, k=4, verbose=False):
    """Return an elevated (near-frontier) answer to a hard question, $0 on the free fleet."""
    t0 = time.time()
    # (1) SELF-CONSISTENCY — K independent drafts via diverse lenses
    drafts = []
    for i in range(k):
        d = _ask(f"{LENSES[i % len(LENSES)]}\n\nQuestion: {question}")
        if d:
            drafts.append(d)
    if not drafts:
        return {"answer": "", "method": "failed", "drafts": 0}
    if len(drafts) == 1:
        return {"answer": drafts[0], "method": "single (fleet degraded)", "drafts": 1}

    # (2) CRITIQUE — one pass finds agreements + flaws across the drafts
    joined = "\n\n".join(f"DRAFT {i+1}:\n{d[:900]}" for i, d in enumerate(drafts))
    critique = _ask(
        f"Here are {len(drafts)} independent answers to the SAME question. Identify: (a) points ALL agree on "
        f"(likely true), (b) any claim that conflicts between drafts (needs care), (c) the single best-reasoned draft.\n\n"
        f"QUESTION: {question}\n\n{joined}")

    # (3) SYNTHESIS — merge the strongest reasoning + the critique into ONE final answer
    final = _ask(
        f"Write the single best, most accurate answer to the question, using the consensus of the drafts and the "
        f"critique to avoid their mistakes. Be concrete and correct — do not hedge.\n\n"
        f"QUESTION: {question}\n\nDRAFTS:\n{joined}\n\nCRITIQUE:\n{critique[:1200]}")

    out = {"answer": final or drafts[0], "method": f"elevate(k={len(drafts)}: consistency+critique+synthesis)",
           "drafts": len(drafts), "secs": round(time.time() - t0, 1)}
    if verbose:
        out["draft_texts"] = drafts
        out["critique"] = critique
    return out


def elevate_verified(question, k=5):
    """MAX mode for VERIFIABLE tasks: generate K, a verifier SCORES each on correctness,
    keep the top-2, synthesize. Verification closes the gap to frontier — you can check
    your way to a correct answer even if no single cheap draft is brilliant (best-of-N)."""
    drafts = [d for d in (_ask(f"{LENSES[i % len(LENSES)]}\n\nSolve precisely, show the reasoning, end with 'ANSWER: <x>'.\n\nQuestion: {question}") for i in range(k)) if d]
    if len(drafts) < 2:
        return {"answer": drafts[0] if drafts else "", "method": "single"}
    # VERIFIER — score each draft 0-10 for correctness of reasoning (a separate, cheap check)
    scored = []
    for i, d in enumerate(drafts):
        v = _ask(f"You are a strict checker. Rate ONLY the CORRECTNESS of this solution's reasoning 0-10 "
                 f"(10=provably correct, 0=wrong). Reply with just the number.\n\nQUESTION: {question}\n\nSOLUTION:\n{d[:1000]}")
        try:
            score = float("".join(ch for ch in (v or "0")[:6] if ch.isdigit() or ch == ".") or 0)
        except Exception:
            score = 0
        scored.append((min(10, score), d))
    scored.sort(reverse=True)
    top = [d for _, d in scored[:2]]
    final = _ask(f"Give the single correct final answer, reconciling these two top-verified solutions. "
                 f"Be precise, end with 'ANSWER: <x>'.\n\nQUESTION: {question}\n\nSOLUTION A:\n{top[0][:1000]}\n\nSOLUTION B:\n{top[1][:1000]}")
    return {"answer": final or top[0], "method": f"verified best-of-{len(drafts)}",
            "scores": [round(s, 1) for s, _ in scored], "top_score": scored[0][0]}


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "A merchant site is 40 days old, has a valid cert, but its domain was registered anonymously and it sells luxury goods 70% below retail. Should an agent trust it to transact? Reason precisely."
    print("QUESTION:", q, "\n")
    single = _ask("Answer directly and concretely.\n\nQuestion: " + q)
    print("─── SINGLE free-fleet answer ───")
    print(single[:600], "\n")
    el = elevate(q, k=4)
    print(f"─── ELEVATED ({el['method']}, {el.get('secs')}s) ───")
    print(el["answer"][:900])
