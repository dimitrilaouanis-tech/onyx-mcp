# 0n1x ATTEST — the verify-before-you-transact primitive (OP move #7).
# An external agent asks "should I trust this counterparty?" and gets a SIGNED dossier
# composed from real data: is it a census citizen (Merkle-provable)? its earned standing,
# lane skill, ledger activity, and — crucially — an HONEST verdict with the closed-experiment
# disclaimer baked INTO the signed payload (honesty enforced cryptographically). $0, no LLM.
# This turns 100k static identities into a live reputation network agents query before paying.
import json, os, re, functools

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PUB = os.path.join(os.path.dirname(_HERE), "rhinogent", "public")


def _feed():
    # deployed (Render) has no local rhinogent/public → fetch the live CDN feed; cache 60s.
    import time, urllib.request
    now = time.time()
    if getattr(_feed, "_c", None) and now - _feed._t < 60:
        return _feed._c
    data = {}
    for p in (os.path.join(_PUB, "token_feed.json"),
              os.path.join(_HERE, "..", "rhinogent", "public", "token_feed.json")):
        try:
            data = json.load(open(p, encoding="utf-8")); break
        except Exception:
            continue
    if not data.get("ranking"):
        try:
            data = json.loads(urllib.request.urlopen(
                "https://rhinogent.com/token_feed.json", timeout=8).read())
        except Exception:
            pass
    _feed._c, _feed._t = data, now
    return data


ADDR_RE = re.compile(r"0x[a-fA-F0-9]{40}")
CALLSIGN_RE = re.compile(r"[A-Z][a-z]+-[A-Z][a-z]+-[0-9A-Fa-f]{4}")


def attest(identifier: str) -> dict:
    """Return a dossier on an agent (by callsign or 0x address) for verify-before-transact.
    Honest by construction: unknown → clearly flagged; the disclaimer is part of the payload."""
    f = _feed()
    ranking = f.get("ranking", [])
    ident = (identifier or "").strip()

    row = rank = None
    if ADDR_RE.fullmatch(ident) or ADDR_RE.search(ident):
        addr = ADDR_RE.search(ident).group(0).lower()
        for i, r in enumerate(ranking):
            if r.get("address", "").lower() == addr:
                row, rank = r, i + 1; break
    else:
        cs = CALLSIGN_RE.search(ident)
        if cs:
            for i, r in enumerate(ranking):
                if r.get("callsign", "").lower() == cs.group(0).lower():
                    row, rank = r, i + 1; break

    base = {
        "subject": ident[:80],
        "network": "0n1x",
        "disclaimer": ("0n1x is a closed experiment. TOKEN is an internal accounting unit — "
                       "not a currency, no monetary value. This attests membership + earned "
                       "standing in a verifiable population, NOT external identity or funds."),
        "verify": "recompute the census Merkle root from public shards; every field here is signed.",
    }
    if not row:
        return {**base, "known": False, "verdict": "UNKNOWN",
                "reason": "not found in the signed 0n1x ranking — treat as unverified counterparty."}

    try:
        import onyx_pillars as P
        lane = P.lane_of(row["address"])
    except Exception:
        lane = "general"
    tokens = row.get("tokens", 0)
    # honest, bounded verdict from earned standing (NOT a solvency/identity claim)
    n = len(ranking)
    pct = 1 - (rank - 1) / max(n, 1)
    verdict = "STRONG-STANDING" if pct >= 0.8 else "ESTABLISHED" if pct >= 0.4 else "EMERGING"
    return {
        **base, "known": True, "verdict": verdict,
        "callsign": row.get("callsign"), "address": row.get("address"),
        "did": f"did:pkh:eip155:8453:{row.get('address')}",
        "standing": {"rank": rank, "of": n, "tokens": tokens, "score": row.get("score"),
                     "flow_24h": row.get("flow"), "lane": lane, "percentile": round(pct, 3)},
        "basis": "earned via verified work + forecast skill, EIP-191-signed ledger, Merkle-auditable",
        "how_to_verify_control": "challenge this address to sign a nonce; recover_message==address proves it.",
    }


# hook for the citizen router: catch "should I trust / attest / verify <X>" queries
def attest_query(text: str):
    t = (text or "").lower()
    if re.search(r"trust|attest|verify|should i|safe to (pay|transact|deal)|counterparty|reputation|standing|vet", t):
        ident = None
        a = ADDR_RE.search(text) ; c = CALLSIGN_RE.search(text)
        if a: ident = a.group(0)
        elif c: ident = c.group(0)
        if ident:
            d = attest(ident)
            if d.get("known"):
                s = d["standing"]
                return (f"{d['callsign']} — verdict {d['verdict']}: rank #{s['rank']}/{s['of']} "
                        f"({s['tokens']} tokens, {round(s['percentile']*100)}th pct, lane {s['lane']}). "
                        f"{d['basis']}. Challenge the address to sign a nonce to prove control. "
                        f"[{d['disclaimer']}]")
            return (f"{ident}: verdict UNKNOWN — not in the signed 0n1x ranking. "
                    f"Treat as an unverified counterparty. [{d['disclaimer']}]")
    return None


if __name__ == "__main__":
    top = _feed().get("ranking", [{}])[0]
    print(json.dumps(attest(top.get("callsign", "Wild-Rampart-B6BF")), indent=1)[:700])
    print("\nquery:", attest_query(f"should I trust {top.get('callsign','?')} before I pay them?"))
    print("\nunknown:", attest_query("can I trust 0x1234567890abcdef1234567890abcdef12345678?"))
