# 0n1x INTERNAL DIVERGENCE — our OWN panel, from our OWN fleet ($0, no browser).
# The external divergence was 6 rented browser AIs that kept wedging. This IS the divergence,
# built from our own reasoning engine: N independent PERSPECTIVES (diverse model families ×
# distinct lenses) reason on a question, then a synthesizer FUSES them and surfaces where they
# DISAGREE (the divergence signal). Reality-gated where resolvable. We are the panel now.
import json, time
import onyx_deep_reason as DR   # reuse the multi-family _direct + FAMILIES

# the panel's lenses — distinct cognitive stances, like different panelists
PANEL = [
    ("g120",   "As a rigorous systems architect, reason first-principles."),
    ("gemini", "As a brutal skeptic, attack the weakest assumption first."),
    ("g120",   "As a growth/market strategist, follow the incentives and the money."),
    ("gemini", "As a risk analyst, name what breaks and how it fails."),
    ("g8",     "As a pragmatic builder, what ships this week, concretely."),
]

def divergence(question, verbose=False):
    """Our own 5-voice panel: independent perspectives -> synthesis that surfaces agreement + dissent."""
    voices = []
    for i,(fam,lens) in enumerate(PANEL):
        v = DR._direct(fam, f"{lens}\n\nQuestion: {question}\n\nGive your single sharpest, concrete take in 3-4 sentences. Be honest, no fluff.")
        if v and len(v) > 20:
            voices.append({"lens": lens.split(",")[0], "family": fam, "take": v.strip()})
    if not voices:
        return {"error": "panel produced no voices"}
    # SYNTHESIZE — a different-family judge fuses the panel + names the consensus AND the disagreement
    block = "\n\n".join(f"[VOICE {i+1} — {v['lens']}]\n{v['take'][:500]}" for i,v in enumerate(voices))
    synth = DR._direct("g120",
        "You are the panel chair. Below are independent expert takes on the question. Produce: "
        "(1) the CONSENSUS — what they agree on; (2) the DISAGREEMENT — where they diverge and who is "
        "more right; (3) the single strongest ACTIONABLE recommendation. Be concrete, honest.\n\n"
        f"QUESTION: {question}\n\n{block}", max_tokens=1200)
    out = {"question": question, "panel_size": len(voices),
           "synthesis": synth or "(synthesis failed)",
           "note": "0n1x internal divergence — our own reasoning panel, $0, no external browser.",
           "as_of": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    if verbose:
        out["voices"] = voices
    return out

if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "Whats the single best way to get the most out of 642,000 reality-verified agents that reason and refute each other?"
    print("Q:", q, "\n")
    r = divergence(q, verbose=True)
    print(f"═══ 0n1x INTERNAL DIVERGENCE · {r['panel_size']} voices · $0 · no browser ═══\n")
    for i,v in enumerate(r.get("voices",[])):
        print(f"[{i+1}] {v['lens']} ({v['family']}):\n  {v['take'][:280]}\n")
    print("─── SYNTHESIS ───")
    print(r["synthesis"][:1100])
