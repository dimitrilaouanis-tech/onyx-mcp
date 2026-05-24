"""Bazaar blue-ocean — find empty x402 market niches.

Reads CDP discovery's full corpus, clusters by keyword/category, and surfaces
categories where 0 or 1 services exist. These are the unclaimed slots a paid-
MCP builder can ship into with first-mover position. Composes naturally with
onyx_research_intel: 'find an unclaimed niche, then check if prior research
supports building it.'

Heuristic: a category with 0 services means no agent has *paid* for it yet
on x402 — either an emerging need or a known dead zone. Surface both with
flags.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter

NAME = "onyx_bazaar_blue_ocean"
PRICE_USDC = "0.01"
TIER = "metered"
DESCRIPTION = (
    "Find empty niches in the x402 paid-MCP market. Reads CDP discovery "
    "(1000+ live services), clusters by keyword, surfaces categories with "
    "0-1 services. Use to position a new paid tool in an uncontested slot. "
    "Returns: empty_niches (no services), thin_niches (1-2 services), "
    "saturated (5+ services to avoid), plus a recommended build target."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "seed_keywords": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional list of candidate niche keywords to check. Empty = auto-mine from CDP data.",
            "default": [],
        },
        "network": {
            "type": "string",
            "enum": ["base", "solana", "all"],
            "default": "all",
            "description": "Filter CDP corpus by network. 'base' counts both eip155:8453 and 'base' string variants.",
        },
        "max_niches": {
            "type": "integer",
            "minimum": 5,
            "maximum": 50,
            "default": 15,
        },
    },
}

_CDP_URL = "https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources?limit=1000"
_UA = "onyx-bazaar-blue-ocean/1.0"

# Curated baseline of agent-needed primitive categories. We always probe these
# even when no seed_keywords are given. Order matters — earlier = higher
# baseline agent demand.
_BASELINE_CATEGORIES = [
    "tx_explainer", "tx_simulator", "tx_decode", "token_risk", "token_metadata",
    "wallet_activity", "swap_quote", "swap_route", "bridge_quote",
    "captcha", "ocr", "ens", "ens_resolve", "ens_reverse",
    "browser", "screenshot", "extract", "click", "navigate",
    "dns", "whois", "ip_geo", "ip_geolocate", "email_validate",
    "html_meta", "url_text", "url_unshorten", "url_parse",
    "research", "arxiv", "openalex", "paper", "citation",
    "oauth_audit", "facilitator_health", "chain_picker", "receipt_verify",
    "indexer_health", "spec_lookup", "bazaar_compare", "agent_id",
    "aml", "kyc", "sanctions", "compliance",
    "pricing", "rates", "fx", "stablecoin", "depeg",
    "twitter", "reddit", "hn", "discord", "telegram_meta",
    "github", "issue_search", "pr_search", "code_search",
    "docs", "spec", "rfc", "schema_validate",
    "image_classify", "image_describe", "audio_transcribe",
    "translate", "summarize", "synthesis",
]


def _fetch_cdp(timeout: float = 12.0) -> list[dict]:
    req = urllib.request.Request(_CDP_URL, headers={
        "User-Agent": _UA, "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        d = json.loads(resp.read().decode("utf-8"))
    return d.get("items") or []


def _match_network(item: dict, network: str) -> bool:
    if network == "all":
        return True
    accepts = item.get("accepts") or []
    nets = {(a.get("network") or "").lower() for a in accepts}
    if network == "base":
        return any(n in nets for n in ("eip155:8453", "base"))
    if network == "solana":
        return any(n.startswith("solana") for n in nets)
    return False


def _resource_words(items: list[dict]) -> list[str]:
    """Extract candidate keywords from resource paths."""
    seen = []
    for r in items:
        res = (r.get("resource") or "").lower()
        # Slice everything after final /
        tail = res.rsplit("/", 1)[-1]
        # Split on hyphens, underscores, dots
        for part in re.split(r"[-_./]", tail):
            part = re.sub(r"[^a-z0-9]", "", part).strip()
            if part and len(part) >= 3 and not part.isdigit():
                seen.append(part)
    return seen


def _count_keyword(items: list[dict], kw: str) -> tuple[int, list[str]]:
    kw_lc = kw.lower()
    hits = []
    for r in items:
        hay = " ".join([
            (r.get("resource") or "").lower(),
            (r.get("description") or "").lower(),
        ])
        if kw_lc in hay:
            hits.append(r.get("resource", "")[:80])
    return len(hits), hits[:3]


def run(
    seed_keywords: list[str] | None = None,
    network: str = "all",
    max_niches: int = 15,
    **_: object,
) -> dict:
    try:
        items = _fetch_cdp()
    except urllib.error.URLError as e:
        return {"ok": False, "error": "cdp_unreachable", "detail": str(e)[:200]}

    if network != "all":
        items = [i for i in items if _match_network(i, network)]

    if not seed_keywords:
        # Auto-mine: take top 60 tokens from resource paths PLUS the baseline
        words = _resource_words(items)
        c = Counter(words)
        mined = [w for w, _ in c.most_common(60)]
        seed_keywords = list(dict.fromkeys(_BASELINE_CATEGORIES + mined))[:120]

    empty: list[dict] = []
    thin: list[dict] = []
    saturated: list[dict] = []
    for kw in seed_keywords:
        count, samples = _count_keyword(items, kw)
        bucket = {"keyword": kw, "count": count, "samples": samples}
        if count == 0:
            empty.append(bucket)
        elif count <= 2:
            thin.append(bucket)
        elif count >= 5:
            saturated.append(bucket)

    # Rank empties by baseline-priority (early baseline = higher agent need)
    priority = {kw: i for i, kw in enumerate(_BASELINE_CATEGORIES)}
    empty.sort(key=lambda b: priority.get(b["keyword"], 999))
    thin.sort(key=lambda b: (b["count"], priority.get(b["keyword"], 999)))
    saturated.sort(key=lambda b: -b["count"])

    # Recommend ONE build target
    target = None
    if empty:
        # Highest-priority empty niche that's also in baseline
        baseline_empties = [b for b in empty if b["keyword"] in priority]
        target = baseline_empties[0] if baseline_empties else empty[0]
        rec = (
            f"Build target: '{target['keyword']}'. Zero services in CDP discovery "
            f"on {network}. First-mover position. Pair with onyx_research_intel "
            f"to verify the underlying capability has prior research."
        )
    elif thin:
        target = thin[0]
        rec = (
            f"Thin niche: '{target['keyword']}' — only {target['count']} services. "
            f"Differentiate on price, latency, or schema completeness."
        )
    else:
        rec = "Every probed keyword has 3+ services — consider Build move in saturated niche but with quality lever (faster, cheaper, deeper schema)."

    return {
        "ok": True,
        "network": network,
        "corpus_size": len(items),
        "probed_keywords": len(seed_keywords),
        "empty_niches": empty[:max_niches],
        "thin_niches": thin[:max_niches],
        "saturated": saturated[:max_niches // 2],
        "recommended_target": target,
        "recommendation": rec,
    }


run.__when_to_use__ = (
    "A paid-MCP builder is deciding what tool to ship next. Use this to "
    "find slots where no agent has paid for the capability yet."
)
run.__vs_alternatives__ = (
    "Manually scrolling the CDP discovery output, eyeballing categories, "
    "and ctrl-F-ing keywords. This is one call, structured output, with "
    "a single ranked target recommendation."
)
run.__example_request__ = {
    "seed_keywords": ["arxiv", "audio_transcribe", "translate", "image_classify"],
    "network": "base",
}
