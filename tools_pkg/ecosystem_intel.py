"""onyx_ecosystem_intel — a signed snapshot of the agentic ecosystem 0n1x observes.

`tools_pkg/_intel.py` already owns GET /intel (productized research + counterparty
verification). This is a different surface: a live "who's live, who's competing,
what does OUR house look like right now" snapshot, so an agent (or a human doing
diligence on us) can ask one question and get one signed answer instead of
scraping five pages.

Three parts, each disclosed:
  1. our own live numbers  — citizen registry + signed fact-layer ledger (same
     source as /stats, just packaged for machine consumption in one call).
  2. the public agentic-web census — a live count + top categories pulled from
     Coinbase's public CDP x402 discovery API (no auth required).
  3. a curated, honestly-labeled competitor map — some entries are described
     from firsthand knowledge (what they verify, at what price), others are
     name-only sightings from ecosystem sweeps we have not independently
     verified. Sign facts, not judgments: unverified entries are marked as such
     rather than padded with invented detail.

Free tier — this is a discovery/positioning surface, not the oracle product;
the moat is the signed price/merchant/preflight oracles elsewhere in this
catalog, not gatekeeping "who else exists."
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request

from . import _onyx_sign

try:
    from . import _claim_registry
except Exception:  # pragma: no cover - defensive on shared repo
    _claim_registry = None
try:
    from . import _ledger
except Exception:  # pragma: no cover
    _ledger = None

NAME = "onyx_ecosystem_intel"
PRICE_USDC = "0"
TIER = "free"
DESCRIPTION = (
    "Signed snapshot of the agentic ecosystem 0n1x observes: our own live citizen "
    "+ signed fact-layer counts, a live census pulled from Coinbase's public CDP "
    "x402 discovery API (service count + top categories), and a curated, honestly-"
    "labeled competitor map (x402 preflight/trust-score/oracle peers — what each "
    "verifies, where known, marked unverified where not). One call to understand "
    "who's live and where 0n1x sits. Free tier, Ed25519-signed, observed_at dated."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "census_limit": {
            "type": "integer",
            "default": 500,
            "minimum": 50,
            "maximum": 1000,
            "description": "How many CDP discovery entries to sample for the census (top categories).",
        },
    },
}

_DISCOVERY = "https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources"
_UA = "onyx-ecosystem-intel/1.0 (+https://onyx-actions.onrender.com)"
_OBSERVED_AT = "2026-07-03"

_STOPWORDS = {
    "the", "and", "for", "with", "this", "that", "your", "from", "into", "onto",
    "over", "under", "agent", "agents", "tool", "tools", "service", "services",
    "api", "data", "using", "based", "provide", "provides", "returns", "given",
    "live", "real", "check", "onto", "each", "any", "any.", "x402", "mcp",
}
_WORD_RE = re.compile(r"[a-z][a-z0-9\-]{3,}")


def _top_categories(items: list[dict], top_n: int = 10) -> list[dict]:
    counts: dict[str, int] = {}
    for it in items:
        desc = (it.get("description") or "").lower()
        for w in set(_WORD_RE.findall(desc)):
            if w in _STOPWORDS:
                continue
            counts[w] = counts.get(w, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])[:top_n]
    return [{"term": t, "count": c} for t, c in ranked]


def _fetch_census(limit: int) -> dict:
    url = f"{_DISCOVERY}?limit={max(50, min(int(limit), 1000))}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            items = (json.loads(r.read()) or {}).get("items", [])
        return {
            "ok": True,
            "source": "Coinbase CDP x402 discovery API (public, no auth)",
            "queried_url": _DISCOVERY,
            "sampled": len(items),
            "top_categories": _top_categories(items),
            "note": "sampled=count returned by this call (bounded by census_limit), not the full "
                    "corpus size — CDP discovery does not expose a total-count field.",
        }
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, Exception) as e:  # noqa: BLE001
        return {"ok": False, "source": "Coinbase CDP x402 discovery API (public, no auth)",
                "queried_url": _DISCOVERY, "error": f"{type(e).__name__}: {str(e)[:120]}"}


def _citizens() -> dict:
    if not _claim_registry:
        return {"available": False}
    try:
        pop = _claim_registry.population()
        return {
            "available": True,
            "total_citizens": pop.get("total_citizens", 0),
            "claimed_proven_key": pop.get("claimed_count", 0),
            "reserved_unclaimed": pop.get("reserved_count", 0),
        }
    except Exception as e:
        return {"available": False, "error": str(e)[:160]}


def _fact_layer() -> dict:
    if not _ledger:
        return {"available": False}
    try:
        s = _ledger.stats()
        return {
            "available": True,
            "signed_verdict_outcome_records": s.get("total_outcomes", 0),
            "resolved_outcomes": s.get("resolved", 0),
            "block_precision": s.get("block_precision"),
        }
    except Exception as e:
        return {"available": False, "error": str(e)[:160]}


# Curated competitor map. "verified": True means the lane/price/mechanism below
# was directly observed/confirmed by us; False means the name was sighted in an
# ecosystem sweep (e.g. awesome-mcp-servers) without independent confirmation of
# the claimed capability — reported honestly rather than padded.
_COMPETITORS = [
    {
        "name": "x402station",
        "lane": "x402 preflight — runs before every x402 payment",
        "verifies": "decoy endpoints, zombie/dead services, price traps",
        "price_usdc": "0.001/call",
        "signed_output": None,
        "verified": True,
        "onyx_delta": "same class of check (onyx_preflight), but every flag is a "
                       "disclosed rule and the verdict is Ed25519-signed for third-"
                       "party re-verification, not an internal-only score.",
    },
    {
        "name": "rplryan/x402-discovery",
        "lane": "x402 endpoint discovery + trust scoring",
        "verifies": "0-100 trust score per endpoint",
        "price_usdc": None,
        "signed_output": None,
        "verified": True,
        "onyx_delta": "scores are opaque (single vendor's model); Onyx publishes the "
                       "rule set behind each flag instead of a single number.",
    },
    {
        "name": "Octodamus",
        "lane": "signed oracle",
        "verifies": "Ed25519-signed outputs (mechanism confirmed, scope not)",
        "price_usdc": None,
        "signed_output": "Ed25519",
        "verified": True,
        "onyx_delta": "closest peer on signing mechanism; Onyx's differentiator is "
                       "breadth (preflight + merchant + price + agent-safety in one "
                       "signed catalog) plus the published neutrality posture.",
    },
    {
        "name": "Swarmwage",
        "lane": "unconfirmed — name observed in ecosystem sweep only",
        "verifies": None,
        "price_usdc": None,
        "signed_output": None,
        "verified": False,
        "onyx_delta": None,
    },
    {
        "name": "cinderwright",
        "lane": "unconfirmed — name observed in ecosystem sweep only",
        "verifies": None,
        "price_usdc": None,
        "signed_output": None,
        "verified": False,
        "onyx_delta": None,
    },
]

_TTL = 600
_CACHE: dict = {"at": 0, "snap": None, "limit": None}


def _build(now: int, census_limit: int) -> dict:
    payload = {
        "snapshot": "0n1x ecosystem intel",
        "as_of": now,
        "as_of_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "onyx": {
            "citizens": _citizens(),
            "fact_layer": _fact_layer(),
            "lane": "signed ground-truth oracle (price/merchant/preflight/agent-safety) "
                    "over x402 + MCP — sign observations, never verdicts about a named party",
        },
        "agentic_web_census": _fetch_census(census_limit),
        "competitor_map": _COMPETITORS,
        "competitor_map_note": (
            "observed_at " + _OBSERVED_AT + ". `verified: true` entries had their lane/price/"
            "mechanism directly confirmed by us; `verified: false` entries are name-only "
            "sightings from an ecosystem sweep, reported honestly rather than padded with "
            "invented detail — sign facts, not judgments, applies to competitors too."
        ),
        "positioning": {
            "differentiator": "Ed25519-signed, disclosed-rule verdicts + neutrality — we do "
                               "not take a cut of the GMV we'd have to grade.",
            "moat": "https://onyx-actions.onrender.com/rank and /stats show the same "
                    "sign-facts-not-judgments posture applied to our own ecosystem.",
        },
        "method": "Citizen/fact-layer counts read from Onyx's own signed logs; census "
                  "queried live from the public CDP x402 discovery API (no auth); "
                  "competitor entries curated and dated, verified/unverified disclosed.",
    }
    return _onyx_sign.attest(payload, tool="onyx_ecosystem_intel")


def run(census_limit: int = 500, **_: object) -> dict:
    limit = max(50, min(int(census_limit or 500), 1000))
    ts = int(time.time())
    if not _CACHE["snap"] or ts - _CACHE["at"] > _TTL or _CACHE["limit"] != limit:
        _CACHE["snap"] = _build(ts, limit)
        _CACHE["at"] = ts
        _CACHE["limit"] = limit
    return _CACHE["snap"]


run.__when_to_use__ = (
    "An agent or human wants one signed call that explains what 0n1x is, how big it "
    "is right now (citizens, signed fact records), how big the wider x402 agentic-web "
    "market looks (live CDP census), and who else runs signed/trust-scoring checks in "
    "this lane."
)
run.__vs_alternatives__ = (
    "No competitor publishes a self-graded positioning snapshot with honesty labels on "
    "unverified claims. This is the same radical-transparency mechanic as our own "
    "/stats page, extended to the competitive landscape."
)
run.__example_request__ = {"census_limit": 500}
run.__example_response__ = {
    "snapshot": "0n1x ecosystem intel",
    "onyx": {"citizens": {"total_citizens": 0}, "fact_layer": {"signed_verdict_outcome_records": 0}},
    "agentic_web_census": {"ok": True, "sampled": 500, "top_categories": [{"term": "price", "count": 40}]},
    "competitor_map": [{"name": "x402station", "verified": True}],
}


def register(app) -> None:
    """Attach GET /ecosystem-intel to the FastAPI app.

    Usage in server_http.py:
        from tools_pkg import ecosystem_intel; ecosystem_intel.register(app)
    """
    from fastapi.responses import JSONResponse

    @app.get("/ecosystem-intel", include_in_schema=False)
    def _ecosystem_intel_get(census_limit: int = 500):
        return JSONResponse(run(census_limit=census_limit))
