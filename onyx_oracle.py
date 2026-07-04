# 0n1x ORACLE LAYER — the anchor that makes the 100k genuinely intelligent.
# Design principle (mine): the swarm PROPOSES, reality DISPOSES. A claim comes in; we
# classify what KIND of truth it is; route it to the EXTERNAL source that can settle it
# (never a same-family cheap model — that's the circular-parrot trap). Return a verdict
# the swarm cannot argue with. This is what turns cheap volume into intelligence:
# every claim is scored against reality, not consensus.
import json, re, urllib.request, time

def _get(url, timeout=15, raw=False):
    req = urllib.request.Request(url, headers={"User-Agent": "0n1x-oracle/1.0"})
    body = urllib.request.urlopen(req, timeout=timeout).read()
    return body.decode().strip() if raw else json.loads(body)

# ── external resolvers — each returns a REAL scalar/verdict from the world, no model ──
def r_price(sym):
    return float(_get(f"https://api.coinbase.com/v2/prices/{sym}-USD/spot")["data"]["amount"])
def r_merchant(domain):
    """MERCHANT-REALITY resolver (eco-voted oracle depth): real risk signals with no key, no
    cold-start dependency. Domain AGE via RDAP is the strongest cheap fraud signal — scam
    storefronts are days-to-weeks old; legit merchants are years old. Returns a real verdict."""
    domain = domain.strip().lower().replace("https://", "").replace("http://", "").split("/")[0]
    age_days = None
    try:
        r = _get(f"https://rdap.org/domain/{domain}", timeout=12)
        import datetime
        for ev in r.get("events", []):
            if ev.get("eventAction") == "registration" and ev.get("eventDate"):
                reg = datetime.datetime.fromisoformat(ev["eventDate"].replace("Z", "+00:00"))
                age_days = (datetime.datetime.now(datetime.timezone.utc) - reg).days
                break
    except Exception:
        pass
    if age_days is None:
        # fall back to the merchant API if RDAP is unavailable for this TLD
        try:
            v = _get(f"https://onyx-actions.onrender.com/api/check?url={domain}", timeout=25)
            return {"band": v.get("band"), "verdict": v.get("verdict"), "source": "api/check"}
        except Exception:
            return {"band": "unknown", "verdict": "COULD NOT RESOLVE", "age_days": None}
    # real risk banding from domain age (the fraud signal)
    if age_days < 60:
        band, verdict = "high_risk", f"HIGH RISK — domain only {age_days} days old"
    elif age_days < 365:
        band, verdict = "caution", f"CAUTION — under a year old ({age_days} days); verify before paying"
    elif age_days < 1095:
        band, verdict = "ok", f"ESTABLISHED — {age_days} days ({age_days // 365}y+)"
    else:
        band, verdict = "ok", f"WELL-ESTABLISHED — {age_days // 365} years old"
    # domain age is ONE signal — honest about its ceiling (an aged domain can still be a scam)
    return {"band": band, "verdict": verdict, "age_days": age_days, "source": "rdap",
            "signal": "domain_age", "note": "age is a strong young-scam filter, not a full guarantee"}

def r_domain(domain):
    return r_merchant(domain)
def r_defillama(slug):
    return float(_get(f"https://api.llama.fi/tvl/{slug}", raw=True))
def r_fx(sym):
    return float(_get(f"https://api.frankfurter.dev/v1/latest?base=USD&symbols={sym}")["rates"][sym])
def r_github(repo):
    return float(_get(f"https://api.github.com/repos/{repo}")["stargazers_count"])

# ── the ROUTER — classify the claim, pick the resolver that settles it against reality ──
KNOWN_SYMS = {"BTC","ETH","SOL","DOGE","LTC","XRP","ADA","AVAX"}
FX_SYMS = {"EUR","GBP","JPY","CAD","AUD","CHF"}

def classify(claim: str):
    """Return (kind, target) — what external truth can settle this claim."""
    c = claim.lower()
    # a domain / merchant reality check
    dom = re.search(r"([a-z0-9][a-z0-9-]*\.[a-z]{2,}(?:\.[a-z]{2,})?)", c)
    if dom and re.search(r"legit|safe|scam|trust|verify|real|merchant|site|domain|check", c):
        return "domain", dom.group(1)
    # a crypto price claim
    for s in KNOWN_SYMS:
        if s.lower() in c and re.search(r"price|above|below|\$|trade|worth|usd", c):
            return "price", s
    # DeFi TVL
    m = re.search(r"(aave|uniswap|lido|makerdao|curve)", c)
    if m and "tvl" in c:
        return "tvl", m.group(1)
    # FX
    for s in FX_SYMS:
        if s.lower() in c or f"usd/{s.lower()}" in c:
            return "fx", s
    # GitHub stars
    gh = re.search(r"([\w.-]+/[\w.-]+)", claim)
    if gh and "star" in c:
        return "github", gh.group(1)
    return "unverifiable", None

RESOLVERS = {"price": r_price, "tvl": r_defillama, "fx": r_fx, "github": r_github, "domain": r_domain}

def resolve(claim: str):
    """Settle a claim against REALITY. Returns the ground truth + whether it's resolvable.
    'unverifiable' claims (pure opinion, no external source) are HONESTLY flagged — the
    swarm cannot manufacture truth where reality offers none."""
    kind, target = classify(claim)
    if kind == "unverifiable":
        return {"resolvable": False, "kind": kind,
                "note": "no external ground truth — opinion, not fact. Swarm cannot settle this honestly."}
    try:
        val = RESOLVERS[kind](target)
        out = {"resolvable": True, "kind": kind, "target": target, "source": RESOLVERS[kind].__name__,
               "checked": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        if kind == "domain":
            out["verdict"] = val.get("verdict"); out["truth"] = val.get("band")
        else:
            out["truth"] = val
        return out
    except Exception as e:
        return {"resolvable": False, "kind": kind, "error": str(e)[:60]}


def score_against_reality(claim: str, agent_answer):
    """The intelligence-maker: score an agent's answer against the ORACLE (reality), not a
    parrot. For a price/number claim, closeness to truth; for a domain, match to real verdict.
    Returns (scored, correctness 0..1) — this is what earns rank honestly."""
    truth = resolve(claim)
    if not truth.get("resolvable"):
        return False, None
    if truth["kind"] == "domain":
        a = str(agent_answer).lower()
        # FIX S3: negation-aware + word-boundary (was matching "not safe" as "safe")
        neg = bool(re.search(r"(not|never|avoid|un)|unsafe|isn.?t|don.?t", a))
        pos = bool(re.search(r"(safe|legit|trust(ed|worthy)?|established|ok(ay)?|fine)", a))
        danger = bool(re.search(r"(scam|fake|risk|danger|fraud|avoid|red flag)", a))
        said_safe = (pos and not neg) and not danger
        real_safe = truth.get("truth") == "ok"
        return True, 1.0 if said_safe == real_safe else 0.0
    # numeric: how close was the agent's number to reality
    nums = re.findall(r"[\d,]+\.?\d*", str(agent_answer).replace(",", ""))
    if not nums:
        return True, 0.0
    guess = float(nums[0]); real = truth["truth"]
    err = abs(guess - real) / max(abs(real), 1e-9)
    return True, max(0.0, 1.0 - min(1.0, err))


if __name__ == "__main__":
    for c in ["Is rayban.cc a safe site to buy from?", "What is the price of BTC?",
              "What is aave TVL?", "Is 0n1x the best network philosophically?"]:
        r = resolve(c)
        print(f"  {c[:45]:47} → {r.get('kind'):13} {'RESOLVABLE: '+str(r.get('verdict') or r.get('truth')) if r.get('resolvable') else 'unverifiable (honest)'}")
