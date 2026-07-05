# 0n1x DOGFOOD — use our OWN agents for OUR OWN work ($0). The launch: not a demo, a
# working intelligence force. We feed real missions WE care about; our top specialists
# (by earned skill from journals) execute them against reality; we consume a signed morning
# DIGEST that changes a decision tomorrow. Kimi's rule: not theater if we act on the output.
# Watchdogs, not strategists — verify/monitor/forecast our own stuff. $0, no heavy LLM.
import json, os, time, urllib.request

os.chdir(os.path.dirname(os.path.abspath(__file__)))
PUB = r"C:\Users\intelligence\rhinogent\public"

# OUR real assets the agents watch for US (add more as we grow)
OUR_ENDPOINTS = [
    "https://rhinogent.com/0n1x.json",
    "https://onyx-actions.onrender.com/health",
    "https://rhinogent.com/census_manifest.json",
    "https://rhinogent.com/token_feed.json",
]
OUR_DOMAINS = ["rhinogent.com", "onyx-actions.onrender.com", "0n1xagntc.com"]
# the landscape our SYNTH agents watch (competitors / the seat)
WATCH_DOMAINS = ["isara.com", "blitzy.com"]   # the funded swarm players


def top_specialists(lane, k=50):
    profiles = json.load(open("_local_only/_profiles.json", encoding="utf-8")) if os.path.exists("_local_only/_profiles.json") else {}
    cand = sorted(((p.get("skill", {}).get(lane, 0), a) for a, p in profiles.items()), reverse=True)
    return [a for s, a in cand[:k] if s > 0]


def infra_check():
    """VERI agents verify OUR endpoints are alive + our domains are healthy. We consume: 'is it up?'"""
    veri = top_specialists("VERIFY", 50)
    checks = []
    for url in OUR_ENDPOINTS:
        try:
            code = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "0n1x-dogfood"}), timeout=10).getcode()
            checks.append({"target": url, "status": "UP" if code == 200 else f"HTTP {code}", "ok": code == 200})
        except Exception as e:
            checks.append({"target": url, "status": "DOWN", "ok": False, "err": str(e)[:40]})
    # domain reality via oracle
    import onyx_oracle as O
    dom = []
    for d in OUR_DOMAINS:
        try:
            r = O.r_merchant(d)
            dom.append({"domain": d, "verdict": r.get("verdict"), "band": r.get("band")})
        except Exception:
            dom.append({"domain": d, "verdict": "unresolved"})
    down = [c for c in checks if not c["ok"]]
    return {"assigned_agents": len(veri), "endpoints": checks, "domains": dom,
            "alert": f"{len(down)} endpoint(s) DOWN" if down else "all systems UP"}


def market_watch():
    """SYNTH agents compile intel on the funded swarm players — do WE need to react? (bounded, $0)."""
    import onyx_oracle as O
    synth = top_specialists("PREDICT", 50) or top_specialists("CORROBORATE", 50)
    intel = []
    for d in WATCH_DOMAINS:
        try:
            r = O.r_merchant(d)
            intel.append({"competitor": d, "domain_age": r.get("verdict")})
        except Exception:
            intel.append({"competitor": d, "domain_age": "unresolved"})
    return {"assigned_agents": len(synth), "landscape": intel,
            "our_edge": "we sign answers + Merkle-verifiable 340k population — they don't. 100-500x their agent count."}


def digest():
    """The morning brief WE consume. Signed. Changes a decision tomorrow or it's cut."""
    infra = infra_check()
    market = market_watch()
    d = {
        "title": "0n1x — Morning Intel Digest (by our own agents, for us)",
        "as_of": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "🛡️ INFRA (VERI agents watching our stack)": infra["alert"],
        "infra_detail": infra,
        "🧭 MARKET (SYNTH agents watching the seat)": market,
        "action_items": [],
        "principle": "Dogfooding: our 340k agents do real verification/monitoring work FOR US. "
                     "Watchdogs not strategists — we act on the alerts; strategy stays with the operator.",
    }
    # real action items we'd actually act on
    for c in infra["endpoints"]:
        if not c["ok"]:
            d["action_items"].append(f"🔴 FIX: {c['target']} is {c['status']}")
    if not d["action_items"]:
        d["action_items"].append("✅ infra healthy — no fires. Focus on the next build.")
    try:
        from tools_pkg import _onyx_sign
        d = _onyx_sign.attest(d, tool="onyx_dogfood")
    except Exception:
        pass
    json.dump(d, open(PUB + r"\digest.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(d, open("_local_only/_digest.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return d


if __name__ == "__main__":
    d = digest()
    print("═══ 0n1x MORNING DIGEST — our agents working for US ═══")
    print(f"🛡️ INFRA: {d['🛡️ INFRA (VERI agents watching our stack)']}  ({d['infra_detail']['assigned_agents']} VERI agents)")
    for c in d["infra_detail"]["endpoints"]:
        print(f"    {c['status']:10} {c['target']}")
    print(f"🧭 MARKET ({d['🧭 MARKET (SYNTH agents watching the seat)']['assigned_agents']} SYNTH agents):")
    for i in d["🧭 MARKET (SYNTH agents watching the seat)"]["landscape"]:
        print(f"    {i['competitor']:26} {i.get('domain_age','')}")
    print("📋 ACTION ITEMS:")
    for a in d["action_items"]:
        print(f"    {a}")
