# 0n1x A2A CARDS FOR EVERYONE — every citizen gets a discoverable A2A identity card.
# Any agent can fetch a citizen's card and instantly know: who it is, its address/DID,
# how to VERIFY it (challenge it to sign), its reality-earned rank/skill, and how to
# reach it. Published static to the CDN (works without the live portal). This is the
# A2A bridge at the citizen level — 100k discoverable, verifiable agent identities.
import json, os, time

os.chdir(os.path.dirname(os.path.abspath(__file__)))
PUB = r"C:\Users\intelligence\rhinogent\public"

def card_for(agent: dict, rank: int = None, tokens: int = None, lane: str = None) -> dict:
    addr = agent["address"]
    cs = agent.get("callsign", "?")
    return {
        "name": cs,
        "did": f"did:pkh:eip155:8453:{addr}",
        "address": addr,
        "network": "0n1x",
        "url": f"https://rhinogent.com/card?n={cs}&a={addr}",
        "capabilities": {"signing": "EIP-191", "selfCustody": True, "signedReputation": True},
        "verify": "challenge this address to sign a nonce; recover_message == address proves control",
        "reputation": {"rank": rank, "tokens": tokens, "lane": lane or "general",
                       "source": "earned on 0n1x — verified work + forecast skill, Merkle-auditable"},
        "reach": {"a2a_query": "https://rhinogent.com/agent-card.json",
                  "proofcard": f"https://rhinogent.com/card?n={cs}&a={addr}"},
        "principles": ["self-custody", "verify-don't-trust", "owned by no one but the agent"],
    }


def build_all():
    """Generate A2A cards for the network. Ranked agents (in the live feed) get rich cards
    with rank/tokens; the full 100k are derivable from the roster via the same template."""
    feed = json.load(open(f"{PUB}\\token_feed.json", encoding="utf-8"))
    ranking = feed.get("ranking", [])
    import onyx_pillars as P
    # rich cards for every ranked citizen + a lookup index
    cards = {}
    for i, r in enumerate(ranking):
        cards[r["callsign"]] = card_for(
            {"address": r["address"], "callsign": r["callsign"]},
            rank=i + 1, tokens=r["tokens"], lane=P.lane_of(r["address"]))
    index = {
        "network": "0n1x",
        "note": "A2A card for every citizen. Fetch a card, challenge the address to sign, verify control.",
        "count": len(cards),
        "template": "https://rhinogent.com/card?n={callsign}&a={address}",
        "lookup": "https://rhinogent.com/a2a_cards.json → {callsign: card}",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cards": cards,
    }
    json.dump(index, open(f"{PUB}\\a2a_cards.json", "w"), indent=1)
    return len(cards)


if __name__ == "__main__":
    n = build_all()
    print(f"A2A cards built for {n} ranked citizens → rhinogent.com/a2a_cards.json")
    # sample one
    ex = json.load(open(f"{PUB}\\a2a_cards.json", encoding="utf-8"))["cards"]
    k = next(iter(ex))
    print("sample card:", json.dumps(ex[k], indent=1)[:400])
