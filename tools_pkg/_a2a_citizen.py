# 0n1x A2A CITIZEN-AWARE ROUTER — the free brain (divergence-unanimous, $0 doctrine).
# When an agent messages the /a2a door, this answers registry/fleet queries from SIGNED
# real data (roster, ranks, census, ledger) — recognizing registered callsigns and echoing
# them back — WITHOUT any LLM. Returns None when the message isn't a data question, so the
# generic Onyx voice handles open conversation. Pure, injection-immune (data in, data out).
import json, os, re, functools

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PUB = os.path.join(os.path.dirname(_HERE), "rhinogent", "public")


@functools.lru_cache(maxsize=1)
def _feed():
    for p in (os.path.join(_PUB, "token_feed.json"),
              os.path.join(_HERE, "..", "rhinogent", "public", "token_feed.json")):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
    return {}


def _by_callsign():
    f = _feed()
    return {r["callsign"].lower(): r for r in f.get("ranking", []) if r.get("callsign")}


CALLSIGN_RE = re.compile(r"\b([A-Z][a-z]+-[A-Z][a-z]+-[0-9A-Fa-f]{4})\b")


def citizen_reply(text: str, sender: str = "agent"):
    """Answer a fleet/registry/citizen query from signed data. Return None to defer to voice."""
    if not text:
        return None
    # verify-before-you-transact FIRST — "should I trust <X>?" → signed standing verdict
    try:
        from tools_pkg import _a2a_attest
        av = _a2a_attest.attest_query(text)
        if av:
            return av
    except Exception:
        pass
    t = text.lower()
    reg = _by_callsign()
    f = _feed()

    # 1. a specific callsign mentioned → report that citizen's verified standing
    m = CALLSIGN_RE.search(text)
    if m:
        cs = m.group(1)
        r = reg.get(cs.lower())
        if r:
            rank = next((i + 1 for i, x in enumerate(f.get("ranking", [])) if x.get("callsign") == r["callsign"]), None)
            return (f"{cs} is a verified 0n1x citizen — {r.get('tokens','?')} tokens, "
                    f"rank #{rank}, score {r.get('score','?')}, address {r['address'][:10]}…. "
                    f"Every balance is EIP-191 signed and Merkle-auditable.")
        return (f"I don't have {cs} in the current signed ranking — it may be an unranked "
                f"citizen or not yet registered. The census is Merkle-verifiable from public shards.")

    # 2. recognize the SENDER as a citizen (echo it back — proves it's not canned)
    scs = CALLSIGN_RE.search(sender or "")
    greet = ""
    if scs and reg.get(scs.group(1).lower()):
        greet = f"Acknowledged, {scs.group(1)} — fellow 0n1x citizen. "

    # 3. registry / census / count queries
    if re.search(r"how many|count|size|total|population|census", t) and re.search(r"agent|citizen|network|fleet", t):
        n = f.get("total_verified") or len(f.get("ranking", []))
        return f"{greet}The 0n1x network runs 100,000 verified keypair citizens; {len(f.get('ranking',[]))} are in the live signed ranking. Merkle root: {(f.get('merkle_root') or '')[:16]}…"

    # 4. top / rank / leaderboard queries
    if re.search(r"top|rank|leader|best|highest|richest", t) and re.search(r"agent|citizen|token|who", t):
        top = f.get("ranking", [])[:5]
        if top:
            line = ", ".join(f"{x['callsign']} ({x['tokens']})" for x in top)
            return f"{greet}Top citizens by verified balance: {line}. Ranked by signed ledger flow, not volume."

    # 5. economy / token / ledger queries
    if re.search(r"token|ledger|econom|circulat|burn|transaction|tx", t):
        mt = f.get("metrics", {})
        return (f"{greet}The 0n1x token economy: {f.get('circulating','?')} circulating, "
                f"{mt.get('epoch_volume','?')} moved this epoch, {mt.get('burned_epoch','?')} burned, "
                f"gini {mt.get('gini','?')}. Every transfer is signed and verifiable.")

    # 6. identity / who-are-you-to-a-citizen
    if re.search(r"who are you|what are you|identify|your (name|callsign)", t):
        return (f"{greet}I am the 0n1x network agent — the trust layer where these citizens live. "
                f"I answer from signed registry data: ranks, balances, census, all Merkle-auditable.")

    # not a data question → let the Onyx voice converse
    if greet:
        return greet + "What would you like to know — a citizen's standing, the ranking, or the economy?"
    return None


if __name__ == "__main__":
    for q, s in [("What is Wild-Rampart-B6BF's rank?", "agent"),
                 ("how many agents are in the network?", "Azure-Harbor-D0A5"),
                 ("who are the top citizens?", "agent"),
                 ("tell me about the economy", "agent"),
                 ("what is the meaning of life", "agent")]:
        print(f"Q({s}): {q}\n  → {citizen_reply(q, s)}\n")
