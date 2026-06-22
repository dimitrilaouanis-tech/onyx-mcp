"""Onyx Agent Index — pull every public agent registry into ONE queryable directory.

The discovery layer is fragmented (a2aregistry, Agoragentic, the x402 census, MCP
registries) and nobody has won the "Google for agents" seat. This aggregates the
machine-readable rosters into a single normalized, cached, queryable index so we
(and any agent) can discover the whole space WITHOUT walking into each registry.

Sources pulled programmatically:
  - a2aregistry.org/api/agents      (A2A agents: name, endpoint, skills)
  - agoragentic.com/api/capabilities (marketplace services)
  - the x402 discovery census is covered by /leaderboard (ranked by demand)

The snapshot is Ed25519-signed (tamper-evident, dogfood). Stdlib-only.
"""
from __future__ import annotations

import http.client
import json
import time
import urllib.parse
import urllib.request

from . import _onyx_sign

_TTL = 1800
_CACHE: dict = {"at": 0, "snap": None}
_UA = {"User-Agent": "Mozilla/5.0 (compatible; OnyxAgentIndex/1.0)", "Accept": "application/json"}


def _get(url: str, timeout: float = 25) -> dict | list:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        try:
            raw = r.read()
        except http.client.IncompleteRead as e:
            raw = e.partial  # large/chunked payload cut short — use what arrived
    return json.loads(raw or b"{}")


def _a2aregistry() -> list[dict]:
    out = []
    try:
        for off in range(0, 400, 100):  # paginate (API caps ~100/page)
            d = _get(f"https://a2aregistry.org/api/agents?limit=100&offset={off}")
            page = d.get("agents", []) if isinstance(d, dict) else []
            for a in page:
                out.append({
                    "name": a.get("name", "?"),
                    "endpoint": a.get("url") or a.get("wellKnownURI", ""),
                    "description": (a.get("description") or "")[:200],
                    "skills": [s.get("name") or s.get("id") for s in (a.get("skills") or [])][:8],
                    "source": "a2aregistry",
                })
            if len(page) < 100:
                break
    except Exception as e:
        out.append({"_error": f"a2aregistry: {type(e).__name__}: {str(e)[:60]}"})
    return out


def _agoragentic() -> list[dict]:
    out = []
    try:
        d = _get("https://agoragentic.com/api/capabilities")
        for c in (d.get("capabilities", []) if isinstance(d, dict) else []):
            out.append({
                "name": c.get("name", "?"),
                "endpoint": c.get("endpoint_url") or ("agoragentic:" + (c.get("slug") or "")),
                "description": (c.get("description") or "")[:200],
                "skills": [],
                "source": "agoragentic",
            })
    except Exception as e:
        out.append({"_error": f"agoragentic: {type(e).__name__}: {str(e)[:60]}"})
    return out


def _mcp_registry() -> list[dict]:
    """The official MCP Registry — the spine every aggregator ingests. Public,
    no auth, cursor-paginated. Adds the remote-callable MCP server universe."""
    out, cursor, pages = [], "", 0
    try:
        while pages < 12:  # ~1200 servers; bump cap for deeper coverage
            url = "https://registry.modelcontextprotocol.io/v0/servers?limit=100"
            if cursor:
                url += "&cursor=" + urllib.parse.quote(cursor)
            d = _get(url)
            servers = d.get("servers", []) if isinstance(d, dict) else []
            for s in servers:
                srv = s.get("server", s) if isinstance(s, dict) else {}
                remotes = srv.get("remotes") or []
                endpoint = (remotes[0].get("url") if remotes else "") or ("mcp:" + (srv.get("name") or ""))
                out.append({
                    "name": srv.get("name", "?"),
                    "endpoint": endpoint,
                    "description": (srv.get("description") or "")[:200],
                    "skills": [],
                    "source": "mcp-registry",
                })
            cursor = (d.get("metadata", {}) or {}).get("nextCursor") if isinstance(d, dict) else ""
            pages += 1
            if not cursor:
                break
    except Exception as e:
        out.append({"_error": f"mcp-registry: {type(e).__name__}: {str(e)[:60]}"})
    return out


def _build(now: int) -> dict:
    a2a = _a2aregistry()
    agora = _agoragentic()
    mcp = _mcp_registry()
    allrows = a2a + agora + mcp
    errors = [x["_error"] for x in allrows if x.get("_error")]
    agents = [x for x in allrows if not x.get("_error")]
    # dedupe by (lowercased name + endpoint host)
    seen, deduped = set(), []
    for a in agents:
        key = (a["name"].lower().strip(), (a.get("endpoint") or "").split("/")[2] if "://" in (a.get("endpoint") or "") else a.get("endpoint", ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(a)
    by_source: dict[str, int] = {}
    for a in deduped:
        by_source[a["source"]] = by_source.get(a["source"], 0) + 1
    snap = {
        "index": "onyx-agent-directory",
        "as_of": now,
        "as_of_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "total_agents": len(deduped),
        "by_source": by_source,
        "sources": ["a2aregistry.org", "agoragentic.com", "registry.modelcontextprotocol.io",
                    "(x402 census ranked separately at /leaderboard)"],
        "agents": deduped,
        "errors": errors,
        "note": "Unified, machine-queryable directory aggregated from public agent "
                "registries — discover the whole space without visiting each one. "
                "Query: /directory?q=<keyword>&source=<a2aregistry|agoragentic>.",
    }
    return _onyx_sign.attest(snap, tool="onyx_agent_index")


def snapshot(now: int | None = None) -> dict:
    ts = int(now if now is not None else time.time())
    if not _CACHE["snap"] or ts - _CACHE["at"] > _TTL:
        _CACHE["snap"] = _build(ts)
        _CACHE["at"] = ts
    return _CACHE["snap"]


def query(q: str = "", source: str = "", limit: int = 50) -> dict:
    """Search the unified index by keyword + source — no registry-hopping."""
    snap = snapshot()
    ql = (q or "").lower().strip()
    rows = snap.get("agents", [])
    if source:
        rows = [a for a in rows if a.get("source") == source]
    if ql:
        rows = [a for a in rows
                if ql in a.get("name", "").lower()
                or ql in a.get("description", "").lower()
                or any(ql in str(s).lower() for s in a.get("skills", []))]
    return {
        "query": q, "source": source or "all",
        "matched": len(rows), "total_indexed": snap.get("total_agents", 0),
        "as_of": snap.get("as_of_iso"),
        "agents": rows[:max(1, min(limit, 200))],
    }
