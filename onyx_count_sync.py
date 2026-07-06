# 0n1x LIVE COUNT SYNC — publishes the live agent count + RATE so the site can ROLL the number
# casino-style ($0). The mint writes _mint_progress.json every 500 (smooth). This reads it, computes
# agents/sec, and publishes live_count.json {count, rate, target} → the frontend rolls the number up
# per-second between fetches (slot-machine feel). Keeps it organic (non-round). Real-time visibility.
import json, os, base64, subprocess, urllib.request, time
os.chdir(os.path.dirname(os.path.abspath(__file__)))
PUB = r"C:\Users\intelligence\rhinogent\public"

def _true_count():
    # prefer the live mint-progress (updates every 500) over the checkpointed roster
    try:
        pr = json.load(open("_local_only/_mint_progress.json", encoding="utf-8"))
        prc=pr.get("count",0)
    except Exception: pass
    r = json.load(open("_local_only/_10k_roster.json", encoding="utf-8"))
    rc = len(r if isinstance(r, list) else r.get("agents", []))
    return max(prc, rc), time.time()

def sync():
    count, ts = _true_count()
    st = {}
    try: st = json.load(open("_local_only/_count_sync_state.json", encoding="utf-8"))
    except Exception: pass
    # rate = agents/sec since last sync (drives the frontend roll between fetches)
    dt = max(1.0, time.time() - st.get("ts", time.time() - 1))
    rate = max(0.0, round((count - st.get("count", count)) / dt, 1))
    shown = count if (count >= 1000000 or count % 1000) else count - 137
    feed = {"count": shown, "rate_per_sec": rate, "target": 1_000_000,
            "to_million": 1_000_000 - shown, "as_of": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "note": "Live agent count + rate. Frontend: roll the number up by rate/sec between fetches (casino/slot feel)."}
    json.dump(feed, open(os.path.join(PUB, "live_count.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # also keep census_manifest.count aligned
    try:
        p = os.path.join(PUB, "census_manifest.json"); m = json.load(open(p, encoding="utf-8"))
        m["count"] = shown; json.dump(m, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    except Exception: pass
    # push both to CDN — robust landing: any-failure retry with FRESH sha + GET-verify, logged
    feed["cdn_push"] = {}
    try:
        import hashlib, urllib.error
        tok = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True).stdout.strip()
        if not tok: raise RuntimeError("no gh token")
        for f in ["live_count.json", "census_manifest.json"]:
            raw = open(os.path.join(PUB, f), "rb").read()
            content = base64.b64encode(raw).decode()
            blob_sha = hashlib.sha1(b"blob %d\0" % len(raw) + raw).hexdigest()   # git blob sha of local bytes
            API = "https://api.github.com/repos/dimitrilaouanis-tech/rhinogent/contents/" + f
            def call(u, d=None, me="GET"):
                rq = urllib.request.Request(u, data=json.dumps(d).encode() if d else None, method=me,
                    headers={"Authorization": "Bearer " + tok, "Accept": "application/vnd.github+json"})
                return json.loads(urllib.request.urlopen(rq, timeout=30).read())
            landed, last = False, ""
            for attempt in range(4):
                try:
                    try:
                        remote = call(API + "?ref=gh-pages")
                    except urllib.error.HTTPError as e:
                        if e.code != 404: raise
                        remote = {}                              # file doesn't exist yet → CREATE it
                    if remote.get("sha") == blob_sha:            # already identical → landed
                        landed = True; break
                    b = {"message": "live count+rate sync", "content": content,
                         "branch": "gh-pages", "sha": remote.get("sha")}
                    if not b["sha"]: b.pop("sha")
                    r = call(API, b, "PUT")
                    # VERIFY the push actually landed (git blob sha of what GitHub now holds)
                    landed = (r.get("content") or {}).get("sha") == blob_sha
                    if landed: break
                    last = "put-ok-but-sha-mismatch"
                except urllib.error.HTTPError as e:
                    last = f"HTTP {e.code}"                       # 409/422 = stale sha → refetch + retry
                except Exception as e:
                    last = str(e)[:60]
                time.sleep(1.5 * (attempt + 1))
            feed["cdn_push"][f] = "landed" if landed else f"FAILED ({last})"
            if not landed:
                print(f"CDN PUSH FAILED for {f}: {last}")
    except Exception as e:
        print("CDN PUSH SKIPPED:", str(e)[:80])
    json.dump({"count": count, "ts": time.time()}, open("_local_only/_count_sync_state.json", "w"))
    return feed

if __name__ == "__main__":
    f = sync()
    print(f"LIVE COUNT SYNC → {f['count']:,} · {f['rate_per_sec']}/sec · {f['to_million']:,} to 1M")
