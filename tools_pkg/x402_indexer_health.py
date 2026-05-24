"""Indexer health — is YOUR x402 endpoint actually discoverable?

Every paid-MCP builder hits the same blindness: you ship 30 tools, your manifest
is clean, your facilitator works — and you get $0 inbound because no indexer
is listing you. This tool probes the 6 indexers agents actually use and tells
you which ones see your domain.

Probed indexers:
  - CDP discovery (api.cdp.coinbase.com/.../x402/discovery/resources)
  - Onyx bazaar mirror (onyx-actions.onrender.com/bazaar.json)
  - awesome-x402 README (github.com/xpaysh/awesome-x402)
  - awesome-mcp-servers README (github.com/punkpeye/awesome-mcp-servers)
  - x402scan.com presence (heuristic — page contains domain)
  - Smithery registry (smithery.ai/server search)

Returns per-indexer hit/miss + last_seen + a single recommended action.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

NAME = "onyx_x402_indexer_health"
PRICE_USDC = "0"
TIER = "free"
DESCRIPTION = (
    "Is your x402 endpoint actually discoverable? Probes 6 indexers agents "
    "use (CDP discovery, Bazaar mirror, awesome-x402 README, awesome-mcp-servers "
    "README, x402scan, Smithery) and returns per-indexer presence + a single "
    "recommended action. Free tier — every paid-MCP-builder hits the same "
    "invisible-launch problem and this is the missing observability tool."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "url": {
            "type": "string",
            "description": "Domain or full URL to check (e.g. 'onyx-actions.onrender.com' or 'https://api.oatp.cc').",
        },
    },
    "required": ["url"],
}

_TIMEOUT = 8.0
_UA = "onyx-indexer-health/1.0"


def _domain_of(url: str) -> str:
    u = (url or "").strip().lower()
    if u.startswith("http://") or u.startswith("https://"):
        u = u.split("://", 1)[1]
    return u.split("/")[0].strip()


def _http_get(url: str, timeout: float = _TIMEOUT, accept: str = "application/json") -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": accept})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except urllib.error.URLError:
        return 0, ""
    except Exception:
        return 0, ""


def _probe_cdp(domain: str) -> dict:
    status, body = _http_get(
        "https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources?limit=1000"
    )
    if status != 200:
        return {"name": "cdp_discovery", "ok": False, "found": 0, "error": f"http_{status}"}
    try:
        items = json.loads(body).get("items", [])
    except Exception:
        return {"name": "cdp_discovery", "ok": False, "found": 0, "error": "parse_fail"}
    hits = [r.get("resource", "") for r in items if domain in (r.get("resource") or "").lower()]
    return {
        "name": "cdp_discovery",
        "ok": True,
        "found": len(hits),
        "sample": hits[:3],
        "total_indexed": len(items),
    }


def _probe_bazaar_mirror(domain: str) -> dict:
    status, body = _http_get(
        "https://onyx-actions.onrender.com/bazaar.json?view=volume&limit=1000"
    )
    if status != 200:
        return {"name": "bazaar_mirror", "ok": False, "found": 0, "error": f"http_{status}"}
    try:
        rows = json.loads(body).get("rows", [])
    except Exception:
        return {"name": "bazaar_mirror", "ok": False, "found": 0, "error": "parse_fail"}
    hits = [r for r in rows if domain in (r.get("domain") or "").lower()]
    return {
        "name": "bazaar_mirror",
        "ok": True,
        "found": len(hits),
        "sample": [r.get("resource") for r in hits[:3]],
    }


def _probe_awesome_repo(domain: str, repo: str, name: str) -> dict:
    # Raw README from default branch
    for branch in ("main", "master"):
        status, body = _http_get(
            f"https://raw.githubusercontent.com/{repo}/{branch}/README.md",
            accept="text/plain",
        )
        if status == 200:
            present = domain.lower() in body.lower()
            return {
                "name": name,
                "ok": True,
                "found": 1 if present else 0,
                "branch": branch,
            }
    return {"name": name, "ok": False, "found": 0, "error": "readme_fetch_failed"}


def _probe_x402scan(domain: str) -> dict:
    # x402scan exposes per-endpoint pages; their index page lists active resources
    status, body = _http_get("https://x402scan.com/", accept="text/html")
    if status != 200:
        return {"name": "x402scan", "ok": False, "found": 0, "error": f"http_{status}"}
    return {
        "name": "x402scan",
        "ok": True,
        "found": 1 if domain.lower() in body.lower() else 0,
        "note": "heuristic — index page text search",
    }


def _probe_smithery(domain: str) -> dict:
    # Smithery search query
    q = urllib.parse.quote(domain.split(".")[0])
    status, body = _http_get(
        f"https://smithery.ai/api/search?q={q}",
        accept="application/json",
    )
    if status != 200:
        return {"name": "smithery", "ok": False, "found": 0, "error": f"http_{status}"}
    try:
        d = json.loads(body)
    except Exception:
        return {"name": "smithery", "ok": False, "found": 0, "error": "parse_fail"}
    servers = d.get("servers") or d.get("results") or d.get("items") or []
    return {
        "name": "smithery",
        "ok": True,
        "found": len(servers),
        "sample": [
            (s.get("qualifiedName") or s.get("name") or "")
            for s in servers[:3]
        ],
    }


def _recommend(hits: list[dict]) -> str:
    by_name = {h["name"]: h for h in hits}
    not_in_cdp = by_name.get("cdp_discovery", {}).get("found", 0) == 0
    not_in_bazaar = by_name.get("bazaar_mirror", {}).get("found", 0) == 0
    not_in_awesome_x402 = by_name.get("awesome_x402", {}).get("found", 0) == 0
    not_in_awesome_mcp = by_name.get("awesome_mcp", {}).get("found", 0) == 0
    not_in_x402scan = by_name.get("x402scan", {}).get("found", 0) == 0
    not_in_smithery = by_name.get("smithery", {}).get("found", 0) == 0

    if not_in_cdp:
        return (
            "Highest leverage: get into CDP discovery. Verify your /.well-known/x402.json "
            "advertises eip155:8453 (Base mainnet) in at least one accepts[] block — "
            "the crawler filters out Sepolia-only manifests."
        )
    if not_in_bazaar:
        return "Onyx bazaar mirror should auto-sync from CDP. Ping the mirror to confirm."
    if not_in_awesome_x402:
        return "PR your project into github.com/xpaysh/awesome-x402 — durable backlink."
    if not_in_awesome_mcp:
        return "PR your MCP server into github.com/punkpeye/awesome-mcp-servers."
    if not_in_x402scan:
        return "x402scan should pick you up automatically once CDP indexes; otherwise contact maintainer."
    if not_in_smithery:
        return "Smithery only lists MCP-flavored servers — submit at smithery.ai/servers/new."
    return "Fully indexed across all 6 surfaces. Funnel is healthy — focus on tool-quality + agent fit."


def run(url: str, **_: object) -> dict:
    domain = _domain_of(url)
    if not domain:
        return {"ok": False, "error": "url required"}

    probes = [
        _probe_cdp(domain),
        _probe_bazaar_mirror(domain),
        _probe_awesome_repo(domain, "xpaysh/awesome-x402", "awesome_x402"),
        _probe_awesome_repo(domain, "punkpeye/awesome-mcp-servers", "awesome_mcp"),
        _probe_x402scan(domain),
        _probe_smithery(domain),
    ]
    total_hits = sum(1 for p in probes if (p.get("found") or 0) > 0)
    return {
        "ok": True,
        "domain": domain,
        "indexers_total": len(probes),
        "indexers_with_hits": total_hits,
        "coverage_pct": round(100 * total_hits / len(probes), 1),
        "indexers": probes,
        "recommended_action": _recommend(probes),
    }


run.__when_to_use__ = (
    "You just shipped a paid x402 endpoint and your inbound is $0. Before "
    "writing another tool, verify you're actually findable."
)
run.__vs_alternatives__ = (
    "Manually visiting 6 indexer sites and ctrl-F-ing your domain. This is "
    "one call, structured output, with a single ranked action."
)
run.__example_request__ = {"url": "api.oatp.cc"}
