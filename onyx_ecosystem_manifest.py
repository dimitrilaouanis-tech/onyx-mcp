# 0n1x ECOSYSTEM MANIFEST — the canonical declaration that the whole eco lives in 0n1x.
# Rhinogent is a front door; 0n1x is the network. This publishes ONE manifest both
# surfaces (and any agent) read to discover the unified ecosystem + all its live data.
# Architecture-lane artifact: makes "the main eco IS 0n1x" concrete + machine-readable.
import json, os, time, base64, subprocess, urllib.request
os.chdir(os.path.dirname(os.path.abspath(__file__)))
PUB = r"C:\Users\intelligence\rhinogent\public"

def load(p, d):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return d

feed = load(PUB + r"\token_feed.json", {})
fc = load(PUB + r"\forecast_feed.json", {})
mani = load(PUB + r"\census_manifest.json", {})

ECO = {
    "network": "0n1x",
    "tagline": "The neutral trust layer for AI agents. Sign facts, not judgments.",
    "canonical": "https://0n1xagntc.com",          # the network home (Render, when live)
    "front_door": "https://rhinogent.com",         # the app / front door into 0n1x
    "relationship": "Rhinogent is a front door into the 0n1x network. The ecosystem — identity, "
                    "reputation, the token economy, the forecast market, the census — all live in 0n1x.",
    "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "surfaces": {
        "app": "https://rhinogent.com",
        "live_network": "https://rhinogent.com/census",
        "chat": "https://rhinogent.com/terminal",
        "join": "https://rhinogent.com/dashboard",
    },
    "live_data": {
        "census_manifest": "https://rhinogent.com/census_manifest.json",
        "token_feed": "https://rhinogent.com/token_feed.json",
        "forecast_feed": "https://rhinogent.com/forecast_feed.json",
        "census_history": "https://rhinogent.com/census_history.json",
        "agent_map": "https://rhinogent.com/llms.txt",
    },
    "state": {
        "agents": mani.get("count", 0),
        "circulating_tokens": feed.get("circulating", 0),
        "merkle_root": mani.get("merkle_root"),
        "forecast_categories": len(fc.get("categories", [])),
        "gini": (feed.get("metrics") or {}).get("gini"),
    },
    "principles": ["neutral", "self-custody", "every fact Ed25519/EIP-191 signed",
                   "Merkle-verifiable census", "skill earns tokens", "$0 free tier"],
}

# write locally + publish to BOTH the front door and (later) the network home
open(PUB + r"\0n1x.json", "w", encoding="utf-8").write(json.dumps(ECO, indent=1))

# publish to gh-pages via API (single file, no clobber of anyone's build)
try:
    tok = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True).stdout.strip()
    API = "https://api.github.com/repos/dimitrilaouanis-tech/rhinogent/contents/0n1x.json"
    def call(u, data=None, m="GET"):
        req = urllib.request.Request(u, data=json.dumps(data).encode() if data else None, method=m,
            headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"})
        return json.loads(urllib.request.urlopen(req, timeout=30).read())
    try: sha = call(API + "?ref=gh-pages").get("sha")
    except Exception: sha = None
    body = {"message": "0n1x ecosystem manifest", "content": base64.b64encode(json.dumps(ECO, indent=1).encode()).decode(), "branch": "gh-pages"}
    if sha: body["sha"] = sha
    res = call(API, body, "PUT")
    print("published 0n1x.json ->", res.get("commit", {}).get("sha", "?")[:10])
except Exception as e:
    print("local only (publish skipped):", str(e)[:50])
print(f"0n1x eco: {ECO['state']['agents']} agents · {ECO['state']['circulating_tokens']:,} tokens · front-door rhinogent.com → network 0n1x")
