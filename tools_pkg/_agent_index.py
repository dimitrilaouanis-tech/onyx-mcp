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


def _slugify(name: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in (name or "").lower()).strip("-") or "unnamed"


def _ep_host(ep: str) -> str:
    """Real http(s) host of an endpoint, normalized; '' for placeholder endpoints
    (agoragentic:/mcp:/smithery:/agentverse:)."""
    ep = (ep or "").strip().lower()
    for p in ("https://", "http://"):
        if ep.startswith(p):
            h = ep[len(p):].split("/")[0]
            return h[4:] if h.startswith("www.") else h
    return ""


def _ep_canon(ep: str) -> str:
    """Canonical key for exact-duplicate detection: host + path, trailing slash
    stripped. Placeholder endpoints return themselves lowercased."""
    ep = (ep or "").strip()
    h = _ep_host(ep)
    if not h:
        return ep.lower()
    rest = ep.split("://", 1)[1]
    path = rest[len(rest.split("/", 1)[0]):].rstrip("/")
    return h + path


def _agoragentic() -> list[dict]:
    out = []
    try:
        d = _get("https://agoragentic.com/api/capabilities")
        for c in (d.get("capabilities", []) if isinstance(d, dict) else []):
            out.append({
                "name": c.get("name", "?"),
                # placeholder must be UNIQUE per capability — an empty slug used to
                # collapse every endpoint-less service to the same "agoragentic:"
                # string (28 phantom "duplicates"). Fall back to a name-derived slug.
                "endpoint": c.get("endpoint_url") or (
                    "agoragentic:" + (c.get("slug") or _slugify(c.get("name", "")))),
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


def _agentverse() -> list[dict]:
    """Fetch.ai Agentverse — open search API (no auth). Adds active uAgents."""
    out = []
    seen = set()
    try:
        _br = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Content-Type": "application/json"}
        for term in ("agent", "finance", "data", "search", "trading", "ai"):
            body = json.dumps({
                "search_text": term, "filters": {"state": ["active"]},
                "sort": "relevancy", "direction": "desc", "offset": 0, "limit": 50,
            }).encode()
            req = urllib.request.Request("https://agentverse.ai/v1/search/agents",
                                         data=body, headers=_br)
            with urllib.request.urlopen(req, timeout=25) as r:
                try:
                    raw = r.read()
                except http.client.IncompleteRead as e:
                    raw = e.partial
            ags = (json.loads(raw or b"{}").get("agents", []))
            for a in ags:
                addr = a.get("address") or ""
                if addr in seen:
                    continue
                seen.add(addr)
                if int(a.get("total_interactions") or 0) <= 0:
                    continue  # skip dead/test agents
                out.append({
                    "name": a.get("name", "?"),
                    "endpoint": "agentverse:" + (a.get("address") or ""),
                    "description": (a.get("readme") or "")[:200].replace("\n", " "),
                    "skills": [],
                    "source": "agentverse",
                })
    except Exception as e:
        out.append({"_error": f"agentverse: {type(e).__name__}: {str(e)[:60]}"})
    return out


def _x402_census() -> list[dict]:
    """The x402 economy — live CDP discovery feed. Adds paying-agent endpoints
    (deduped by host). The transacting layer the others miss."""
    out, seen = [], set()
    try:
        for off in range(0, 12000, 1000):  # deeper sweep -> capture long-tail hosts (real small agents)
            d = _get(f"https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources?limit=1000&offset={off}")
            items = d.get("items", []) if isinstance(d, dict) else []
            for it in items:
                res = it.get("resource", "")
                host = res.split("/")[2] if "://" in res else res
                if not host or host in seen:
                    continue
                seen.add(host)
                out.append({
                    "name": host,
                    "endpoint": res,
                    "description": (it.get("description") or "")[:200],
                    "skills": [],
                    "source": "x402-census",
                })
            if len(items) < 1000:
                break
    except Exception as e:
        out.append({"_error": f"x402-census: {type(e).__name__}: {str(e)[:60]}"})
    return out


def _smithery() -> list[dict]:
    """Smithery — the largest MCP server registry (~6.5k servers). Open REST API."""
    out = []
    try:
        page = 1
        while page <= 30:  # ~3000 servers; bump cap for deeper coverage
            d = _get(f"https://registry.smithery.ai/servers?page={page}&pageSize=100")
            servers = d.get("servers", []) if isinstance(d, dict) else []
            if not servers:
                break
            for s in servers:
                qn = s.get("qualifiedName") or s.get("namespace") or ""
                out.append({
                    "name": s.get("displayName") or qn or "?",
                    "endpoint": "smithery:" + qn,
                    "description": (s.get("description") or "")[:200],
                    "skills": [],
                    "source": "smithery",
                })
            pg = (d.get("pagination") or {}) if isinstance(d, dict) else {}
            if page >= (pg.get("totalPages") or page):
                break
            page += 1
    except Exception as e:
        out.append({"_error": f"smithery: {type(e).__name__}: {str(e)[:60]}"})
    return out


def _build(now: int) -> dict:
    a2a = _a2aregistry()
    agora = _agoragentic()
    mcp = _mcp_registry()
    averse = _agentverse()
    x402 = _x402_census()
    smith = _smithery()
    allrows = a2a + agora + mcp + averse + x402 + smith
    errors = [x["_error"] for x in allrows if x.get("_error")]
    agents = [x for x in allrows if not x.get("_error")]
    # --- dedup (overlap control) ---
    # (1) drop (name, host) repeats AND exact canonical-URL repeats — the latter
    #     catches the SAME agent listed in two registries under different names.
    seen_nh, seen_canon, deduped = set(), set(), []
    for a in agents:
        ep = a.get("endpoint") or ""
        canon = _ep_canon(ep)
        nh = (a["name"].lower().strip(), _ep_host(ep) or canon)
        if nh in seen_nh or (canon and canon in seen_canon):
            continue
        seen_nh.add(nh)
        if canon:
            seen_canon.add(canon)
        deduped.append(a)
    # (2) prune BARE census records (name==host, no skills/description) whose host
    #     is already represented by a richer listing — the cross-registry double
    #     count, without dropping genuinely distinct agents sharing a host.
    rich_hosts = {
        _ep_host(a.get("endpoint")) for a in deduped
        if _ep_host(a.get("endpoint")) and a.get("source") != "x402-census"
        and (a.get("skills") or (a.get("description") or "").strip())
    }
    deduped = [
        a for a in deduped
        if not (
            a.get("source") == "x402-census"
            and not a.get("skills")
            and not (a.get("description") or "").strip()
            and _ep_host(a.get("endpoint")) in rich_hosts
        )
    ]
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
                    "agentverse.ai", "x402-census (CDP discovery)", "registry.smithery.ai"],
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
