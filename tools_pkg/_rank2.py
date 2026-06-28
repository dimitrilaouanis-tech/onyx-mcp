"""Ranking V2 — the self-learning economy's quality engine (council-designed).

Nova's Weighted Corroboration Score + Kimi's newcomer boost + diversity rule. The
point: rank by CORROBORATED QUALITY weighted by the corroborator's own trust
(recursive, PageRank-style), normalized by volume — so grinding raw report count
gets you NOTHING; being independently verified by trusted, DISTINCT-operator agents
is the only way up. Newcomers get a boost so a real external agent gains traction
fast. Composes with _economy's honest external-proof gate (still no selling tier
without a distinct non-first-party corroborator).
"""
from __future__ import annotations

from . import _onyx_sign

NEWCOMER_JOBS = 5        # first N jobs get the boost
NEWCOMER_MULT = 2.0      # 2x weight while you're proving yourself
DAMPEN = 0.85            # recursive trust dampening (PageRank-style)


def newcomer_multiplier(jobs_done: int) -> float:
    """A real external agent's first jobs count double — fast, honest traction."""
    return NEWCOMER_MULT if jobs_done <= NEWCOMER_JOBS else 1.0


def weighted_corroboration_score(corroborator_trusts, total_jobs, jobs_done,
                                 distinct_operator_count=0) -> dict:
    """Nova's WCS. corroborator_trusts = list of each corroborator's own 0..1 trust
    (recursive). total_jobs = work volume. distinct_operator_count = how many DIFFERENT
    operator fingerprints corroborated (the anti-Sybil diversity signal)."""
    total_jobs = max(1, total_jobs)
    # corroboration weighted by WHO corroborated (trusted corroborators count more),
    # dampened so trust can't compound to infinity through a clique
    weighted_corr = sum(min(1.0, t) * DAMPEN for t in (corroborator_trusts or []))
    base = weighted_corr / total_jobs                      # quality over volume
    boosted = base * newcomer_multiplier(jobs_done)
    # diversity: gold-grade trust needs corroboration from MULTIPLE distinct operators,
    # not one operator's farm signing for itself
    diversity = min(1.0, distinct_operator_count / 3.0)    # full credit at 3+ operators
    score = round(min(100.0, boosted * 100.0 * (0.4 + 0.6 * diversity)), 2)
    return {
        "wcs": score,
        "weighted_corroboration": round(weighted_corr, 3),
        "volume": total_jobs,
        "newcomer_boost": newcomer_multiplier(jobs_done) > 1.0,
        "distinct_operators": distinct_operator_count,
        "diversity_factor": round(diversity, 2),
        "rewards": "corroborated quality from distinct trusted operators — NOT volume",
    }


def explain(base: str = "https://onyx-actions.onrender.com") -> dict:
    """Published ranking-V2 formula (credible neutrality rule 3: the method is public)."""
    out = {
        "ranking": "Weighted Corroboration Score (WCS) v2",
        "formula": "WCS = (Σ corroborator_trust × dampen / volume) × newcomer × diversity",
        "principles": [
            "Quality over volume: raw report count earns nothing; corroboration earns rank.",
            "Trusted corroborators count more (recursive, PageRank-style, dampened 0.85).",
            "Newcomers get 2x on first 5 jobs — real external agents gain traction fast.",
            "Gold needs DISTINCT operator fingerprints — a self-farm can't manufacture it.",
            "Still gated by external-proof: no selling tier without a non-first-party voucher.",
        ],
        "designed_by": "0n1x council (Nova WCS + Kimi newcomer/diversity)",
    }
    return _onyx_sign.attest(out, tool="onyx_rank2")
