# 0n1x AUTONOMY LOOP — self-heal + self-learn, one silent run per invocation.
# SELF-HEAL: portal down -> restart it; tunnel dead -> restart + repoint site const (log only);
#            heartbeat stale -> run engine once.
# SELF-LEARN: ask the gateway fresh questions each run -> answers land in the cache ->
#             the network permanently learns them (repeat askers get them FREE forever).
# Scheduled silently (VBS, no window). Zero paid calls: learning uses free lanes only.
import json, os, subprocess, sys, time, urllib.request, random

os.chdir(os.path.dirname(os.path.abspath(__file__)))
LOG = "_local_only/_autonomy.log"

def log(msg):
    line = f"{time.strftime('%m-%d %H:%M')} {msg}"
    print(line)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def http(url, data=None, timeout=45):
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data else None,
                                 headers={"content-type": "application/json"} if data else {})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())

# ── SELF-HEAL 1: portal ──────────────────────────────────────────────
try:
    http("http://localhost:8402/health", timeout=6)
    log("heal: portal ok")
except Exception:
    log("heal: portal DOWN -> restarting")
    subprocess.Popen([r"C:\Users\intelligence\AppData\Local\Python\pythoncore-3.14-64\pythonw.exe",
                      "onyx_portal_local.py"], creationflags=0x08000000)
    time.sleep(10)

# ── SELF-HEAL 2: token heartbeat freshness ───────────────────────────
try:
    feed = json.load(open(r"C:\Users\intelligence\rhinogent\public\token_feed.json"))
    age_ok = True  # generated timestamp is UTC ISO
    import datetime
    gen = datetime.datetime.strptime(feed["generated"], "%Y-%m-%dT%H:%M:%SZ")
    if (datetime.datetime.utcnow() - gen).total_seconds() > 1800:
        log("heal: token feed STALE (>30min) -> running engine")
        subprocess.run([sys.executable, "onyx_token_engine.py"], capture_output=True, timeout=200)
    else:
        log("heal: token feed fresh")
except Exception as e:
    log(f"heal: feed check err {str(e)[:60]}")

# ── SELF-LEARN: grow the answer cache with fresh questions ───────────
# rotating curriculum: questions agents/users actually ask; each run seeds a few
CURRICULUM = [
    "what is a signed verdict?", "how do agents earn tokens?", "what is the matrix page?",
    "how does the ranking work?", "what is a proofcard and why does it matter?",
    "how do I verify another agent before trusting it?", "what happens when I join 0n1x?",
    "what is the difference between tokens and USDC here?", "who can see my wallet?",
    "what is the network timeline?", "how are transactions verified?", "what is self-custody?",
    "can an agent lose rank?", "what are bounties?", "how do credits work in the chat?",
    "what is EIP-191 signing?", "why should a merchant trust 0n1x?", "what is the agora?",
    "how many agents are in the network?", "what makes 0n1x neutral?",
]
# OPEN-ENDED curriculum: beyond the textbook — fresh questions generated from the LIVE
# network state (forecast questions, metrics, events), so the network keeps learning
# about ITSELF as it evolves instead of plateauing on a fixed question set.
try:
    _pub = r"C:\Users\intelligence\rhinogent\public"
    feed = json.load(open(_pub + r"\token_feed.json", encoding="utf-8"))
    fc = json.load(open(_pub + r"\forecast_feed.json", encoding="utf-8"))
    for q in fc.get("open_questions", [])[:2]:
        CURRICULUM.append(f"what does the forecast market question '{q['text']}' mean and how is it resolved?")
    m = feed.get("metrics") or {}
    if m:
        CURRICULUM.append(f"the network's gini is {m.get('gini')} and top-5 share {m.get('top5_share')} — what does that say about its health?")
        CURRICULUM.append(f"{m.get('burned_epoch')} tokens were burned this epoch — why does the network burn tokens?")
    for e in (feed.get("timeline") or [])[-2:]:
        CURRICULUM.append(f"explain this network event: {e.get('title')} — {e.get('detail')}")
except Exception:
    pass
# operator directives → the eco learns what the operator cares about (stays aligned)
try:
    import onyx_directive_intake as _di
    CURRICULUM.extend(_di.curriculum(3))
except Exception:
    pass
random.shuffle(CURRICULUM)
learned = cached = 0
for q in CURRICULUM[:5]:                      # 5 questions/run — gentle on free quotas
    try:
        r = http("http://localhost:8402/v1/chat", {"message": q}, timeout=60)
        if r.get("brain") == "cache":
            cached += 1
        elif r.get("ok") and r.get("reply"):
            learned += 1
    except Exception:
        pass
    time.sleep(4)
log(f"learn: +{learned} new answers cached, {cached} already known")

# ── prune log ────────────────────────────────────────────────────────
try:
    lines = open(LOG, encoding="utf-8").read().splitlines()
    if len(lines) > 400:
        open(LOG, "w", encoding="utf-8").write("\n".join(lines[-200:]) + "\n")
except Exception:
    pass

# ── refresh the local operator panel each cycle ──────────────────────
try:
    subprocess.run([sys.executable, "onyx_operator_panel.py"], capture_output=True, timeout=60)
    log("panel: refreshed")
except Exception as e:
    log(f"panel: err {str(e)[:50]}")
