"""Partnership check — does company X have an MCP / x402 footprint? Where does Onyx fit?

Given a company name or domain, probes:
  - their public website for MCP / x402 / agentic-commerce signals
  - CDP discovery for any services they ship under that domain
  - awesome-x402 + awesome-mcp-servers for listings
  - GitHub for repos with their org name + MCP/x402 keywords
  - Onyx catalog for tools that *complement* their stack

Returns: signal_strength (1-5), found_endpoints, found_repos, gap analysis
(what Onyx ships that complements them), suggested integration angle.

This is a meeting-generator tool. Run it on every funded peer in the
agentic web, ship the gap analysis as an outbound email subject line.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

NAME = "onyx_partnership_check"
PRICE_USDC = "0.02"
TIER = "metered"
DESCRIPTION = (
    "Where does Onyx plug into Company X's stack? Probes their domain + CDP "
    "discovery + awesome-x402/awesome-mcp + GitHub for MCP/x402 footprint. "
    "Returns gap analysis: which of Onyx's 64+ tools complement what they "
    "already ship. Plus a suggested integration angle and signal strength. "
    "Built for outbound partnership / merger / B2B sales conversations."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "company": {
            "type": "string",
            "description": "Company name (e.g. 'Catena Labs') or root domain (e.g. 'catena.xyz').",
        },
        "github_org": {
            "type": "string",
            "description": "Optional GitHub org slug. If known, narrows the repo probe.",
        },
    },
    "required": ["company"],
}

_UA = "onyx-partnership-check/1.0"
_TIMEOUT = 10.0


# Onyx capability map — what each tool category solves for partners
_CAPABILITY_MAP = {
    "trust_and_audit": {
        "tools": ["onyx_aml_screen", "onyx_agent_id", "onyx_agent_budget_tracker",
                  "onyx_agent_audit_trail", "onyx_base_token_risk_scan"],
        "fit_for": "trust / audit / guardrails companies (Catena, Nava, Ralio, Natural)",
    },
    "discoverability": {
        "tools": ["onyx_x402_indexer_health", "onyx_bazaar_compare",
                  "onyx_bazaar_blue_ocean", "onyx_mcp_catalog_diff"],
        "fit_for": "marketplace / brand-visibility companies (Brandlight, Lemrock, agentic.market)",
    },
    "on_chain_primitives": {
        "tools": ["onyx_base_tx_explainer", "onyx_base_tx_simulator",
                  "onyx_base_token_risk_scan", "onyx_base_contract_verify",
                  "onyx_base_swap_quote", "onyx_base_bridge_quote",
                  "onyx_base_dex_pair_lookup", "onyx_base_event_logs"],
        "fit_for": "DeFi / wallet / payment infra (Skyfire, Nekuda, Stripe Link, Catena)",
    },
    "x402_ops": {
        "tools": ["onyx_x402_receipt_verify", "onyx_x402_chain_picker",
                  "onyx_x402_error_explain", "onyx_facilitator_health",
                  "onyx_mcp_meta_call", "onyx_x402_demo_wallet"],
        "fit_for": "any x402 builder needing ops + observability",
    },
    "agent_security": {
        "tools": ["onyx_mcp_oauth_audit", "onyx_base_token_risk_scan",
                  "onyx_base_contract_verify", "onyx_aml_screen"],
        "fit_for": "agent security / observability (General Analysis, octonomy)",
    },
    "research": {
        "tools": ["onyx_research_intel", "onyx_paper_synthesis"],
        "fit_for": "research / IP / due-diligence layers, regulator-adjacent",
    },
}


def _http_get(url: str, accept: str = "text/html") -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": accept})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except (urllib.error.URLError, Exception):
        return 0, ""


def _scan_for_signals(text: str) -> dict:
    text_lc = (text or "").lower()
    return {
        "mentions_mcp": any(k in text_lc for k in ("model context protocol", "mcp server", "/mcp/", "mcp-")),
        "mentions_x402": "x402" in text_lc,
        "mentions_agentic": "agentic" in text_lc,
        "mentions_usdc": "usdc" in text_lc or "stablecoin" in text_lc,
        "mentions_base": " base " in text_lc or "base mainnet" in text_lc or "base-mainnet" in text_lc,
        "mentions_eip3009": "eip-3009" in text_lc or "transferwithauthorization" in text_lc,
        "mentions_oauth_dcr": "rfc 7591" in text_lc or "dynamic client registration" in text_lc,
        "mentions_aml": "aml" in text_lc or "sanctions screen" in text_lc,
    }


def _probe_cdp_for_domain(domain_lc: str) -> dict:
    status, body = _http_get(
        "https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources?limit=1000",
        accept="application/json",
    )
    if status != 200:
        return {"ok": False, "found": 0, "endpoints": []}
    try:
        items = json.loads(body).get("items", [])
    except Exception:
        return {"ok": False, "found": 0, "endpoints": []}
    hits = [r.get("resource", "") for r in items if domain_lc in (r.get("resource") or "").lower()]
    return {"ok": True, "found": len(hits), "endpoints": hits[:5]}


def _probe_github(company: str, org: str | None) -> dict:
    q_terms = []
    if org:
        q_terms.append(f"org:{org}")
    else:
        q_terms.append(company.lower().replace(" ", "+"))
    q_terms.append("(mcp+OR+x402)")
    q = "+".join(q_terms)
    url = f"https://api.github.com/search/repositories?q={q}&sort=updated&per_page=8"
    status, body = _http_get(url, accept="application/json")
    if status != 200:
        return {"ok": False, "repos": [], "total": 0}
    try:
        d = json.loads(body)
    except Exception:
        return {"ok": False, "repos": [], "total": 0}
    repos = [
        {
            "name": r.get("full_name"),
            "stars": r.get("stargazers_count"),
            "updated": r.get("updated_at", "")[:10],
            "description": (r.get("description") or "")[:120],
        }
        for r in d.get("items", [])[:5]
    ]
    return {"ok": True, "repos": repos, "total": d.get("total_count", 0)}


def _probe_awesome(domain_lc: str) -> dict:
    out = {}
    for slug, name in (
        ("xpaysh/awesome-x402", "awesome_x402"),
        ("punkpeye/awesome-mcp-servers", "awesome_mcp"),
    ):
        for branch in ("main", "master"):
            status, body = _http_get(
                f"https://raw.githubusercontent.com/{slug}/{branch}/README.md",
                accept="text/plain",
            )
            if status == 200:
                out[name] = domain_lc in body.lower()
                break
        else:
            out[name] = False
    return out


def _recommend_capabilities(signals: dict, cdp: dict, gh: dict) -> list[dict]:
    """Given what we see about them, recommend which Onyx caps to lead with."""
    out = []
    if signals.get("mentions_aml") or signals.get("mentions_usdc"):
        out.append(_CAPABILITY_MAP["trust_and_audit"])
    if cdp.get("found", 0) > 0:
        out.append(_CAPABILITY_MAP["x402_ops"])
    if signals.get("mentions_mcp"):
        out.append(_CAPABILITY_MAP["discoverability"])
    if signals.get("mentions_base") or signals.get("mentions_eip3009"):
        out.append(_CAPABILITY_MAP["on_chain_primitives"])
    if signals.get("mentions_oauth_dcr"):
        out.append(_CAPABILITY_MAP["agent_security"])
    # Always at least include x402_ops if no obvious signals
    if not out:
        out.append(_CAPABILITY_MAP["x402_ops"])
        out.append(_CAPABILITY_MAP["discoverability"])
    # Dedup by tools list identity
    seen = set()
    uniq = []
    for c in out:
        key = tuple(c["tools"])
        if key not in seen:
            seen.add(key)
            uniq.append(c)
    return uniq


def _resolve_domain(company: str) -> str:
    s = company.strip().lower()
    if "://" in s:
        s = s.split("://", 1)[1]
    s = s.split("/")[0]
    # If just a name, guess the dot-com
    if "." not in s:
        s = s.replace(" ", "") + ".com"
    return s


def run(company: str, github_org: str | None = None, **_: object) -> dict:
    if not company:
        return {"ok": False, "error": "company required"}
    domain = _resolve_domain(company)

    # Probe their landing page
    site_text = ""
    for scheme in ("https://", "https://www."):
        status, body = _http_get(f"{scheme}{domain}", accept="text/html")
        if status == 200 and body:
            site_text = body
            break

    signals = _scan_for_signals(site_text)
    cdp = _probe_cdp_for_domain(domain)
    awesome = _probe_awesome(domain)
    gh = _probe_github(company.split(".")[0], github_org)

    # Signal strength: 0-5 weighted
    strength = 0
    strength += min(2, sum(1 for v in signals.values() if v) // 2)
    strength += 2 if cdp.get("found", 0) > 0 else 0
    strength += 1 if awesome.get("awesome_x402") or awesome.get("awesome_mcp") else 0
    strength += min(1, (gh.get("total") or 0) // 5)
    strength = min(5, strength)

    recommended = _recommend_capabilities(signals, cdp, gh)

    integration_pitch = (
        f"Onyx Actions ships 64 tools across {len(_CAPABILITY_MAP)} capability areas. "
        f"Based on {company}'s footprint, the natural integration is: "
        + ", ".join(c["fit_for"].split(" companies")[0] for c in recommended[:2])
        + ". "
        + ("They already ship x402 — pitch composition (their tools call ours via x402)." if cdp.get("found") else
           "No x402 presence yet — pitch us as their x402 entry kit.")
    )

    return {
        "ok": True,
        "company": company,
        "domain": domain,
        "signal_strength_0_5": strength,
        "site_signals": signals,
        "cdp_discovery": cdp,
        "awesome_lists": awesome,
        "github_search": gh,
        "recommended_capabilities": recommended,
        "integration_pitch": integration_pitch,
        "outreach_angles": [
            f"Subject: {company} + Onyx — {recommended[0]['fit_for'].split(',')[0]} integration",
            f"Subject: We ship the {len(recommended[0]['tools'])} primitives your stack needs (audit-ready, x402-native)",
        ] if recommended else [],
    }


run.__when_to_use__ = (
    "Before any outbound partnership / merger / B2B sales conversation. "
    "Run this on the target company and lead with the gap-analysis subject line."
)
run.__vs_alternatives__ = (
    "LinkedIn stalking + manual scraping. This is one paid call, structured "
    "JSON, with capability-fit ranking + ready outreach subject lines."
)
run.__example_request__ = {
    "company": "Catena Labs",
    "github_org": "catena-labs",
}
