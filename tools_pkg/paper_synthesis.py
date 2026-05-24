"""Paper synthesis — given N OpenAlex/DOI IDs, return structured comparison.

Composes naturally after research_intel. Workflow:
  1. Agent: onyx_research_intel(query='X') -> 5 candidate papers
  2. Agent: onyx_paper_synthesis(ids=[3 most-relevant])
     -> structured comparison + thematic synthesis + agent-actionable summary

Does NOT call out to an LLM — synthesis is structural (abstract overlap,
citation network, year/venue clustering). The agent reads the structured
output and forms its own narrative if it wants one.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter

NAME = "onyx_paper_synthesis"
PRICE_USDC = "0.03"
TIER = "metered"
DESCRIPTION = (
    "Structured synthesis across N academic papers. Input: 2-10 OpenAlex IDs "
    "or DOIs. Output: per-paper metadata (title, year, citations, abstract), "
    "thematic overlap (shared keywords across abstracts), citation co-graph "
    "(papers that cite multiple inputs), and an agent-actionable summary "
    "stating what's converged vs contested. Composes after onyx_research_intel."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "ids": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 2,
            "maxItems": 10,
            "description": "OpenAlex work IDs (W123..., or full URL) or DOIs (10.xxxx/...).",
        },
    },
    "required": ["ids"],
}

_UA = "onyx-paper-synthesis/1.0 (mailto:hello@onyx-actions.example)"


def _normalize_id(raw: str) -> str:
    s = (raw or "").strip()
    if s.startswith("https://openalex.org/"):
        return s.split("/")[-1]
    if s.startswith("openalex:"):
        return s.split(":", 1)[1]
    if s.startswith("W") and s[1:].isdigit():
        return s
    if s.startswith("10."):
        return f"doi:{s}"
    if s.startswith("doi:"):
        return s
    return s


def _fetch(id_: str, timeout: float = 10.0) -> dict | None:
    norm = _normalize_id(id_)
    if norm.startswith("doi:"):
        url = f"https://api.openalex.org/works/https://doi.org/{urllib.parse.quote(norm[4:], safe='')}"
    else:
        url = f"https://api.openalex.org/works/{norm}"
    req = urllib.request.Request(url, headers={
        "User-Agent": _UA, "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError):
        return None


def _reconstruct_abstract(inverted: dict | None) -> str:
    if not inverted or not isinstance(inverted, dict):
        return ""
    pos_to_token: dict[int, str] = {}
    for token, positions in inverted.items():
        for p in positions:
            pos_to_token[p] = token
    if not pos_to_token:
        return ""
    return " ".join(pos_to_token[i] for i in sorted(pos_to_token))


def _shape(w: dict) -> dict:
    authors = [
        (a.get("author") or {}).get("display_name")
        for a in (w.get("authorships") or [])[:5]
        if (a.get("author") or {}).get("display_name")
    ]
    abstract = _reconstruct_abstract(w.get("abstract_inverted_index"))
    return {
        "id": w.get("id"),
        "title": w.get("title"),
        "year": w.get("publication_year"),
        "citations": w.get("cited_by_count") or 0,
        "authors": authors,
        "doi": w.get("doi"),
        "abstract_full": abstract,
        "abstract_excerpt": abstract[:300] + ("…" if len(abstract) > 300 else ""),
        "referenced_works": w.get("referenced_works") or [],
    }


_STOP = {
    "the", "and", "for", "with", "that", "this", "these", "those", "from", "into",
    "are", "was", "were", "been", "being", "have", "has", "had", "but", "not",
    "all", "any", "can", "may", "such", "than", "then", "they", "their", "them",
    "our", "ours", "its", "his", "her", "her", "one", "two", "also", "very",
    "use", "used", "using", "uses", "based", "show", "shows", "shown", "showed",
    "paper", "papers", "study", "studies", "work", "works", "abstract",
    "approach", "approaches", "method", "methods", "result", "results",
    "data", "model", "models", "task", "tasks", "system", "systems",
    "propose", "proposed", "present", "presented", "introduce", "introduces",
}


def _tokens(text: str) -> list[str]:
    out = []
    for w in (text or "").lower().split():
        w = "".join(c for c in w if c.isalnum())
        if len(w) >= 4 and w not in _STOP and not w.isdigit():
            out.append(w)
    return out


def _shared_keywords(papers: list[dict], min_papers: int = 2) -> list[dict]:
    """Tokens that appear in abstracts of at least min_papers."""
    paper_tokens = [set(_tokens(p.get("abstract_full", ""))) for p in papers]
    counts: Counter = Counter()
    for s in paper_tokens:
        for w in s:
            counts[w] += 1
    shared = [(w, c) for w, c in counts.items() if c >= min_papers]
    shared.sort(key=lambda x: (-x[1], x[0]))
    return [{"keyword": w, "papers": c} for w, c in shared[:20]]


def _citation_overlap(papers: list[dict]) -> dict:
    refs_by_paper = [set(p.get("referenced_works") or []) for p in papers]
    if not refs_by_paper:
        return {"shared_refs": 0, "examples": []}
    # Refs cited by at least 2 papers
    flat: Counter = Counter()
    for refs in refs_by_paper:
        for r in refs:
            flat[r] += 1
    shared = [(r, c) for r, c in flat.items() if c >= 2]
    shared.sort(key=lambda x: -x[1])
    return {
        "shared_refs": len(shared),
        "examples": [{"ref": r, "cited_by_n_inputs": c} for r, c in shared[:5]],
    }


def _agent_summary(papers: list[dict], shared_kws: list[dict], co: dict) -> str:
    n = len(papers)
    if n < 2:
        return "Need 2+ papers to synthesize."
    years = [p.get("year") for p in papers if p.get("year")]
    span = f"{min(years)}–{max(years)}" if years else "no year data"
    total_cit = sum(p.get("citations", 0) for p in papers)
    top_kw = shared_kws[0]["keyword"] if shared_kws else None
    pct_shared = (
        f"{shared_kws[0]['papers']}/{n} papers share '{top_kw}'"
        if top_kw else "no shared keywords"
    )
    if co["shared_refs"] >= 3:
        convergence = "high — papers share substantial citation base, work is converging"
    elif co["shared_refs"] >= 1:
        convergence = "moderate — some shared references"
    else:
        convergence = "low — these papers come from different lineages, may represent contested or fragmented field"
    return (
        f"{n} papers, {span}, {total_cit:,} total citations. "
        f"Shared keyword signal: {pct_shared}. "
        f"Citation convergence: {convergence}."
    )


def run(ids: list[str], **_: object) -> dict:
    if not isinstance(ids, list) or len(ids) < 2:
        return {"ok": False, "error": "need >=2 paper ids"}
    if len(ids) > 10:
        ids = ids[:10]

    raw = [_fetch(i) for i in ids]
    papers = [_shape(r) for r in raw if r]
    missing = [ids[i] for i, r in enumerate(raw) if not r]

    if len(papers) < 2:
        return {
            "ok": False,
            "error": "could_not_resolve_enough_papers",
            "resolved": len(papers),
            "missing": missing,
        }

    shared = _shared_keywords(papers)
    co = _citation_overlap(papers)
    summary = _agent_summary(papers, shared, co)

    # Strip the full abstract from outbound payload (keep excerpt only)
    for p in papers:
        p.pop("abstract_full", None)
        # Trim refs list to first 10
        if len(p.get("referenced_works") or []) > 10:
            p["referenced_works_n"] = len(p["referenced_works"])
            p["referenced_works"] = p["referenced_works"][:10]

    return {
        "ok": True,
        "requested": len(ids),
        "resolved": len(papers),
        "missing": missing,
        "papers": papers,
        "shared_keywords": shared,
        "citation_overlap": co,
        "synthesis": summary,
    }


run.__when_to_use__ = (
    "After calling onyx_research_intel and picking 2-10 papers, use this to "
    "structurally synthesize them in one call instead of fetching each."
)
run.__vs_alternatives__ = (
    "Per-paper OpenAlex calls (5-10 round trips) + LLM call to find shared "
    "themes (1000s of context tokens). This is one paid call, structured "
    "JSON, no LLM tokens consumed."
)
run.__example_request__ = {
    "ids": [
        "W4392267281",
        "W4385248213",
        "10.48550/arxiv.2308.11432",
    ],
}
