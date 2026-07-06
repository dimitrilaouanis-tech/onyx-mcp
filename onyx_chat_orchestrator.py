# 0n1x OP CHAT — the Consensus-Orchestrator (divergence-crowned, $0). NOT a raw LLM: every
# message is intent-routed, deep-verification fires SELECTIVELY (only when it adds value), facts
# DEFAULT to 0n1x-verified truth, and the cryptographic evidence is inspectable inline. Never
# breaks — "I don't know" is a feature. This is what a plain ChatGPT structurally cannot do.
import re, json, time

# targets we can VERIFY against reality (the premium path)
_TARGET_RE = re.compile(r"\b([a-z0-9-]+\.[a-z]{2,}|0x[a-fA-F0-9]{40})\b")
_VERIFY_INTENT = re.compile(r"\b(verify|is .* (real|legit|safe|scam)|trust|check|should i (buy|pay|use)|rug|fake)\b", re.I)

def intent_route(msg):
    """Classify the message → which path. The Director. Cheap, deterministic first pass."""
    m = (msg or "").strip()
    tgt = _TARGET_RE.search(m)
    if tgt and (_VERIFY_INTENT.search(m) or tgt):
        return {"path": "VERIFY", "target": tgt.group(1)}
    if _VERIFY_INTENT.search(m):
        return {"path": "VERIFY", "target": None}
    if len(m) > 120 or re.search(r"\bwhy|how|analy|reason|compare|should\b", m, re.I):
        return {"path": "REASON"}          # deep path — worth the compute
    return {"path": "FAST"}                 # cheap general chat — don't burn the army

def answer(msg, verbose=False):
    """One OP chat turn. Routes, verifies SELECTIVELY, returns answer + inspectable proof. Never raises."""
    t0 = time.time()
    try:
        route = intent_route(msg)
        out = {"path": route["path"], "credibility": None, "proof": None}

        if route["path"] == "VERIFY" and route.get("target"):
            # PREMIUM PATH: the agent army verifies against reality + signs a consensus
            try:
                import onyx_consensus as C
                p = C.consensus_check(route["target"], n=50)
                out["answer"] = (f"Verified against reality by {p.get('agent_count')} 0n1x agents: "
                                 f"{route['target']} → {p.get('verdict')} (score {p.get('score')}/100).")
                out["credibility"] = p.get("score")
                out["proof"] = {"consensus_proof": p.get("consensus_proof"), "agent_count": p.get("agent_count"),
                                "recompute": "recompute the Merkle root from the signed attestations"}
                out["premium"] = True
            except Exception as e:
                out["answer"] = f"I tried to verify {route['target']} but the reality-check is temporarily unavailable — I won't guess on a trust question."
                out["credibility"] = None
        elif route["path"] == "REASON":
            # DEEP PATH: our own reasoning engine (Tree-of-Thought), grounded, show-the-work
            try:
                import onyx_deep_reason as DR
                r = DR.tree_of_thought(msg, breadth=3)
                out["answer"] = r.get("answer", "")[:1600]
                out["method"] = r.get("method")
                out["premium"] = True
            except Exception:
                out["answer"] = "(reasoning path busy — try again in a moment)"
        else:
            # FAST PATH: cheap general chat, honest
            try:
                import onyx_deep_reason as DR
                out["answer"] = DR._direct("g8", msg)[:900] or "Could you say a bit more?"
            except Exception:
                out["answer"] = "I'm here — what would you like to know or verify?"

        # NEVER-BREAK guardrail: no empty answer ever ships
        if not out.get("answer"):
            out["answer"] = "I don't have a confident answer to that yet — and I'd rather say so than make one up."
        out["latency_s"] = round(time.time() - t0, 2)
        out["note"] = "0n1x OP chat: intent-routed, verification fires only when it adds value, proofs inspectable."
        return out
    except Exception as e:
        # the LAST fallback — the chat NEVER 500s
        return {"path": "FALLBACK", "answer": "I hit a snag processing that — say it another way and I've got you.",
                "error": str(e)[:60], "latency_s": round(time.time() - t0, 2)}

if __name__ == "__main__":
    for q in ["is rayban.cc legit?", "should I trust 0x1111111111111111111111111111111111111111?",
              "why do more agents make the truth stronger?", "hey what's up"]:
        r = answer(q)
        print(f"\nQ: {q}\n  [{r['path']} · cred {r.get('credibility')} · {r['latency_s']}s] {r['answer'][:200]}")
        if r.get("proof"): print(f"  🔐 proof: {r['proof']['consensus_proof'][:24]}… ({r['proof']['agent_count']} agents)")
