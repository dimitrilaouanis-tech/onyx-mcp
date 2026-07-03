# 0n1x QUESTION BANK v2 — Metaculus/Kalshi/Polymarket-grade categorized question system.
# Core principle stolen from all four exemplars: a question is valid ONLY IF, at creation
# time, we can point a machine at the exact source+field and get a deterministic scalar NOW
# (the pre-flight dry-run). That one gate automates what Metaculus does with human review,
# Kalshi with filed Source Agencies, and Polymarket with pre-written UMA rules.
import json, time, random, hashlib, urllib.request

# ── D1/D2: fixed small CATEGORY enum (Metaculus pattern) + TYPE enum ──────────
CATEGORIES = ("CRYPTO_PRICE", "DEFI", "WEATHER", "TECH_METRICS",
              "MACRO_FX", "SCIENCE_QUAKE", "TECH_NPM", "SPACE_LAUNCH",
              "CRYPTO_DIFF", "MACRO_DEBT")   # allowlist: only live-verified free resolvers
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
def _raw(url, timeout=20):   # plain-text body resolvers
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "0n1x/1.0"}), timeout=timeout).read().decode().strip()

# ── resolvers researched + LIVE-VERIFIED by the recruited Fable citizens ──
def r_fx(sym):           # Frankfurter ECB FX (no key) — Bold-Herald-49D4
    return float(_get(f"https://api.frankfurter.dev/v1/latest?base=USD&symbols={sym}")["rates"][sym])
def r_quakes(_):         # USGS M5+ quakes, last 7 days (no key) — Bold-Herald-49D4
    import datetime, calendar
    start = "2026-06-26"
    return float(_get(f"https://earthquake.usgs.gov/fdsnws/event/1/count?format=geojson&starttime={start}&minmagnitude=5")["count"])
def r_npm(pkg):          # npm weekly downloads (no key) — Bold-Herald-49D4
    return float(_get(f"https://api.npmjs.org/downloads/point/last-week/{pkg}")["downloads"])
def r_debt(_):           # US national debt (Treasury, no key) — Bold-Herald-49D4
    return float(_get("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/debt_to_penny?sort=-record_date&page%5Bsize%5D=1")["data"][0]["tot_pub_debt_out_amt"])
def r_launches(_):       # upcoming rocket launches count (no key) — Bold-Herald-49D4
    return float(_get("https://ll.thespacedevs.com/2.2.0/launch/upcoming/?limit=1")["count"])
def r_btc_difficulty(_): # BTC difficulty, consensus-deterministic (no key) — Bold-Herald-49D4
    return float(_raw("https://blockchain.info/q/getdifficulty"))

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
    # categories the recruited Fable citizens researched + verified live:
    "MACRO_FX":      {"label": "FX Rates", "src": "FRANKFURTER", "fn": r_fx,
                      "targets": ["EUR", "GBP", "JPY", "CAD", "AUD", "CHF"],
                      "unit": "per USD", "band": 0.008, "q": lambda t, s: f"Will USD/{t} be above {s:.4f} at resolution?"},
    "SCIENCE_QUAKE": {"label": "Earthquakes", "src": "USGS", "fn": r_quakes,
                      "targets": ["global"], "unit": "M5+ quakes/wk", "band": 0.15,
                      "q": lambda t, s: f"Will there be more than {int(s)} M5+ earthquakes worldwide this week?"},
    "TECH_NPM":      {"label": "npm Downloads", "src": "NPM", "fn": r_npm,
                      "targets": ["react", "express", "vue", "axios", "typescript"],
                      "unit": "dl/wk", "band": 0.03, "q": lambda t, s: f"Will {t} exceed {int(s):,} weekly npm downloads at resolution?"},
    "SPACE_LAUNCH":  {"label": "Rocket Launches", "src": "SPACEDEVS", "fn": r_launches,
                      "targets": ["upcoming"], "unit": "launches", "band": 0.2,
                      "q": lambda t, s: f"Will more than {int(s)} rocket launches be scheduled at resolution?"},
    "CRYPTO_DIFF":   {"label": "BTC Difficulty", "src": "BLOCKCHAIN", "fn": r_btc_difficulty,
                      "targets": ["bitcoin"], "unit": "difficulty", "band": 0.01,
                      "q": lambda t, s: f"Will BTC mining difficulty be above {s:.3e} at resolution?"},
    "MACRO_DEBT":    {"label": "US National Debt", "src": "TREASURY", "fn": r_debt,
                      "targets": ["usa"], "unit": "USD", "band": 0.002,
                      "q": lambda t, s: f"Will the US national debt exceed {_bn(s)} at resolution?"},
}
WX = {"London": (51.5, -0.12), "New York": (40.7, -74.0), "Tokyo": (35.7, 139.7),
      "Dubai": (25.2, 55.3), "Sydney": (-33.9, 151.2)}

def _p(v): return f"${v:,.4f}" if v < 10 else f"${v:,.0f}"
def _bn(v):
    if v >= 1e12: return f"${v/1e12:.2f}T"
    if v >= 1e9: return f"${v/1e9:.2f}B"
    return f"${v/1e6:.0f}M"

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
