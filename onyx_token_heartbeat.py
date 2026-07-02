# 0n1x token heartbeat — every run: a fresh batch of REAL signed token transfers
# (engine v1), then pushes ONLY token_feed.json to the live gh-pages branch via the
# GitHub contents API. Lightweight: no site rebuild, no full deploy, silent.
import json, subprocess, base64, urllib.request, sys, os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# 1) run the engine (fast, local, $0) — appends to the signed ledger + rewrites the feed
r = subprocess.run([sys.executable, "onyx_token_engine.py"], capture_output=True, text=True, timeout=180)
if "REAL signed" not in r.stdout:
    print("engine failed:", (r.stderr or r.stdout)[-200:]); sys.exit(1)
print(r.stdout.strip().splitlines()[-4])

# 2) push token_feed.json to gh-pages via API (single-file update, no clone)
feed_path = r"C:\Users\intelligence\rhinogent\public\token_feed.json"
content = base64.b64encode(open(feed_path, "rb").read()).decode()
tok = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True).stdout.strip()
API = "https://api.github.com/repos/dimitrilaouanis-tech/rhinogent/contents/token_feed.json"

def call(url, data=None, method="GET"):
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data else None, method=method,
        headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())

try:
    sha = call(API + "?ref=gh-pages").get("sha")
except Exception:
    sha = None
body = {"message": "heartbeat: fresh signed token transactions", "content": content, "branch": "gh-pages"}
if sha:
    body["sha"] = sha
res = call(API, body, "PUT")
print("pushed live:", res.get("commit", {}).get("sha", "?")[:10])
