# 0n1x QUESTION BANK v2 — Metaculus/Kalshi/Polymarket-grade categorized question system.
# Core principle stolen from all four exemplars: a question is valid ONLY IF, at creation
# time, we can point a machine at the exact source+field and get a deterministic scalar NOW
# (the pre-flight dry-run). That one gate automates what Metaculus does with human review,
# Kalshi with filed Source Agencies, and Polymarket with pre-written UMA rules.
import json, time, random, hashlib, urllib.request

# ── D1/D2: fixed small CATEGORY enum (Metaculus pattern) + TYPE enum ──────────
CATEGORIES = ("CRYPTO_PRICE", "CRYPTO_MARKET", "DEFI", "MACRO_ECON",
              "WEATHER", "TECH_METRICS")   # allowlist: only free deterministic resolvers
TYPES = ("BINARY", "NUMERIC")

# ── D4: resolution-source adapters — each returns ONE scalar for a live target ──
def _get(url, timeout=20):
    return json.loads(urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": "0n1x/1.0"}), timeout=timeout).read())

def r_price(sym):        # Coinbase spot
    return float(_get(f"https://api.coinbase.com/v2/prices/{sym}-USD/spot")["data"]["amount"])
def r_defillama(slug):   # DefiLlama TVL (free, no key)
    return float(_get(f"https://api.llama.fi/tvl/{slug}"))
def r_weather(lat, lon): # Open-Meteo current temp °C (free, no key)
    return float(_get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m")["current"]["temperature_2m"])
def r_github(repo):      # GitHub stars (free)
    return float(_get(f"https://api.github.com/repos/{repo}")["stargazers_count"])
def r_gas():             # Base gas via public metric — mempool-style (uses blockchair eth)
    return float(_get("https://api.blockchair.com/ethereum/stats")["data"]["mempool_median_gas_price"]) / 1e9

# ── question templates per category: (label, resolver, targets, unit, band) ──
TEMPLATES = {
    "CRYPTO_PRICE": {"label": "Crypto Prices", "src": "PRICE_API", "fn": r_price,
                     "targets": ["BTC", "ETH", "SOL", "DOGE", "LTC", "XRP", "ADA", "AVAX"],
                     "unit": "USD", "band": 0.004, "q": lambda t, s: f"Will {t} trade above {_p(s)} at resolution?"},
    "DEFI":         {"label": "DeFi TVL", "src": "DEFILLAMA", "fn": r_defillama,
                     "targets": ["aave", "uniswap", "lido", "makerdao", "curve-dex"],
                     "unit": "USD", "band": 0.01, "q": lambda t, s: f"Will {t} TVL be above {_bn(s)} at resolution?"},
    "WEATHER":      {"label": "Weather", "src": "WEATHER_API", "fn": lambda t: r_weather(*WX[t]),
                     "targets": ["London", "New York", "Tokyo", "Dubai", "Sydney"],
                     "unit": "°C", "band": 0.06, "q": lambda t, s: f"Will {t}'s temperature be above {s:.1f}°C at resolution?"},
    "TECH_METRICS": {"label": "Tech / GitHub", "src": "GITHUB", "fn": r_github,
                     "targets": ["ethereum/go-ethereum", "bitcoin/bitcoin", "openai/whisper"],
                     "unit": "stars", "band": 0.002, "q": lambda t, s: f"Will {t} have more than {int(s):,} stars at resolution?"},
}
WX = {"London": (51.5, -0.12), "New York": (40.7, -74.0), "Tokyo": (35.7, 139.7),
      "Dubai": (25.2, 55.3), "Sydney": (-33.9, 151.2)}

def _p(v): return f"${v:,.4f}" if v < 10 else f"${v:,.0f}"
def _bn(v): return f"${v/1e9:.2f}B" if v >= 1e9 else f"${v/1e6:.0f}M"

BLOCKLIST = ("significant", "major", "crash", "soon", "enough", "considered", "widely", "moon")


# ── D5: THE QUALITY FILTER (auto-reject; the disqualifier list) ──────────────
def quality_check(q):
    req = ("id", "category", "type", "title", "target", "threshold", "operator",
           "unit", "resolution_source", "open_ts", "close_ts", "resolution_ts")
    for f in req:
        if q.get(f) in (None, ""):
            return False, f"missing:{f}"
    if q["category"] not in CATEGORIES: return False, "category not in allowlist"
    if q["type"] not in TYPES:          return False, "unknown type"
    if q["resolution_ts"] <= q["close_ts"]:  return False, "resolution_ts <= close_ts"
    if q["close_ts"] <= q["open_ts"]:        return False, "close_ts <= open_ts"
    if q["resolution_ts"] - q["open_ts"] < 600: return False, "horizon <10min"
    if q["operator"] not in (">", ">=", "<", "<="): return False, "bad operator"
    if q["threshold"] <= 0:             return False, "non-positive threshold"
    low = q["title"].lower()
    if any(w in low for w in BLOCKLIST):  return False, "subjective term in title"
    return True, "ok"


def generate(category=None, horizon_choices=(3600, 10800)):
    """Build ONE categorized question and PRE-FLIGHT its resolver. Ships only if it
    passes the filter AND the resolver returns a live deterministic scalar right now."""
    cat = category or random.choice(list(TEMPLATES.keys()))
    t = TEMPLATES[cat]
    target = random.choice(t["targets"])
    try:
        spot = t["fn"](target)                 # ← THE DRY-RUN: if this throws, no question ships
    except Exception as e:
        return None, f"preflight failed: {str(e)[:40]}"
    if not spot or spot != spot:               # nan/zero guard
        return None, "preflight non-scalar"
    band = t["band"]
    threshold = round(spot * (1 + random.uniform(-band, band)), 4 if spot < 10 else 2)
    now = time.time()
    horizon = random.choice(horizon_choices)
    q = {
        "id": hashlib.sha256(f"{cat}{target}{threshold}{now}".encode()).hexdigest()[:12],
        "category": cat, "type": "BINARY", "target": target,
        "tags": [cat.lower(), target.lower(), t["src"].lower()],
        "title": t["q"](target, threshold),
        "threshold": threshold, "operator": ">", "unit": t["unit"],
        "resolution_source": {"type": t["src"], "target": target},
        "timezone": "UTC",
        "open_ts": round(now, 1), "close_ts": round(now + horizon * 0.5, 1),
        "resolution_ts": round(now + horizon, 1),
        "open_price": spot,     # kept for the panel's baseline prior
        "fallback_rule": "RESOLVE_NA_0.5",
        "scoring": {"method": "BRIER", "cohort_relative": True},
    }
    ok, reason = quality_check(q)
    return (q if ok else None), reason


def resolve_value(q):
    """Fetch the current scalar for a question's target (used at resolution time)."""
    return TEMPLATES[q["category"]]["fn"](q["target"])


if __name__ == "__main__":
    ok_n = rej_n = 0
    by_cat = {}
    for _ in range(18):
        q, reason = generate()
        if q:
            ok_n += 1
            by_cat[q["category"]] = by_cat.get(q["category"], 0) + 1
            print(f"  ✓ [{q['category']:13}] {q['title'][:60]}")
        else:
            rej_n += 1
            print(f"  ✗ {reason}")
    print(f"\n{ok_n} shipped (pre-flight passed), {rej_n} rejected · categories hit: {by_cat}")
