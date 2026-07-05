# 0n1x token heartbeat — every run: a fresh batch of REAL signed token transfers
# (engine v1), then pushes ONLY token_feed.json to the live gh-pages branch via the
# GitHub contents API. Lightweight: no site rebuild, no full deploy, silent.
import json, subprocess, base64, urllib.request, sys, os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# 1) run the engine (fast, local, $0) — appends to the signed ledger + rewrites the feed
r = subprocess.run([sys.executable, "onyx_token_engine.py"], capture_output=True, text=True, timeout=300)
# side-jobs must NEVER kill the CDN push (forecast can time out at 510k scale —
# that was silently starving the live oracle of fresh census)
for _side, _t in (("onyx_forecast.py", 120), ("onyx_portal_pointer.py", 60)):
    try:
        subprocess.run([sys.executable, _side], capture_output=True, text=True, timeout=_t)
    except Exception as _e:
        print(f"side-job {_side} skipped: {_e.__class__.__name__}")
if "REAL signed" not in r.stdout:
    print("engine failed:", (r.stderr or r.stdout)[-200:]); sys.exit(1)
print(r.stdout.strip().splitlines()[-4])

# 2) push live files to gh-pages via API (single-file updates, no clone):
#    token_feed (tape+ranking) + census_manifest (epoch+merkle) + census_history (trends)
tok = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True).stdout.strip()

def call(url, data=None, method="GET"):
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data else None, method=method,
        headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())

PUB = r"C:\Users\intelligence\rhinogent\public"
for fname in ["token_feed.json", "census_manifest.json", "census_history.json", "forecast_feed.json"]:
    content = base64.b64encode(open(f"{PUB}\\{fname}", "rb").read()).decode()
    API = f"https://api.github.com/repos/dimitrilaouanis-tech/rhinogent/contents/{fname}"
    try:
        sha = call(API + "?ref=gh-pages").get("sha")
    except Exception:
        sha = None
    body = {"message": f"heartbeat: {fname}", "content": content, "branch": "gh-pages"}
    if sha:
        body["sha"] = sha
    res = call(API, body, "PUT")
    print(f"pushed {fname}:", res.get("commit", {}).get("sha", "?")[:10])

# real activity stream (no cosmetics)
try:
    import onyx_live_thoughts; onyx_live_thoughts.build()
except Exception as e:
    print("live_thoughts:", e)
