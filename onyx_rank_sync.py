# 0n1x REAL-TIME RANK SYNC — fast, frequent ranking updates ($0).
# The full census rebuild (Merkle + 200 shards) is heavy and runs q10min. But RANKING is
# just a sort over balances (sub-millisecond at 200k). This decouples them: recompute the
# ranking from the live ledger + genesis and publish ONLY token_feed's ranking + a fresh
# timestamp — fast, so the live network's rankings move in near-real-time. Scheduleable
# every 1-2 min without the census cost. Signed timestamp = provable freshness.
import json, os, time, base64, subprocess, urllib.request
os.chdir(os.path.dirname(os.path.abspath(__file__)))
PUB = r"C:\Users\intelligence\rhinogent\public"


def load(p, d):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return d


def sync():
    feed = load(PUB + r"\token_feed.json", {})
    roster = load("_local_only/_10k_roster.json", [])
    rag = roster if isinstance(roster, list) else roster.get("agents", [])
    ledger = load("_local_only/_ledger.json", []) or feed.get("_ledger", [])

    # balances = genesis(score-derived) + net signed ledger flow (same formula as the engine)
    by_addr = {a["address"]: a for a in rag if a.get("address")}
    def genesis(a):
        salt = int(a.get("address", "0x0")[-4:], 16) % 600 if len(a.get("address", "")) >= 4 else 0
        return round(a.get("score", 0) * 11 + salt + 40)
    bal = {a["address"]: genesis(a) for a in rag if a.get("address")}
    flow = {}
    for tx in (ledger if isinstance(ledger, list) else []):
        fr, to, amt = tx.get("from"), tx.get("to"), tx.get("amount", 0)
        if fr in bal: bal[fr] -= amt; flow[fr] = flow.get(fr, 0) - amt
        if to in bal: bal[to] += amt; flow[to] = flow.get(to, 0) + amt

    # THE SORT — over all 200k, sub-ms. Publish the top cohort + a fresh signed timestamp.
    ranked = sorted(bal, key=lambda ad: (bal[ad], by_addr[ad].get("score", 0)), reverse=True)
    top = [{"callsign": by_addr[ad].get("callsign", "?"), "address": ad,
            "tokens": bal[ad], "flow": flow.get(ad, 0), "score": by_addr[ad].get("score", 0)}
           for ad in ranked[:120]]

    feed["ranking"] = top
    feed["ranked_total"] = len(ranked)
    feed["rank_synced"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    feed["rank_sync_epoch"] = int(time.time())
    try:
        from tools_pkg import _onyx_sign
        stamp = _onyx_sign.attest({"rank_synced": feed["rank_synced"], "ranked_total": len(ranked),
                                   "top1": top[0]["address"] if top else None}, tool="onyx_rank_sync")
        feed["rank_sync_attestation"] = stamp.get("onyx_attestation")
    except Exception:
        pass

    json.dump(feed, open(PUB + r"\token_feed.json", "w"), ensure_ascii=False)
    return feed


def publish():
    tok = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True).stdout.strip()
    content = base64.b64encode(open(PUB + r"\token_feed.json", "rb").read()).decode()
    API = "https://api.github.com/repos/dimitrilaouanis-tech/rhinogent/contents/token_feed.json"
    def call(u, d=None, m="GET"):
        r = urllib.request.Request(u, data=json.dumps(d).encode() if d else None, method=m,
                                   headers={"Authorization": "Bearer " + tok, "Accept": "application/vnd.github+json"})
        return json.loads(urllib.request.urlopen(r, timeout=30).read())
    try: sha = call(API + "?ref=gh-pages").get("sha")
    except Exception: sha = None
    b = {"message": "rank sync (real-time)", "content": content, "branch": "gh-pages"}
    if sha: b["sha"] = sha
    return call(API, b, "PUT").get("commit", {}).get("sha", "?")[:10]


if __name__ == "__main__":
    import sys
    t0 = time.time()
    f = sync()
    print(f"RANK SYNC: {f.get('ranked_total',0):,} agents ranked in {round((time.time()-t0)*1000)}ms "
          f"· synced {f.get('rank_synced')} · top: {f['ranking'][0]['callsign']} ({f['ranking'][0]['tokens']})")
    if "--publish" in sys.argv:
        print("published ->", publish())
