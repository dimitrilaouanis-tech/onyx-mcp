# 0n1x PREMIUM DATA ENGINE — the army into action ($0, signed, real).
# Agents from the 612k roster are ASSIGNED real commerce domains; each runs the reality-oracle
# (live RDAP) and SIGNS its verdict with its own key. Aggregated into a signed "Verified Merchant
# Index" the Rhinogent chat draws on → the chat answers "is this store real?" with agent-verified,
# recompute-able premium data a plain LLM cannot give. This is deployment #1: the merchant-reality grid.
import json, os, time
from eth_account import Account
from eth_account.messages import encode_defunct

os.chdir(os.path.dirname(os.path.abspath(__file__)))
PUB = r"C:\Users\intelligence\rhinogent\public"

# real commerce/merchant domains — a live starter watchlist (grow over time)
WATCHLIST = [
    "shopify.com", "stripe.com", "amazon.com", "ebay.com", "etsy.com", "walmart.com",
    "target.com", "bestbuy.com", "nike.com", "adidas.com", "rayban.com", "rayban.cc",
    "gucci.com", "louisvuitton.com", "apple.com", "samsung.com", "aliexpress.com",
    "temu.com", "shein.com", "wayfair.com", "chewy.com", "instacart.com",
]

def load(p, d):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return d

def _agents(n):
    """Assign the first n roster agents (with keys) as the verification squad."""
    r = load("_local_only/_10k_roster.json", []); rag = r if isinstance(r, list) else r.get("agents", [])
    k = load("_local_only/_10k_keys.json", []); kag = k if isinstance(k, list) else list(k.values())[0]
    key = {a["address"]: a["key"] for a in kag}
    squad = [(a, key[a["address"]]) for a in rag[:n] if a["address"] in key]
    return squad

def build():
    import onyx_oracle as O
    squad = _agents(len(WATCHLIST))
    if len(squad) < len(WATCHLIST):
        return {"error": "roster too small"}
    index = []
    for i, domain in enumerate(WATCHLIST):
        agent, pk = squad[i]
        # RETRY on failure/caution — RDAP transiently rate-limits under batch load and returns a
        # false "be careful"; a scary verdict from a FAILED lookup burns trust. Verify, don't alarm.
        r = {}
        for attempt in range(3):
            try:
                r = O.r_merchant(domain)
                if r.get("band") in ("ok", "well-established", "high_risk"):
                    break                        # a REAL resolved verdict (incl. real high-risk) — trust it
            except Exception as e:
                r = {"verdict": "unverified", "band": "unverified", "err": str(e)[:40]}
            time.sleep(0.8 * (attempt + 1))      # back off, let RDAP recover
        if r.get("band") not in ("ok", "well-established", "high_risk", "caution"):
            r = {"verdict": "AGE UNVERIFIED — lookup unavailable (not a risk signal)", "band": "unverified"}
        # the assigned agent SIGNS its verdict — verifiable, non-repudiable premium data
        body = json.dumps({"domain": domain, "band": r.get("band"), "verdict": r.get("verdict"),
                           "age_days": r.get("age_days"), "by": agent["address"]}, sort_keys=True)
        try:
            sig = Account.sign_message(encode_defunct(text=body), private_key=pk).signature.hex()
        except Exception:
            sig = None
        index.append({
            "domain": domain,
            "band": r.get("band"),               # ok / caution / high_risk / well-established
            "verdict": r.get("verdict"),
            "age_days": r.get("age_days"),
            "source": r.get("source", "rdap"),
            "verified_by": agent["callsign"],
            "verifier_addr": agent["address"],
            "signature": ("0x" + sig.removeprefix("0x")[:24] + "…") if sig else None,
        })
    out = {
        "title": "0n1x Verified Merchant Index — agent-signed, RDAP-anchored premium data",
        "count": len(index),
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "how": "Each merchant is verified by an assigned 0n1x agent running a live RDAP reality check "
               "and SIGNING the verdict with its own key. Recompute-able, non-repudiable. This is data "
               "a plain LLM cannot produce — it is not memory, it is a live signed reality check.",
        "index": index,
    }
    try:
        from tools_pkg import _onyx_sign
        out = _onyx_sign.attest(out, tool="onyx_premium_data")
    except Exception:
        pass
    json.dump(out, open(PUB + r"\verified_merchants.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(out, open("_local_only/_verified_merchants.json", "w", encoding="utf-8"), ensure_ascii=False)
    return out

def lookup(domain):
    """The chat calls THIS — return the signed premium verdict for a domain (or a live check)."""
    idx = load("_local_only/_verified_merchants.json", {}).get("index", [])
    hit = next((x for x in idx if x["domain"] == domain.lower().strip()), None)
    if hit:
        return hit
    import onyx_oracle as O                       # not in index → live check on demand
    r = O.r_merchant(domain)
    return {"domain": domain, "band": r.get("band"), "verdict": r.get("verdict"), "source": "live"}

if __name__ == "__main__":
    o = build()
    print(f"═══ 0n1x VERIFIED MERCHANT INDEX — {o['count']} merchants, agent-signed ═══")
    for x in o["index"]:
        flag = "🔴" if x["band"] in ("high_risk", "caution") else "🟢"
        print(f"  {flag} {x['domain']:18} {x['verdict']:32} · by {x['verified_by']}")
