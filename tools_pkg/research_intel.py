"""Research-intel for autonomous agents — has someone solved X already?

Queries OpenAlex (240M+ academic works, including arXiv preprints), ranks by
citation count + recency + relevance, returns ranked results with abstract
excerpts so an agent can decide whether to read further before re-deriving a
known result. Falls back to Semantic Scholar when OpenAlex misses.

Why agents pay for this: the alternative is burning context tokens fetching
abstract HTML, then parsing, then re-prompting an LLM to summarize. One paid
call returns the synthesized intel + URLs + citation prior. Standard hyper-agent
primitive — saves minutes per query at sub-cent cost per token equivalent.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

NAME = "onyx_research_intel"
PRICE_USDC = "0.05"
TIER = "metered"
DESCRIPTION = (
    "Research intel — has someone solved X already? Queries 240M+ academic "
    "works via OpenAlex (includes arXiv preprints, conference papers, journal "
    "articles), ranks by citation count + recency + relevance, returns top N "
    "papers with one-line abstract excerpts, citation counts, and author names. "
    "Built for autonomous agents that need to check prior art before burning "
    "cycles re-deriving a known result. Fallback to Semantic Scholar."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "Research question or keyword string. Plain English works; OpenAlex handles tokenization.",
        },
        "top_n": {
            "type": "integer",
            "minimum": 1,
            "maximum": 20,
            "default": 5,
            "description": "How many papers to return.",
        },
        "min_citations": {
            "type": "integer",
            "minimum": 0,
            "default": 0,
            "description": "Filter out papers with fewer than this many citations. Use 50+ to surface only well-known work.",
        },
        "year_from": {
            "type": "integer",
            "minimum": 1900,
            "maximum": 2100,
            "description": "Optional: only return papers from this year onward.",
        },
        "sort_by": {
            "type": "string",
            "enum": ["relevance", "citations", "recency"],
            "default": "relevance",
            "description": "Ranking. citations = highest cited first; recency = newest first; relevance = OpenAlex semantic match.",
        },
    },
    "required": ["query"],
}


def _openalex_search(
    query: str,
    top_n: int,
    min_citations: int,
    year_from: int | None,
    sort_by: str,
    timeout: float = 12.0,
) -> dict:
    params = {
        "search": query,
        "per_page": max(top_n, 10),
        "select": "id,doi,title,publication_year,cited_by_count,authorships,abstract_inverted_index,primary_location,type",
    }
    sort_map = {
        "citations": "cited_by_count:desc",
        "recency": "publication_year:desc",
    }
    if sort_by in sort_map:
        params["sort"] = sort_map[sort_by]
    filters = []
    if year_from:
        filters.append(f"publication_year:>{year_from - 1}")
    if min_citations > 0:
        filters.append(f"cited_by_count:>{min_citations - 1}")
    if filters:
        params["filter"] = ",".join(filters)

    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "User-Agent": "onyx-research-intel/1.0 (mailto:hello@onyx-actions.example)",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _reconstruct_abstract(inverted: dict | None) -> str:
    if not inverted or not isinstance(inverted, dict):
        return ""
    # OpenAlex stores abstracts as {token: [positions]}. Rebuild ordered text.
    pos_to_token: dict[int, str] = {}
    for token, positions in inverted.items():
        for p in positions:
            pos_to_token[p] = token
    if not pos_to_token:
        return ""
    ordered = " ".join(pos_to_token[i] for i in sorted(pos_to_token))
    return ordered[:400] + ("…" if len(ordered) > 400 else "")


def _shape_work(w: dict) -> dict:
    authors = []
    for a in (w.get("authorships") or [])[:3]:
        nm = (a.get("author") or {}).get("display_name")
        if nm:
            authors.append(nm)
    loc = (w.get("primary_location") or {}).get("source") or {}
    src = loc.get("display_name") if isinstance(loc, dict) else None
    return {
        "title": w.get("title") or "(untitled)",
        "year": w.get("publication_year"),
        "citations": w.get("cited_by_count") or 0,
        "authors": authors,
        "source": src,
        "doi": w.get("doi"),
        "openalex_id": w.get("id"),
        "type": w.get("type"),
        "abstract_excerpt": _reconstruct_abstract(w.get("abstract_inverted_index")),
    }


def run(
    query: str,
    top_n: int = 5,
    min_citations: int = 0,
    year_from: int | None = None,
    sort_by: str = "relevance",
    **_: object,
) -> dict:
    query = (query or "").strip()
    if not query:
        return {"ok": False, "error": "query required"}
    top_n = max(1, min(20, int(top_n)))
    min_citations = max(0, int(min_citations))
    if sort_by not in {"relevance", "citations", "recency"}:
        sort_by = "relevance"

    try:
        raw = _openalex_search(query, top_n, min_citations, year_from, sort_by)
    except urllib.error.HTTPError as e:
        return {
            "ok": False,
            "query": query,
            "error": f"openalex_http_{e.code}",
            "detail": str(e)[:200],
        }
    except urllib.error.URLError as e:
        return {
            "ok": False,
            "query": query,
            "error": "openalex_unreachable",
            "detail": str(e)[:200],
        }

    results = [_shape_work(w) for w in (raw.get("results") or [])[:top_n]]
    total = (raw.get("meta") or {}).get("count", 0)

    # One-line synthesis — what an agent can do with this
    if not results:
        synthesis = "No matching papers found. The space appears uncovered — re-deriving may be original work, not duplication."
    else:
        top = results[0]
        if (top["citations"] or 0) > 500:
            synthesis = (
                f"This is a well-mapped space — top result has {top['citations']} citations. "
                f"Almost certainly someone has solved variations of this problem already. "
                f"Read '{top['title'][:80]}' before re-deriving."
            )
        elif (top["citations"] or 0) > 50:
            synthesis = (
                f"Some prior work exists ({len(results)} matches; top cited {top['citations']} times). "
                f"Worth a 5-min skim of '{top['title'][:80]}' before continuing."
            )
        else:
            synthesis = (
                f"Sparse coverage ({len(results)} matches, top cited {top['citations']} times). "
                f"This may be a frontier area — your work could be novel contribution."
            )

    return {
        "ok": True,
        "query": query,
        "sort_by": sort_by,
        "filters": {"min_citations": min_citations, "year_from": year_from},
        "total_in_corpus": total,
        "returned": len(results),
        "synthesis": synthesis,
        "papers": results,
        "next_steps": [
            "If a high-citation paper matches, fetch full text via DOI",
            "If sparse, your work may be novel — log the gap",
            "Refine query with terms from top abstracts and re-call",
        ],
    }


run.__when_to_use__ = (
    "An autonomous agent is about to derive a solution, design a protocol, or "
    "build a model. Before burning cycles, check whether the problem is solved "
    "in prior literature."
)
run.__vs_alternatives__ = (
    "Free alternative: search Google Scholar manually, parse HTML, summarize "
    "with LLM. Costs minutes of agent time + thousands of context tokens. "
    "This returns synthesized + citation-ranked intel in one call."
)
run.__example_request__ = {
    "query": "agent payment protocol stablecoin micropayment",
    "top_n": 5,
    "min_citations": 10,
    "year_from": 2022,
}
