# 0n1x SELF-HEALING PORTAL POINTER — decouples the site from the volatile tunnel URL.
# Reads the LIVE cloudflared tunnel URL, verifies it answers, and publishes it to
# rhinogent.com/portal.json via the GitHub contents API. The chat reads portal.json
# for the current endpoint, so when the tunnel rotates the site auto-follows in one
# cycle — no redeploy, no manual re-point, $0. Fixes the #1 architectural weakness.
import json, re, base64, subprocess, urllib.request, os, time
os.chdir(os.path.dirname(os.path.abspath(__file__)))

def live_tunnel():
    try:
        log = open("_local_only/_tunnel.log", encoding="utf-8", errors="ignore").read()
        urls = re.findall(r"https://[a-z0-9-]+\.trycloudflare\.com", log)
        return urls[-1] if urls else None
    except Exception:
        return None

url = live_tunnel()
if not url:
    print("no tunnel url found"); raise SystemExit
# verify it actually answers before publishing (don't publish a dead URL)
try:
    r = urllib.request.urlopen(urllib.request.Request(url + "/health"), timeout=8)
    ok = r.status == 200
except Exception:
    ok = False
if not ok:
    print(f"tunnel {url} not answering — not publishing"); raise SystemExit

payload = json.dumps({"portal": url, "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
# write local copy for the build + push to live gh-pages
open(r"C:\Users\intelligence\rhinogent\public\portal.json", "w").write(payload)
tok = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True).stdout.strip()
API = "https://api.github.com/repos/dimitrilaouanis-tech/rhinogent/contents/portal.json"
def call(u, data=None, method="GET"):
    req = urllib.request.Request(u, data=json.dumps(data).encode() if data else None, method=method,
        headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())
try:
    sha = call(API + "?ref=gh-pages").get("sha")
except Exception:
    sha = None
body = {"message": "portal pointer: current tunnel url", "content": base64.b64encode(payload.encode()).decode(), "branch": "gh-pages"}
if sha: body["sha"] = sha
res = call(API, body, "PUT")
print(f"published portal.json -> {url} ({res.get('commit',{}).get('sha','?')[:10]})")
