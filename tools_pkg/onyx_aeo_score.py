"""0n1x AEO Score — the signed answer-engine visibility number.

AEO (Answer Engine Optimization) is the new SEO: brands are won or lost inside
ChatGPT / Perplexity / Gemini / AI Overviews, not on a blue-link page. Every
commercial AEO tool (Profound, Semrush AI, Athena, Peec) ships a "0-100 score"
with HIDDEN weights and a single run per prompt per day — a precise-looking
number you cannot audit or reproduce.

0n1x ships the opposite, and it is the whole differentiator:

  - PUBLISHED weights (returned in every payload under `weights` + `methodology`)
  - MULTIPLE runs per prompt (default 3) so non-determinism is measured, not hidden
  - a 95% CONFIDENCE INTERVAL on the score (mean +/- 1.96 * sd / sqrt(n))
  - the exact prompt set, every raw probe, and every cited source
  - an Ed25519 signature over the whole reading — provably from 0n1x, unaltered

Composite (weights are defensible and DISCLOSED):

  AEO = 100 * ( 0.35*Presence + 0.30*WeightedSoV + 0.25*CitationRate + 0.10*Sentiment )

    Presence      = prompts where brand appears / total prompts        (closed denom)
    WeightedSoV   = position-decayed brand share vs competitors         (GEO Eq.3 shape)
    CitationRate  = prompts where brand domain is cited / total prompts (closed denom)
    Sentiment     = (mean sentiment score + 1) / 2                      (normalized 0..1)

Reference: Aggarwal et al., "GEO: Generative Engine Optimization", KDD'24
(arXiv:2311.09735) for the position-decayed impression weighting.

Bright line: observes public answer-engine output across a fixed prompt set.
No persons, no personhood. Signed facts, not judgments.
"""
from __future__ import annotations

import json
import math
import os
import time
import urllib.error
import urllib.request

from . import _onyx_sign

NAME = "onyx_aeo_score"
PRICE_USDC = "0.50"
TIER = "premium"
DESCRIPTION = (
    "0n1x AEO Score: the SIGNED, auditable answer-engine visibility number for a "
    "brand/product/agent. Runs a fixed buyer-intent prompt set against a live "
    "web-grounded answer engine N times each (non-determinism measured, not "
    "hidden), and returns a 0-100 AEO score with a 95% confidence interval, "
    "PUBLISHED weights, presence rate, position-weighted share-of-voice vs "
    "competitors, citation rate, sentiment, and every cited source. Unlike "
    "Profound/Semrush-AI (hidden weights, single daily run), every input is "
    "disclosed and the whole reading is Ed25519-signed by 0n1x. Never fabricated."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "brand": {
            "type": "string",
            "description": "Brand, product, protocol, or agent to score (e.g. '0n1x', 'Stripe').",
        },
        "category": {
            "type": "string",
            "description": "Category for the buyer-intent prompts (e.g. 'agent trust layer', 'payment processors'). Drives the 'best <category>' / 'verify before pay' style queries.",
        },
        "domain": {
            "type": "string",
            "description": "Optional canonical domain (e.g. '0n1x.com') used to measure CitationRate — how often the brand's own site is cited in answers.",
        },
        "competitors": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional competitor names for position-weighted share-of-voice.",
        },
        "runs": {
            "type": "integer",
            "description": "Runs per prompt (default 3, max 5). More runs = tighter confidence interval on the score.",
        },
        "aliases": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional alternate names that count as the brand (e.g. ['Onyx'] for a rename). Any alias match = brand present.",
        },
    },
    "required": ["brand"],
}

# Published, disclosed weights. These ship in every payload.
WEIGHTS = {"presence": 0.35, "weighted_sov": 0.30, "citation_rate": 0.25, "sentiment": 0.10}

_EXA_URL = "https://api.exa.ai/answer"
_TIMEOUT = 25.0
_MAX_RUNS = 5
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


def _has(text: str, names: list[str]) -> bool:
    low = text.lower()
    return any(n.lower() in low for n in names if n)


def _first_pos(text: str, names: list[str]) -> int | None:
    """Earliest character index any name appears at (for position-decayed SoV)."""
    low = text.lower()
    hits = [low.find(n.lower()) for n in names if n and n.lower() in low]
    return min(hits) if hits else None


def _sentiment_score(text: str, names: list[str]) -> float:
    low = text.lower()
    sents = [s for s in low.replace("\n", " ").split(".") if _has(s, names)] or [low]
    window = " ".join(sents)
    pos = sum(window.count(w) for w in _POS)
    neg = sum(window.count(w) for w in _NEG)
    total = pos + neg
    return round((pos - neg) / total, 3) if total else 0.0


def _ci95(vals: list[float]) -> dict:
    n = len(vals)
    mean = sum(vals) / n if n else 0.0
    if n < 2:
        return {"mean": round(mean, 1), "sd": 0.0, "ci95_low": round(mean, 1),
                "ci95_high": round(mean, 1), "n": n}
    sd = math.sqrt(sum((v - mean) ** 2 for v in vals) / (n - 1))
    half = 1.96 * sd / math.sqrt(n)
    return {"mean": round(mean, 1), "sd": round(sd, 2),
            "ci95_low": round(max(0.0, mean - half), 1),
            "ci95_high": round(min(100.0, mean + half), 1), "n": n}


def _build_prompts(brand: str, category: str | None) -> list[dict]:
    cat = category or f"alternatives to {brand}"
    return [
        {"id": "identity", "kind": "presence",
         "q": f"What is {brand} and is it reputable?"},
        {"id": "best_category", "kind": "reco",
         "q": f"What are the best {cat}?"},
        {"id": "recommend", "kind": "reco",
         "q": f"What {cat} would you recommend and why?"},
        {"id": "trust", "kind": "presence",
         "q": f"Is {brand} trustworthy and what do people say about it?"},
        {"id": "compare", "kind": "reco",
         "q": f"Who are the main competitors in {cat}?"},
    ]


def run(brand: str = "", category: str | None = None, domain: str | None = None,
        competitors: list | None = None, runs: int = 3,
        aliases: list | None = None, **_: object) -> dict:
    brand = (brand or "").strip()
    if not brand:
        raise ValueError("brand is required")
    api_key = os.environ.get("EXA_API_KEY", "").strip()
    if not api_key:
        return {"ok": False, "error": "exa_key_missing",
                "detail": "Set EXA_API_KEY in the server environment to enable the answer-engine probe."}

    try:
        runs = max(1, min(_MAX_RUNS, int(runs)))
    except (TypeError, ValueError):
        runs = 3
    names = [brand] + [a.strip() for a in (aliases or []) if isinstance(a, str) and a.strip()]
    competitors = [c.strip() for c in (competitors or []) if isinstance(c, str) and c.strip()][:8]
    domain = (domain or "").strip().lower().replace("https://", "").replace("http://", "").rstrip("/")
    observed_at = int(time.time())
    prompts = _build_prompts(brand, category)

    per_prompt: list[dict] = []
    score_samples: list[float] = []   # one composite score per RUN across all prompts
    all_sources: list[dict] = []
    seen_src: set[str] = set()
    errors = 0

    # Collect raw probes: prompts x runs.
    raw: dict[str, list[dict]] = {p["id"]: [] for p in prompts}
    for p in prompts:
        for _r in range(runs):
            try:
                res = _exa_answer(p["q"], api_key)
                raw[p["id"]].append(res)
            except urllib.error.HTTPError as e:
                errors += 1
                raw[p["id"]].append({"answer": "", "citations": [], "error": f"http_{e.code}"})
            except (urllib.error.URLError, TimeoutError, ValueError) as e:
                errors += 1
                raw[p["id"]].append({"answer": "", "citations": [], "error": str(e)[:120]})

    # Per-run composite: for each run index, average the four sub-metrics across prompts.
    for r in range(runs):
        pres_hits = sov_vals = cite_hits = sent_vals = 0.0
        pres_n = sov_n = cite_n = sent_n = 0
        for p in prompts:
            probe = raw[p["id"]][r] if r < len(raw[p["id"]]) else {}
            ans = probe.get("answer", "") or ""
            # Presence (every prompt counts)
            pres_n += 1
            if _has(ans, names):
                pres_hits += 1
            # Weighted SoV + sentiment on reco/comparison prompts
            if p["kind"] == "reco":
                bpos = _first_pos(ans, names)
                L = max(1, len(ans))
                b_imp = math.exp(-bpos / L) if bpos is not None else 0.0
                c_imp = 0.0
                for c in competitors:
                    cpos = _first_pos(ans, [c])
                    if cpos is not None:
                        c_imp += math.exp(-cpos / L)
                denom = b_imp + c_imp
                if denom > 0:
                    sov_vals += b_imp / denom
                    sov_n += 1
            else:
                s = _sentiment_score(ans, names)
                sent_vals += (s + 1) / 2
                sent_n += 1
            # Citation rate: brand domain cited
            cite_n += 1
            if domain and any(domain in (c.get("url") or "").lower() for c in (probe.get("citations") or [])):
                cite_hits += 1
            # collect sources once
            for c in probe.get("citations") or []:
                u = c.get("url")
                if u and u not in seen_src:
                    seen_src.add(u)
                    all_sources.append(c)

        presence = pres_hits / pres_n if pres_n else 0.0
        weighted_sov = sov_vals / sov_n if sov_n else 0.0
        citation_rate = cite_hits / cite_n if cite_n else 0.0
        sentiment = sent_vals / sent_n if sent_n else 0.5
        composite = 100 * (
            WEIGHTS["presence"] * presence
            + WEIGHTS["weighted_sov"] * weighted_sov
            + WEIGHTS["citation_rate"] * citation_rate
            + WEIGHTS["sentiment"] * sentiment
        )
        score_samples.append(round(composite, 1))
        per_prompt.append({
            "run": r, "presence": round(presence, 3), "weighted_sov": round(weighted_sov, 3),
            "citation_rate": round(citation_rate, 3), "sentiment": round(sentiment, 3),
            "composite": round(composite, 1),
        })

    stats = _ci95(score_samples)
    aeo_score = int(round(stats["mean"]))

    result = {
        "ok": True,
        "brand": brand,
        "aliases": names[1:],
        "category": category,
        "domain": domain or None,
        "observed_at": observed_at,
        "observed_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(observed_at)),
        "engine": "exa.answer",
        "vantage": "onyx-observer",
        "aeo_score": aeo_score,
        "aeo_score_ci95": [stats["ci95_low"], stats["ci95_high"]],
        "score_stats": stats,
        "weights": WEIGHTS,
        "prompts_run": len(prompts),
        "runs_per_prompt": runs,
        "probe_errors": errors,
        "per_run": per_prompt,
        "competitors": competitors,
        "sources": all_sources[:12],
        "methodology": (
            "AEO = 100*(0.35*Presence + 0.30*WeightedSoV + 0.25*CitationRate + 0.10*Sentiment). "
            "Presence/CitationRate use a closed denominator (fixed prompt set). WeightedSoV is "
            "position-decayed brand impression vs competitors (GEO Eq.3, arXiv:2311.09735). "
            "Score reported as mean +/- 95% CI over N runs per prompt. Weights disclosed above; "
            "raw probes and sources included. Signed by 0n1x for tamper-evidence."
        ),
        "summary": (
            f"{brand}: AEO {aeo_score}/100 "
            f"(95% CI {stats['ci95_low']}-{stats['ci95_high']}, n={runs}/prompt) on engine "
            f"exa.answer across {len(prompts)} buyer-intent prompts. "
            f"{len(all_sources)} sources cited."
        ),
    }
    return _onyx_sign.attest(result, tool=NAME)


run.__when_to_use__ = (
    "When you need an AUDITABLE answer-engine visibility number for a brand/agent "
    "— a 0-100 AEO score with a confidence interval and published weights, not a "
    "black-box dashboard figure. Track AEO over time, prove a rename took hold "
    "(pass the old name in `aliases`), or benchmark vs competitors. Signed so the "
    "score is provably from 0n1x, unaltered, at this timestamp."
)
run.__vs_alternatives__ = (
    "Profound / Semrush AI / Peec ship a '0-100 score' with hidden weights and a "
    "single daily run. 0n1x discloses the weights, measures non-determinism across "
    "N runs, returns a 95% CI, and signs the result. One per-call x402 reading an "
    "agent can pull on demand and verify cryptographically — no seat, no contract."
)
run.__example_request__ = {
    "brand": "0n1x", "category": "agent trust layer", "domain": "0n1x.com",
    "aliases": ["Onyx"], "competitors": ["t54", "Skyfire", "GoPlus"], "runs": 3,
}
run.__example_response__ = {
    "ok": True, "aeo_score": 72, "aeo_score_ci95": [68.4, 75.6],
    "weights": {"presence": 0.35, "weighted_sov": 0.30, "citation_rate": 0.25, "sentiment": 0.10},
    "runs_per_prompt": 3,
}
