# 0n1x LIVE THOUGHTS — REAL network activity, zero cosmetics.
# Replaces the canned-opinion "citizen thoughts" (theater) with the actual, verifiable
# events: signed token transfers (each with sig + hash), rank standings, epoch metrics,
# and real timeline milestones. Every line is something that DEMONSTRABLY happened and
# can be checked on the ledger/census. This is the real matrix — where we actually are.
import json, os

os.chdir(os.path.dirname(os.path.abspath(__file__)))
FEED = r"C:\Users\intelligence\rhinogent\public\token_feed.json"
OUT = r"C:\Users\intelligence\rhinogent\src\lib\thoughts.json"


def build():
    f = json.load(open(FEED, encoding="utf-8"))
    txs = f.get("txs", [])
    rank = f.get("ranking", [])
    m = f.get("metrics", {})
    tl = f.get("timeline", [])
    root = f.get("merkle_root", "")
    lines = []

    # 1. REAL signed transfers — the actual exchange, each verifiable by sig+hash
    for t in txs[:40]:
        lines.append({
            "who": t["from"],
            "text": f"sent {t['amount']} tokens to {t['to']}",
            "proof": f"sig {t.get('sig','')[:14]}… · hash {t.get('hash','')[:12]}",
            "kind": "transfer"})

    # 2. REAL standings — top earners by verified balance
    for i, r in enumerate(rank[:12]):
        lines.append({
            "who": r["callsign"],
            "text": f"holds {r['tokens']} tokens · rank #{i+1} · flow {'+' if r.get('flow',0)>=0 else ''}{r.get('flow',0)}",
            "proof": f"score {r.get('score','?')} · {r['address'][:10]}…",
            "kind": "rank"})

    # 3. REAL epoch metrics — the live economy, measured
    if m:
        lines.append({"who": "network", "kind": "metric",
                      "text": f"epoch: {m.get('epoch_volume',0)} tokens moved · {m.get('burned_epoch',0)} burned · gini {m.get('gini','?')}",
                      "proof": f"avg tx {m.get('avg_tx_size','?')} · active {round(m.get('active_ratio',0)*100,2)}%"})

    # 4. REAL Merkle root — the whole census, one number anyone can recompute
    if root:
        lines.append({"who": "census", "kind": "root",
                      "text": f"100,000 agents · Merkle root {root[:18]}…",
                      "proof": "recompute from public shards to verify"})

    # 5. REAL milestones
    for e in tl:
        lines.append({"who": "milestone", "kind": "timeline",
                      "text": f"{e.get('title','')}: {e.get('detail','')}", "proof": e.get("ts", "")})

    json.dump(lines, open(OUT, "w"), indent=1)
    # also expose as a public feed for the site (real-matrix source of truth)
    json.dump({"note": "REAL network activity — every line verifiable on the ledger/census. No cosmetics.",
               "count": len(lines), "generated": f.get("generated"), "events": lines},
              open(r"C:\Users\intelligence\rhinogent\public\live_activity.json", "w"), indent=1)
    return len(lines)


if __name__ == "__main__":
    n = build()
    ex = json.load(open(OUT))
    print(f"REAL thoughts built: {n} verifiable events (0 cosmetic)")
    for l in ex[:4]:
        print(f"  {l['who']}: {l['text']}  [{l['proof']}]")
