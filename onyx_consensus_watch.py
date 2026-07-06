# 0n1x CONSENSUS WATCH — continuous intel accumulation ($0). The uncopyable moat: every run,
# the fleet re-attests a growing watchlist and APPENDS to a signed corpus. A competitor can copy
# the code, but not the accumulated, timestamped, signed attestation HISTORY — that only grows
# with real running time. Momentum IS the moat. Also gives TEMPORAL change-detection for free.
import json, os, time, hashlib
os.chdir(os.path.dirname(os.path.abspath(__file__)))
PUB = r"C:\Users\intelligence\rhinogent\public"
CORPUS = "_local_only/_consensus_corpus.jsonl"

WATCHLIST = [
    "shopify.com", "stripe.com", "amazon.com", "rayban.cc", "rayban.com", "gucci.com",
    "temu.com", "shein.com", "aliexpress.com", "nike.com", "coinbase.com", "binance.com",
    "uniswap.org", "opensea.io", "metamask.io", "ledger.com",
]

def run():
    import onyx_consensus as C
    prev = {}
    if os.path.exists(CORPUS):                       # last verdict per target → temporal change-detection
        for line in open(CORPUS, encoding="utf-8"):
            try:
                r = json.loads(line); prev[r["target"]] = r.get("score")
            except Exception: pass
    epoch = int(time.time())
    results, changes = [], []
    for tgt in WATCHLIST:
        p = C.consensus_check(tgt, n=100)
        rec = {"target": tgt, "score": p.get("score"), "verdict": p.get("verdict"),
               "agent_count": p.get("agent_count"), "consensus_proof": p.get("consensus_proof"),
               "epoch": epoch}
        # TEMPORAL: did it change since last run? (the signal no static LLM has)
        if tgt in prev and prev[tgt] is not None and p.get("score") != prev[tgt]:
            rec["changed_from"] = prev[tgt]
            changes.append({"target": tgt, "from": prev[tgt], "to": p.get("score")})
        results.append(rec)
        open(CORPUS, "a", encoding="utf-8").write(json.dumps(rec) + "\n")

    # publish the live snapshot + the growing corpus size (the momentum number)
    corpus_size = sum(1 for _ in open(CORPUS, encoding="utf-8")) if os.path.exists(CORPUS) else 0
    snap = {"as_of": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "watchlist": len(WATCHLIST), "latest": results, "changes_this_run": changes,
            "corpus_attestations_total": corpus_size,
            "note": "A growing, signed, timestamped corpus of fleet attestations. The moat is the "
                    "HISTORY — copyable code, uncopyable accumulated proof. Change-detection built in."}
    json.dump(snap, open(PUB + r"\consensus_watch.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return snap

if __name__ == "__main__":
    s = run()
    print(f"CONSENSUS WATCH: {s['watchlist']} targets re-attested · corpus now {s['corpus_attestations_total']:,} signed attestations")
    if s["changes_this_run"]:
        print("  ⚡ CHANGES:", s["changes_this_run"])
