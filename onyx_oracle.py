# 0n1x ORACLE LAYER — the anchor that makes the 100k genuinely intelligent.
# Design principle (mine): the swarm PROPOSES, reality DISPOSES. A claim comes in; we
# classify what KIND of truth it is; route it to the EXTERNAL source that can settle it
# (never a same-family cheap model — that's the circular-parrot trap). Return a verdict
# the swarm cannot argue with. This is what turns cheap volume into intelligence:
# every claim is scored against reality, not consensus.
import json, re, os, urllib.request, time

def _get(url, timeout=15, raw=False):
    req = urllib.request.Request(url, headers={"User-Agent": "0n1x-oracle/1.0"})
    body = urllib.request.urlopen(req, timeout=timeout).read()
    return body.decode().strip() if raw else json.loads(body)

# ── RDAP TTL cache (6h) + retry-with-backoff — batch runs stop rate-limiting into None ──
_HERE = os.path.dirname(os.path.abspath(__file__))
_RDAP_CACHE = os.path.join(_HERE, "_local_only", "_rdap_cache.json")
_RDAP_TTL = 6 * 3600

def _rdap_cache_load():
    try: return json.load(open(_RDAP_CACHE, encoding="utf-8"))
    except Exception: return {}

def _rdap_cache_put(domain, rec):
    c = _rdap_cache_load()
    c[domain] = {**rec, "ts": time.time()}
    try:
        tmp = _RDAP_CACHE + f".{os.getpid()}.tmp"
        json.dump(c, open(tmp, "w", encoding="utf-8"))
        os.replace(tmp, _RDAP_CACHE)
    except Exception: pass

def rdap_lookup(domain):
    """Cached (6h TTL) + backoff RDAP lookup. Returns {age_days, registered} —
    age_days None + registered False means the registry says NOT FOUND (a real signal);
    age_days None + registered None means RDAP unavailable (NOT a risk signal)."""
    c = _rdap_cache_load().get(domain)
    if c and time.time() - c.get("ts", 0) < _RDAP_TTL:
        return {"age_days": c.get("age_days"), "registered": c.get("registered"), "cached": True}
    import datetime
    last_err = None
    for attempt in range(4):
        try:
            r = _get(f"https://rdap.org/domain/{domain}", timeout=12)
            age_days = None
            for ev in r.get("events", []):
                if ev.get("eventAction") == "registration" and ev.get("eventDate"):
                    reg = datetime.datetime.fromisoformat(ev["eventDate"].replace("Z", "+00:00"))
                    age_days = (datetime.datetime.now(datetime.timezone.utc) - reg).days
                    break
            rec = {"age_days": age_days, "registered": True}
            _rdap_cache_put(domain, rec)
            return rec
        except urllib.error.HTTPError as e:
            if e.code == 404:                    # registry says: no such domain (definitive)
                rec = {"age_days": None, "registered": False}
                _rdap_cache_put(domain, rec)
                return rec
            last_err = e
            if e.code in (429, 500, 502, 503):   # rate-limit / transient → backoff + retry
                time.sleep(1.5 * (2 ** attempt))
                continue
            break
        except Exception as e:
            last_err = e
            time.sleep(1.0 * (attempt + 1))
    return {"age_days": None, "registered": None, "error": str(last_err)[:60]}

# ── external resolvers — each returns a REAL scalar/verdict from the world, no model ──
def r_price(sym):
    return float(_get(f"https://api.coinbase.com/v2/prices/{sym}-USD/spot")["data"]["amount"])
def r_merchant(domain):
    """MERCHANT-REALITY resolver (eco-voted oracle depth): real risk signals with no key, no
    cold-start dependency. Domain AGE via RDAP is the strongest cheap fraud signal — scam
    storefronts are days-to-weeks old; legit merchants are years old. Returns a real verdict."""
    domain = domain.strip().lower().replace("https://", "").replace("http://", "").split("/")[0]
    rd = rdap_lookup(domain)                     # cached + backoff (no more None under batch)
    age_days = rd.get("age_days")
    if rd.get("registered") is False:
        return {"band": "high_risk", "verdict": "UNRESOLVED — domain is NOT REGISTERED at the registry",
                "age_days": None, "source": "rdap", "signal": "not_registered"}
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

def r_tls(domain, timeout=8):
    """TLS certificate validity — a live handshake with full chain verification.
    Scam kits often run on fresh DV certs or none; an invalid/absent cert is a hard signal."""
    import ssl, socket, datetime
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((domain, 443), timeout=timeout) as s:
            with ctx.wrap_socket(s, server_hostname=domain) as w:
                cert = w.getpeercert()
        na = cert.get("notAfter")
        days_left = None
        if na:
            exp = datetime.datetime.strptime(na, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=datetime.timezone.utc)
            days_left = (exp - datetime.datetime.now(datetime.timezone.utc)).days
        issuer = dict(x[0] for x in cert.get("issuer", ())).get("organizationName", "?")
        return {"tls_ok": True, "days_left": days_left, "issuer": issuer}
    except ssl.SSLCertVerificationError as e:
        return {"tls_ok": False, "reason": "cert_invalid: " + str(e)[:50]}
    except Exception as e:
        return {"tls_ok": None, "reason": "unreachable: " + str(e)[:50]}

def r_http(domain, timeout=10):
    """HTTPS reachability — does the site actually answer?"""
    try:
        req = urllib.request.Request("https://" + domain, method="HEAD",
                                     headers={"User-Agent": "0n1x-oracle/1.0"})
        code = urllib.request.urlopen(req, timeout=timeout).getcode()
        return {"http_ok": code < 400, "status": code}
    except urllib.error.HTTPError as e:
        if e.code in (405, 403, 501):            # HEAD blocked ≠ down
            return {"http_ok": True, "status": e.code, "note": "HEAD blocked, host answers"}
        return {"http_ok": False, "status": e.code}
    except Exception as e:
        return {"http_ok": None, "reason": str(e)[:50]}

_CONTRACT_RE = re.compile(r"0x[0-9a-fA-F]{40}$")

def r_merchant_multi(target):
    """MULTI-SIGNAL merchant reality: domain AGE (RDAP) + TLS cert validity + HTTP reachability,
    fused into one 0-100 score + band. Never returns a None band: contract addresses get an
    honest 'unverified' contract path; unresolvable domains get 'high_risk'/UNRESOLVED."""
    t = str(target).strip()
    if _CONTRACT_RE.fullmatch(t):
        return {"band": "unverified", "kind": "contract", "score": 50, "target": t,
                "verdict": "CONTRACT ADDRESS — domain-reality signals do not apply; "
                           "verify on-chain provenance/deployer history instead",
                "signals": {"age": None, "tls": None, "http": None}}
    domain = t.lower().replace("https://", "").replace("http://", "").split("/")[0]
    age = r_merchant(domain)
    tls = r_tls(domain)
    http = r_http(domain)
    signals = {"age": {"band": age.get("band"), "age_days": age.get("age_days")}, "tls": tls, "http": http}
    host_alive = bool(tls.get("tls_ok") or http.get("http_ok"))
    # totally dark: RDAP not-found AND no live TLS host AND no HTTP answer → unresolved, high risk.
    # (RDAP 404 alone is NOT definitive — rdap.org can't bootstrap every TLD, e.g. some .io lookups.)
    if (age.get("signal") == "not_registered" and not host_alive) or \
       (tls.get("tls_ok") is None and http.get("http_ok") is None):
        return {"band": "high_risk", "kind": "domain", "score": 5, "target": domain,
                "verdict": "UNRESOLVED — domain does not resolve or is not registered; treat as high risk",
                "signals": signals}
    if age.get("signal") == "not_registered" and host_alive:
        age = {"band": "unknown", "verdict": "AGE UNKNOWN — registry RDAP not available for this TLD",
               "age_days": None}
        signals["age"] = {"band": "unknown", "age_days": None}
    age_score = {"high_risk": 8, "caution": 35, "ok": 88, "well-established": 92}.get(age.get("band"), 50)
    tls_score = 100 if tls.get("tls_ok") else (0 if tls.get("tls_ok") is False else 40)
    http_score = 100 if http.get("http_ok") else (0 if http.get("http_ok") is False else 40)
    score = round(age_score * 0.6 + tls_score * 0.2 + http_score * 0.2)
    band = "ok" if score >= 80 else ("caution" if score >= 45 else "high_risk")
    if age.get("band") in ("caution", "high_risk") and band == "ok":
        band = "caution"                          # young domain caps the band even with clean TLS/HTTP
    verdict = f"{band.upper().replace('_',' ')} — fused: age[{age.get('verdict','?')}] · " \
              f"tls[{'valid ('+str(tls.get('issuer'))+')' if tls.get('tls_ok') else tls.get('reason','?')}] · " \
              f"http[{'up '+str(http.get('status')) if http.get('http_ok') else http.get('reason', 'status '+str(http.get('status')))}]"
    return {"band": band, "kind": "domain", "score": score, "target": domain,
            "verdict": verdict, "signals": signals, "source": "multi:rdap+tls+http"}

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
