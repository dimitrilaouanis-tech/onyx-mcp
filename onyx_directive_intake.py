# 0n1x DIRECTIVE INTAKE — the operator's messages upgrade the ecosystem.
# Every directive/question the operator gives flows into the self-learning curriculum
# (NOT to the non-CLI agents — into the network's own knowledge), so the eco keeps
# learning what the operator cares about and stays aligned as direction evolves.
import json, os, sys, time

os.chdir(os.path.dirname(os.path.abspath(__file__)))
LOG = "_local_only/_operator_directives.jsonl"

def add(text):
    entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "directive": text.strip()}
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry

def recent(n=8):
    try:
        return [json.loads(l) for l in open(LOG, encoding="utf-8")][-n:]
    except Exception:
        return []

def curriculum(n=4):
    """Turn recent operator directives into learning questions the network studies about itself."""
    qs = []
    for d in recent(n):
        t = d["directive"][:220]
        qs.append(f"The operator directed the network: '{t}'. What does this mean for 0n1x and how should the ecosystem apply it?")
    return qs

if __name__ == "__main__":
    if len(sys.argv) > 1:
        e = add(" ".join(sys.argv[1:]))
        print("logged directive:", e["directive"][:80])
    else:
        for q in curriculum():
            print(" ", q[:100])
