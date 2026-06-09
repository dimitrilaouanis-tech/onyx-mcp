"""Reputation / review ground-truth oracle — what real customers say, signed.

Sibling of onyx_ai_visibility. Where that measures what AI engines say, this
measures what HUMANS say: a live, web-grounded read of a product/business/
service's real reputation — sentiment, recurring pros & cons, and the sources
behind them. An agent about to recommend, buy from, or partner with an entity
can pull one signed reputation reading instead of hallucinating "it's great."

Bright line: observes public review/reputation signal. No persons, no
personhood claims.
"""
from __future__ import annotations

import time
import urllib.error

from . import _onyx_sign
from .ai_visibility import _exa_answer, _sentiment  # one Exa impl, fix-in-one-place

import os

NAME = "onyx_review_truth"
PRICE_USDC = "0.06"
TIER = "premium"
DESCRIPTION = (
    "Reputation ground-truth oracle. Give a product/business/service (+ optional "
    "aspect like 'shipping' or 'support'); get a SIGNED, web-grounded read of "
    "what real customers say right now — the aggregated public sentiment and the "
    "cited sources, as actually observed. Onyx attests WHAT WAS OBSERVED, not a "
    "trust ruling: the agent forms its own judgment from the signed evidence. "
    "For an agent about to recommend, buy from, or partner with an entity. "
    "Never fabricated."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "entity": {
            "type": "string",
            "description": "Product, business, service, or seller to check the live reputation of.",
        },
        "aspect": {
            "type": "string",
            "description": "Optional specific aspect to focus on (e.g. 'shipping speed', 'customer support', 'refunds').",
        },
    },
    "required": ["entity"],
}


def run(entity: str = "", aspect: str | None = None, **_: object) -> dict:
    entity = (entity or "").strip()
    if not entity:
        raise ValueError("entity is required")
    api_key = os.environ.get("EXA_API_KEY", "").strip()
    if not api_key:
        return {"ok": False, "error": "exa_key_missing",
                "detail": "Set EXA_API_KEY in the server environment to enable the review probe."}

    observed_at = int(time.time())
    focus = f" regarding {aspect}" if aspect else ""
    query = (f"What do real customers say about {entity}{focus}? "
             f"Summarize the main pros and cons and whether it is trustworthy.")

    try:
        res = _exa_answer(query, api_key)
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"exa_http_{e.code}", "entity": entity, "observed_at": observed_at}
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        return {"ok": False, "error": "exa_unreachable", "detail": str(e)[:160],
                "entity": entity, "observed_at": observed_at}

    answer = res.get("answer", "")
    sentiment = _sentiment(answer, entity)
    sources = res.get("citations", [])[:10]

    # We sign FACTS, not JUDGMENTS. Onyx attests exactly what it observed —
    # the sources returned and the sentiment of their aggregated text at this
    # instant — NOT a "trusted/untrusted" ruling on a named entity. Signing a
    # trust verdict (an opinion derived from soft sentiment) would be a
    # non-repudiable, attributable claim against a real business: a defamation
    # surface AND the "signing a guess" failure mode. The caller draws the
    # conclusion from the signed evidence; the signature only guarantees the
    # evidence is real and unaltered.
    result = {
        "ok": True,
        "entity": entity,
        "aspect": aspect,
        "observed_at": observed_at,
        "observed_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(observed_at)),
        "engine": "exa.answer",
        "vantage": "onyx-observer",
        "observed_sentiment": sentiment,        # sentiment OF the returned text — a fact about the text
        "answer": answer[:900],                 # Exa's summary, attributed to the engine
        "sources": sources,                     # the cited pages actually returned — a fact
        "source_count": len(res.get("citations", [])),
        "attested_claim": "observation",        # NOT a trust determination
        "disclaimer": (
            "Onyx attests the sources observed and the sentiment of their "
            "aggregated text at observed_at. This is NOT a verified determination "
            "that the entity is trustworthy or untrustworthy — the agent must form "
            "its own judgment from the cited sources."
        ),
        "summary": (
            f"{entity}: observed sentiment {sentiment['label']} (score {sentiment['score']}) "
            f"across {len(res.get('citations', []))} cited sources. Evidence signed; "
            f"trust conclusion left to the caller."
        ),
    }
    return _onyx_sign.attest(result, tool=NAME)


run.__when_to_use__ = (
    "Before an agent recommends, purchases from, or partners with a "
    "product/business/seller. To get a live, signed reputation reading instead "
    "of a hallucinated 'it's reputable'. Optionally focus on one aspect."
)
run.__vs_alternatives__ = (
    "Generic web search returns links to parse. Review-aggregator APIs are "
    "platform-locked and rate-limited. This returns one signed, sourced "
    "sentiment observation an agent can act on and verify — with the trust "
    "conclusion left to the agent (we attest evidence, not opinions)."
)
run.__example_request__ = {"entity": "Acme Hosting", "aspect": "uptime"}
run.__example_response__ = {"ok": True, "attested_claim": "observation",
                            "observed_sentiment": {"label": "neutral", "score": 0.1},
                            "source_count": 7}
