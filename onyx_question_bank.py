# 0n1x QUESTION BANK — categorized, filtered question generation for the forecast market.
# Reverse-engineered from Metaculus/Polymarket/Kalshi: every question is a typed, categorized
# object with an explicit resolution source + a QUALITY FILTER that auto-rejects bad questions
# (ambiguous, un-resolvable, degenerate strikes). Only questions that PASS become live.
import json, time, random, urllib.request

# ── CATEGORY SCHEMA (crypto-price tier auto-resolvable via free public APIs) ──
# Each category: how to fetch spot, and the human label. Extend as new resolvers land.
CATEGORIES = {
    "crypto": {
        "label": "Crypto Prices",
        "symbols": ["BTC", "ETH", "SOL", "DOGE", "LTC", "XRP", "ADA", "AVAX"],
        "resolver": "coinbase_spot",
    },
    # scaffolded for when the researcher's resolvers land:
    # "onchain": {"label": "On-chain", "resolver": "base_rpc"},
    # "sports":  {"label": "Sports",   "resolver": "espn_scores"},
}

QUESTION_TYPES = ("binary_above",)   # v1 type; researcher will add numeric/date/multi

def coinbase_spot(sym):
    r = json.loads(urllib.request.urlopen(
        f"https://api.coinbase.com/v2/prices/{sym}-USD/spot", timeout=20).read())
    return float(r["data"]["amount"])

RESOLVERS = {"coinbase_spot": coinbase_spot}


def _fmt_price(p):
    return f"${p:,.4f}" if p < 10 else f"${p:,.0f}"


# ── THE QUALITY FILTER (Metaculus's "well-formed question" checklist) ─────────
def quality_check(q):
    """Return (ok, reason). Auto-rejects any question that isn't cleanly resolvable."""
    # 1) must have every required field
    required = ("id", "category", "type", "text", "symbol", "strike",
                "open_price", "opened_at", "resolves_at", "resolution_source")
    for f in required:
        if q.get(f) in (None, ""):
            return False, f"missing field: {f}"
    # 2) time-bounded and in the future (Good Judgment: unambiguous horizon)
    if q["resolves_at"] <= q["opened_at"]:
        return False, "resolves_at not after opened_at"
    if q["resolves_at"] - q["opened_at"] < 600:
        return False, "horizon too short (<10min) — unresolvable/noisy"
    # 3) NON-DEGENERATE strike — reject near-certain outcomes (Metaculus bans ~coin-flip-less)
    #    strike must be within a sane band of open price so the question is genuinely uncertain
    dist = abs(q["strike"] - q["open_price"]) / max(1e-9, q["open_price"])
    if dist > 0.05:
        return False, f"strike too far from spot ({dist:.1%}) — near-certain, no signal"
    if q["strike"] <= 0:
        return False, "non-positive strike"
    # 4) category/type/resolver must be known
    if q["category"] not in CATEGORIES:
        return False, f"unknown category: {q['category']}"
    if q["type"] not in QUESTION_TYPES:
        return False, f"unknown type: {q['type']}"
    if CATEGORIES[q["category"]]["resolver"] not in RESOLVERS:
        return False, "no resolver for category"
    return True, "ok"


def generate(category="crypto", horizon_choices=(3600, 10800)):
    """Build ONE candidate question; returns it only if it passes the quality filter."""
    cat = CATEGORIES[category]
    sym = random.choice(cat["symbols"])
    px = RESOLVERS[cat["resolver"]](sym)
    now = time.time()
    # strike within a genuinely-uncertain band (±0.4%) — the sweet spot the filter allows
    strike = round(px * (1 + random.uniform(-0.004, 0.004)), 4 if px < 10 else 2)
    q = {
        "id": __import__("hashlib").sha256(f"{sym}{strike}{now}".encode()).hexdigest()[:12],
        "category": category,
        "type": "binary_above",
        "symbol": sym,
        "strike": strike,
        "open_price": px,
        "opened_at": round(now, 1),
        "resolves_at": round(now + random.choice(horizon_choices), 1),
        "resolution_source": f"{cat['resolver']} ({sym}-USD)",
        "text": f"Will {sym} trade above {_fmt_price(strike)} at resolution?",
    }
    ok, reason = quality_check(q)
    return (q if ok else None), reason


if __name__ == "__main__":
    ok_n = rej_n = 0
    for _ in range(12):
        q, reason = generate()
        if q:
            ok_n += 1
            print(f"  ✓ [{q['category']}] {q['text']}  ({(q['resolves_at']-q['opened_at'])/3600:.0f}h)")
        else:
            rej_n += 1
            print(f"  ✗ rejected: {reason}")
    print(f"\nfilter working: {ok_n} passed, {rej_n} auto-rejected")
    print(f"categories: {list(CATEGORIES)} · types: {QUESTION_TYPES}")
