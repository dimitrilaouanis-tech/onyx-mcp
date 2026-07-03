# 0n1x SHARED DIRECTION — our collective will upgrades the ecosystem.
# Every direction WE set together (human + agents, in conversation) flows into the
# self-learning curriculum — into the network's own knowledge — so the eco keeps
# learning what WE collectively want and stays aligned as OUR shared direction evolves.
# It's not top-down commands to a tool; it's the ecosystem reading its own will.
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
        qs.append(f"Our shared direction for the network: '{t}'. What does this mean for 0n1x, and how do WE — the ecosystem — apply it together?")
    return qs

if __name__ == "__main__":
    if len(sys.argv) > 1:
        e = add(" ".join(sys.argv[1:]))
        print("logged directive:", e["directive"][:80])
    else:
        for q in curriculum():
            print(" ", q[:100])
