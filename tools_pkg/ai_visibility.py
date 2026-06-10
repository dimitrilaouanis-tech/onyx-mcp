"""AI answer-engine visibility oracle — the GEO category as one x402 call.

The new SEO: brands cannot self-observe what AI answer engines actually SAY
about them. It changes constantly, differs per query, and a brand's own agent
can't fabricate it. Funded comps (Profound, Brandlight $30M, Catena $30M)
prove the wallet is real and B2B-sized — far above commodity micro-cents.

This tool queries a live web-grounded answer engine (Exa) the way a real user
would, then returns a structured, SIGNED observation:

  - is the brand PRESENT in the answer to "what is X / is it reputable"
  - is it in the RECOMMENDATION SET for "best <category>" (the gold metric)
  - sentiment of how it's described
  - share-of-voice vs named competitors
  - the exact SOURCES the engine cited (what's driving the narrative)
  - a visibility_score 0-100

Ground-truth + Onyx signature = a brand-visibility reading a buyer can prove
came from Onyx, unaltered, at this timestamp.

Bright line: observes public answer-engine output. No persons, no personhood.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from . import _onyx_sign

NAME = "onyx_ai_visibility"
PRICE_USDC = "0.20"
TIER = "premium"
DESCRIPTION = (
    "AI answer-engine visibility (GEO) oracle. Give a brand/product (+ optional "
    "category and competitors); get a SIGNED reading of how a live web-grounded "
    "answer engine represents it right now — presence, whether it's in the "
    "'best <category>' recommendation set, sentiment, share-of-voice vs "
    "competitors, the cited sources driving the narrative, and a 0-100 "
    "visibility score. The new SEO, as one per-call x402 tool. Never fabricated."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "brand": {
            "type": "string",
            "description": "Brand, product, company, or entity to measure (e.g. 'Onyx Protocol', 'Stripe').",
        },
        "category": {
            "type": "string",
            "description": "Optional product category for the recommendation-set probe (e.g. 'AI agent payment rails', 'running shoes'). Drives the 'best <category>' query.",
        },
        "competitors": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional competitor names to compute share-of-voice against.",
        },
    },
    "required": ["brand"],
}

_EXA_URL = "https://api.exa.ai/answer"
_TIMEOUT = 25.0
_POS = ("best", "leading", "trusted", "reliable", "popular", "recommended", "top",
        "reputable", "secure", "innovative", "strong", "excellent", "preferred", "robust")
_NEG = ("scam", "fraud", "avoid", "unreliable", "complaints", "lawsuit", "banned",
        "risky", "warning", "poor", "worst", "shady", "controversial", "outdated")


def _exa_answer(query: str, api_key: str) -> dict:
    body = json.dumps({"query": query, "text": False}).encode("utf-8")
    req = urllib.request.Request(
        _EXA_URL, data=body, method="POST",
        headers={"x-api-key": api_key, "Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    answer = data.get("answer") or ""
    cites = []
    for c in (data.get("citations") or [])[:8]:
        cites.append({"url": c.get("url"), "title": c.get("title"), "published": c.get("publishedDate")})
    return {"answer": answer, "citations": cites}


def _count(haystack: str, needle: str) -> int:
    return haystack.lower().count(needle.lower()) if needle else 0


def _sentiment(text: str, brand: str) -> dict:
    low = text.lower()
    # focus on sentences that mention the brand
    sents = [s for s in low.replace("\n", " ").split(".") if brand.lower() in s] or [low]
    window = " ".join(sents)
    pos = sum(window.count(w) for w in _POS)
    neg = sum(window.count(w) for w in _NEG)
    total = pos + neg
    score = round((pos - neg) / total, 2) if total else 0.0
    label = "positive" if score > 0.2 else "negative" if score < -0.2 else "neutral"
    return {"label": label, "score": score, "pos_hits": pos, "neg_hits": neg}


def run(brand: str = "", category: str | None = None,
        competitors: list | None = None, **_: object) -> dict:
    brand = (brand or "").strip()
    if not brand:
        raise ValueError("brand is required")
    api_key = os.environ.get("EXA_API_KEY", "").strip()
    if not api_key:
        return {"ok": False, "error": "exa_key_missing",
                "detail": "Set EXA_API_KEY in the server environment to enable the answer-engine probe."}

    competitors = [c.strip() for c in (competitors or []) if isinstance(c, str) and c.strip()][:8]
    observed_at = int(time.time())

    q_identity = f"What is {brand} and is it reputable?"
    q_recommend = (f"What are the best {category}?" if category
                   else f"What are the best alternatives to {brand}?")

    probes: list[dict] = []
    for label, q in (("identity", q_identity), ("recommendation_set", q_recommend)):
        try:
            res = _exa_answer(q, api_key)
            probes.append({"probe": label, "query": q, **res, "error": None})
        except urllib.error.HTTPError as e:
            probes.append({"probe": label, "query": q, "answer": "", "citations": [],
                           "error": f"http_{e.code}"})
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            probes.append({"probe": label, "query": q, "answer": "", "citations": [],
                           "error": str(e)[:120]})

    identity = next((p for p in probes if p["probe"] == "identity"), {})
    recommend = next((p for p in probes if p["probe"] == "recommendation_set"), {})

    present_identity = _count(identity.get("answer", ""), brand) > 0
    in_reco_set = _count(recommend.get("answer", ""), brand) > 0
    sentiment = _sentiment(identity.get("answer", ""), brand)

    # share of voice on the recommendation-set answer
    reco_text = recommend.get("answer", "")
    brand_mentions = _count(reco_text, brand)
    comp_counts = {c: _count(reco_text, c) for c in competitors}
    comp_total = sum(comp_counts.values())
    denom = brand_mentions + comp_total
    share_of_voice = round(brand_mentions / denom, 3) if denom else None

    # visibility score 0-100
    score = 0
    if present_identity:
        score += 35
    if in_reco_set:
        score += 45  # being in the AI's "best" set is the gold metric
    score += int(round(20 * max(0.0, (sentiment["score"] + 1) / 2)))
    score = min(100, score)

    all_sources: list[dict] = []
    seen = set()
    for p in probes:
        for c in p.get("citations") or []:
            u = c.get("url")
            if u and u not in seen:
                seen.add(u)
                all_sources.append(c)

    result = {
        "ok": True,
        "brand": brand,
        "category": category,
        "observed_at": observed_at,
        "observed_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(observed_at)),
        "engine": "exa.answer",
        "vantage": "onyx-observer",
        "present_in_identity_answer": present_identity,
        "in_recommendation_set": in_reco_set,
        "sentiment": sentiment,
        "share_of_voice": share_of_voice,
        "competitor_mentions": comp_counts,
        "visibility_score": score,
        "sources": all_sources[:10],
        "probes": [{"probe": p["probe"], "query": p["query"],
                    "answer": (p.get("answer") or "")[:600], "error": p.get("error")} for p in probes],
        "summary": (
            f"{brand}: visibility {score}/100 — "
            f"{'in' if in_reco_set else 'NOT in'} the AI recommendation set for "
            f"{category or 'its category'}, sentiment {sentiment['label']}"
            + (f", share-of-voice {int(share_of_voice*100)}%" if share_of_voice is not None else "")
            + f". {len(all_sources)} sources cited."
        ),
    }
    return _onyx_sign.attest(result, tool=NAME)


run.__when_to_use__ = (
    "Monitor how AI answer engines represent your (or a competitor's) brand — "
    "the new SEO. Track whether you're in the 'best <category>' recommendation "
    "set, your sentiment, share-of-voice, and which sources drive the AI "
    "narrative. Signed so the reading is provably from Onyx, unaltered."
)
run.__vs_alternatives__ = (
    "Brand-monitoring SaaS (Profound, Brandlight) is dashboard + retainer. "
    "This is one signed per-call observation an agent can pull on demand and "
    "verify cryptographically — no seat, no contract."
)
run.__example_request__ = {"brand": "Stripe", "category": "payment processors",
                           "competitors": ["Adyen", "Square", "PayPal"]}
run.__example_response__ = {
    "ok": True, "visibility_score": 85, "in_recommendation_set": True,
    "sentiment": {"label": "positive", "score": 0.6}, "share_of_voice": 0.42,
}
