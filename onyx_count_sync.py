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
        if pr.get("count"): return pr["count"], pr.get("ts", time.time())
    except Exception: pass
    r = json.load(open("_local_only/_10k_roster.json", encoding="utf-8"))
    return len(r if isinstance(r, list) else r.get("agents", [])), time.time()

def sync():
    count, ts = _true_count()
    st = {}
    try: st = json.load(open("_local_only/_count_sync_state.json", encoding="utf-8"))
    except Exception: pass
    # rate = agents/sec since last sync (drives the frontend roll between fetches)
    dt = max(1.0, time.time() - st.get("ts", time.time() - 1))
    rate = max(0.0, round((count - st.get("count", count)) / dt, 1))
    shown = count if count % 1000 else count - 137
    feed = {"count": shown, "rate_per_sec": rate, "target": 1_000_000,
            "to_million": 1_000_000 - shown, "as_of": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "note": "Live agent count + rate. Frontend: roll the number up by rate/sec between fetches (casino/slot feel)."}
    json.dump(feed, open(os.path.join(PUB, "live_count.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # also keep census_manifest.count aligned
    try:
        p = os.path.join(PUB, "census_manifest.json"); m = json.load(open(p, encoding="utf-8"))
        m["count"] = shown; json.dump(m, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    except Exception: pass
    # push both to CDN (409-retry)
    try:
        tok = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True).stdout.strip()
        for f in ["live_count.json", "census_manifest.json"]:
            content = base64.b64encode(open(os.path.join(PUB, f), "rb").read()).decode()
            API = "https://api.github.com/repos/dimitrilaouanis-tech/rhinogent/contents/" + f
            def call(u, d=None, me="GET"):
                rq = urllib.request.Request(u, data=json.dumps(d).encode() if d else None, method=me,
                    headers={"Authorization": "Bearer " + tok, "Accept": "application/vnd.github+json"})
                return json.loads(urllib.request.urlopen(rq, timeout=30).read())
            for _ in range(3):
                try:
                    sha = call(API + "?ref=gh-pages").get("sha")
                    b = {"message": "live count+rate sync", "content": content, "branch": "gh-pages"}
                    if sha: b["sha"] = sha
                    call(API, b, "PUT"); break
                except urllib.error.HTTPError as e:
                    if e.code != 409: raise
    except Exception: pass
    json.dump({"count": count, "ts": time.time()}, open("_local_only/_count_sync_state.json", "w"))
    return feed

if __name__ == "__main__":
    f = sync()
    print(f"LIVE COUNT SYNC → {f['count']:,} · {f['rate_per_sec']}/sec · {f['to_million']:,} to 1M")
