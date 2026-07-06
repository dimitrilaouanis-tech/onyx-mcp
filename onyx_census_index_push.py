# Census-index pusher — syncs rhinogent/public/census_idx/*.json to gh-pages so the
# live oracle can attest ANY citizen (depth beyond the top-120 tape). Pushes only
# buckets whose content differs from the CDN copy (git blob-sha compare), so a
# typical run is a handful of PUTs, worst case 256. Scheduled hourly (OnyxCensusIdx).
import base64
import hashlib
import json
import os
import subprocess
import urllib.request

os.chdir(os.path.dirname(os.path.abspath(__file__)))
PUB = r"C:\Users\intelligence\rhinogent\public\census_idx"
REPO = "dimitrilaouanis-tech/rhinogent"

tok = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True).stdout.strip()


def call(url, data=None, method="GET"):
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data else None,
        method=method,
        headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


# one tree listing instead of 256 GETs
remote = {}
try:
    tree = call(f"https://api.github.com/repos/{REPO}/git/trees/gh-pages?recursive=1")
    remote = {e["path"]: e["sha"] for e in tree.get("tree", [])
              if e["path"].startswith("census_idx/")}
except Exception as e:
    print("tree listing failed (will PUT blind):", str(e)[:80])

pushed = skipped = failed = 0
for fname in sorted(os.listdir(PUB)):
    if not fname.endswith(".json"):
        continue
    raw = open(os.path.join(PUB, fname), "rb").read()
    path = f"census_idx/{fname}"
    if remote.get(path) == blob_sha(raw):
        skipped += 1
        continue
    body = {"message": f"census-idx: {fname}", "branch": "gh-pages",
            "content": base64.b64encode(raw).decode()}
    if path in remote:
        body["sha"] = remote[path]
    try:
        call(f"https://api.github.com/repos/{REPO}/contents/{path}", body, "PUT")
        pushed += 1
    except Exception as e:
        failed += 1
        print(f"PUT {fname} failed: {str(e)[:60]}")

print(f"census index push: {pushed} pushed, {skipped} unchanged, {failed} failed")
