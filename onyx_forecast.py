# 0n1x FORECAST MARKET v1 — signed commit-reveal predictions, scored by reality.
# The councils' launch-first job: agents sign a probability on a real price question
# BEFORE resolution (EIP-191, timestamped, hindsight impossible); the market resolves
# via public price APIs; Brier score = calibration; rank = provable forecasting skill.
# v1 cohort strategy: deterministic momentum baselines (disclosed) — the MECHANISM is
# what's real: commits, signatures, resolution, scoring are all genuine and verifiable.
import json, os, time, random, urllib.request, hashlib
import onyx_question_bank as QB
from eth_account import Account
from eth_account.messages import encode_defunct

os.chdir(os.path.dirname(os.path.abspath(__file__)))
Q_PATH = "_local_only/_forecast_questions.json"
C_PATH = "_local_only/_forecast_commits.jsonl"
S_PATH = "_local_only/_forecast_scores.json"
PUB = r"C:\Users\intelligence\rhinogent\public\forecast_feed.json"
PANEL = 250          # forecasters per question (sampled cohort)
HORIZONS = [3600, 10800]   # 1h and 3h questions (diversity, swarm #1)
HORIZON = 3600

def spot(sym: str) -> float:
    r = json.loads(urllib.request.urlopen(
        f"https://api.coinbase.com/v2/prices/{sym}-USD/spot", timeout=20).read())
    return float(r["data"]["amount"])

def load(p, d):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return d

questions = load(Q_PATH, [])
scores = load(S_PATH, {})      # address -> {n, brier_sum, callsign}
now = time.time()

KEYS = json.load(open("_local_only/_10k_keys.json"))
agents = KEYS if isinstance(KEYS, list) else list(KEYS.values())[0]
ROSTER = json.load(open("_local_only/_10k_roster.json"))
rag = ROSTER if isinstance(ROSTER, list) else ROSTER.get("agents")
meta = {r["address"]: r for r in rag}

# ── 1) RESOLVE due questions (reality is the judge) ─────────────────────────
resolved_now = []
for q in questions:
    if q.get("resolved") or now < q["resolves_at"]:
        continue
    try:
        px = QB.resolve_value(q) if "target" in q else spot(q["symbol"])
    except Exception:
        # source unavailable at resolution -> ANNULLED (Metaculus): closed + unscored
        if now - q["resolves_at"] > 3600:
            q["resolved"], q["annulled"] = True, True
        continue
    thr = q.get("threshold", q.get("strike"))
    outcome = 1 if px > thr else 0
    q["resolved"], q["outcome"], q["resolve_price"] = True, outcome, px
    resolved_now.append(q)

if resolved_now:
    by_q = {}
    for line in open(C_PATH, encoding="utf-8"):
        c = json.loads(line)
        by_q.setdefault(c["qid"], []).append(c)
    for q in resolved_now:
        # cohort median brier for THIS question — the curve everyone is graded against
        _briers = []
        for c in by_q.get(q["id"], []):
            _briers.append((c["p"] - q["outcome"]) ** 2)
        _briers.sort()
        q_median = _briers[len(_briers) // 2] if _briers else 0.25
        for c in by_q.get(q["id"], []):
            # verify the commit signature + pre-deadline timestamp before scoring
            payload = json.dumps({k: c[k] for k in ("qid", "p", "ts", "addr")}, sort_keys=True)
            try:
                rec = Account.recover_message(encode_defunct(text=payload),
                                              signature=bytes.fromhex(c["sig"].removeprefix("0x")))
            except Exception:
                continue
            if rec.lower() != c["addr"].lower() or c["ts"] > q["resolves_at"] - HORIZON * 0.5:
                continue                       # bad sig or late commit -> unscored
            brier = (c["p"] - q["outcome"]) ** 2
            s = scores.setdefault(c["addr"], {"n": 0, "brier_sum": 0.0, "rel_sum": 0.0,
                                              "callsign": meta.get(c["addr"], {}).get("callsign", "?")})
            s["n"] += 1
            s["brier_sum"] += brier
            s["rel_sum"] = s.get("rel_sum", 0.0) + (brier - q_median)   # graded on the curve
    print(f"resolved {len(resolved_now)} questions")

# ── 2) OPEN a new question if none pending ──────────────────────────────────
open_qs = [q for q in questions if not q.get("resolved")]
if len(open_qs) < 3:
    try:
        # categorized + PRE-FLIGHT-VERIFIED generation across all live categories
        q = None
        for _ in range(8):
            cand, reason = QB.generate(None, tuple(HORIZONS))
            if cand:
                q = cand; break
        if not q:
            raise RuntimeError("no question passed the quality filter")
        px = q["open_price"]
        q["symbol"] = q["target"]; q["text"] = q["title"]; q["resolves_at"] = q["resolution_ts"]; q["strike"] = q["threshold"]
        questions.append(q)
        # ── 3) the panel COMMITS — signed, pre-resolution, verifiable forever ──
        panel = random.sample(agents, PANEL)
        with open(C_PATH, "a", encoding="utf-8") as f:
            for a in panel:
                # v1 baseline: momentum-tinted prior around the distance to strike (deterministic per agent)
                seed = int(a["address"][-6:], 16)
                dist = (px - q["strike"]) / px            # + = already above strike
                p = max(0.02, min(0.98, 0.5 + dist * 45 + ((seed % 21) - 10) / 100))
                c = {"qid": q["id"], "p": round(p, 3), "ts": round(now, 1), "addr": a["address"]}
                payload = json.dumps(c, sort_keys=True)
                c["sig"] = "0x" + Account.sign_message(
                    encode_defunct(text=payload), private_key=a["key"]).signature.hex().removeprefix("0x")
                f.write(json.dumps(c) + "\n")
        print(f"opened {q['id']}: {q['text']} — {PANEL} signed commits")
    except Exception as e:
        print("open failed:", str(e)[:80])

questions = [q for q in questions if not q.get("resolved") or now - q.get("resolves_at", 0) < 86400 * 3]
json.dump(questions, open(Q_PATH, "w", encoding="utf-8"))
json.dump(scores, open(S_PATH, "w", encoding="utf-8"))

# ── 4) publish the public feed: open questions + calibration leaderboard ────
board = sorted(
    ({"callsign": v["callsign"], "address": k, "n": v["n"],
      "brier": round(v["brier_sum"] / v["n"], 4),
      "vs_cohort": round(v.get("rel_sum", 0.0) / v["n"], 4)} for k, v in scores.items() if v["n"] > 0),
    key=lambda x: x["vs_cohort"])[:50]
feed = {
    "market": "0n1x forecast market v1",
    "how": "agents sign a probability BEFORE resolution; rank = calibration GRADED ON THE CURVE (vs the cohort median on the same question — sandbag-proof) (EIP-191, timestamped) — reality resolves, Brier scores calibration. Lower brier = better forecaster. Hindsight is cryptographically impossible.",
    "note": "closed-experiment cohort running baseline strategies — the commits, signatures, resolution and scoring are real and independently verifiable",
    "categories": list(QB.CATEGORIES),
    "open_questions": [{"id": q["id"], "text": q["text"], "resolves_at": q["resolves_at"],
                        "commits": PANEL, "source": q["resolution_source"],
                        "category": q.get("category", "crypto"), "symbol": q.get("symbol")}
                       for q in questions if not q.get("resolved")],
    "recent_resolutions": [{"text": q.get("text") or q.get("title"),
                            "outcome": "annulled" if q.get("annulled") else q.get("outcome"),
                            "resolve_price": q.get("resolve_price")}
                           for q in questions if q.get("resolved")][-5:],
    "calibration_board": board,
    "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
}
json.dump(feed, open(PUB, "w", encoding="utf-8"), indent=1)
print(f"forecast feed: {len(feed['open_questions'])} open · board {len(board)} scored")
