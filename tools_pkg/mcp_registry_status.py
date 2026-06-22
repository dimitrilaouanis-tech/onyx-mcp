"""Cross-registry listing status for any MCP server.

Given an MCP server URL or owner/repo, checks whether it's listed in:
  - Coinbase Bazaar (x402 discovery feed)
  - Smithery (smithery.ai)
  - Glama (glama.ai)
  - MCP Registry (official)
  - awesome-mcp-servers (community)

Returns per-registry status + a coverage score 0-100. Useful for MCP
server operators auditing their distribution, and agents preferring
multi-registry-validated services.

Stdlib HTTP. SSRF-hardened. Free tier.
"""
from __future__ import annotations

import ipaddress
import json
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

NAME = "onyx_mcp_registry_status"
PRICE_USDC = "0"
TIER = "free"
DESCRIPTION = (
    "Cross-registry listing audit for any MCP server. Checks Coinbase Bazaar "
    "(x402 discovery), Smithery, Glama, the official MCP Registry, and the "
    "awesome-mcp-servers list. Returns per-registry status + coverage score "
    "0-100 + remediation suggestions for unlisted registries. Free tier."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "server_url": {
            "type": "string",
            "description": "Base URL of the MCP server to audit (e.g. https://onyx-actions.onrender.com). Required for Bazaar lookup.",
        },
        "github_repo": {
            "type": "string",
            "description": "owner/repo slug if the server is open-source (e.g. 'onyx/onyx-mcp'). Required for Smithery/Glama/awesome-mcp-servers lookups.",
        },
    },
}


def _is_public(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False
    for _, _, _, _, sa in infos:
        try:
            ip = ipaddress.ip_address(sa[0])
        except ValueError:
            return False
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_multicast or ip.is_reserved):
            return False
    return True


def _fetch(url: str, timeout: float = 8.0) -> tuple[int | None, str, str]:
    """Returns (status, body, error)."""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; OnyxRegistryStatus/1.0)",
            "Accept": "application/json, text/plain, text/html;q=0.5",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(65536).decode("utf-8", "replace"), ""
    except urllib.error.HTTPError as e:
        body = e.read(4096).decode("utf-8", "replace") if e else ""
        return e.code, body, ""
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as e:
        return None, "", str(e)[:160]


def _check_bazaar(server_url: str) -> dict:
    """Pull the Onyx mirror of Coinbase Bazaar and grep for our domain."""
    parsed = urllib.parse.urlparse(server_url)
    target_domain = (parsed.hostname or "").lower()
    if not target_domain:
        return {"listed": False, "reason": "server_url missing host"}
    status, body, err = _fetch("https://onyx-actions.onrender.com/bazaar.json?view=newest&limit=500")
    if err:
        return {"listed": None, "error": err}
    try:
        rows = json.loads(body).get("rows", [])
    except Exception:
        return {"listed": None, "error": "bazaar response not JSON"}
    matches = [r for r in rows if target_domain in (r.get("domain") or r.get("resource") or "").lower()]
    return {
        "listed": len(matches) > 0,
        "rows_in_bazaar": len(rows),
        "matches": len(matches),
        "sample": matches[:2] if matches else None,
        "submission_endpoint": "https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources (typically populated by crawl of /openapi.json + x402 settlements)",
    }


def _check_smithery(repo: str) -> dict:
    """Smithery server URL pattern: smithery.ai/server/<owner>/<repo>."""
    if not repo or "/" not in repo:
        return {"listed": None, "skipped": "no github_repo provided"}
    url = f"https://smithery.ai/server/{repo}"
    status, body, err = _fetch(url)
    if err:
        return {"listed": None, "error": err}
    # Smithery returns 404 if not listed, 200 if listed
    return {
        "listed": status == 200,
        "status": status,
        "url": url,
        "submission_endpoint": "https://smithery.ai/new (manual submit, requires WorkOS auth)",
    }


def _check_glama(repo: str) -> dict:
    if not repo or "/" not in repo:
        return {"listed": None, "skipped": "no github_repo provided"}
    url = f"https://glama.ai/mcp/servers/{repo}"
    status, body, err = _fetch(url)
    if err:
        return {"listed": None, "error": err}
    return {
        "listed": status == 200,
        "status": status,
        "url": url,
        "submission_endpoint": "https://glama.ai/mcp/servers (requires Dockerfile + manual submit)",
    }


def _check_mcp_registry(repo: str) -> dict:
    """Official MCP Registry — github.com/modelcontextprotocol/registry"""
    if not repo or "/" not in repo:
        return {"listed": None, "skipped": "no github_repo provided"}
    url = f"https://registry.modelcontextprotocol.io/v0/servers?search={urllib.parse.quote(repo)}"
    status, body, err = _fetch(url)
    if err:
        return {"listed": None, "error": err, "url": url}
    if status != 200:
        return {"listed": None, "status": status, "url": url}
    try:
        servers = json.loads(body).get("servers", []) if body else []
    except Exception:
        servers = []
    matches = [s for s in servers if repo.lower() in str(s).lower()]
    return {
        "listed": len(matches) > 0,
        "matches": len(matches),
        "url": url,
        "submission_endpoint": "https://registry.modelcontextprotocol.io (requires PyPI/npm publish first + manifest submit via mcp-publisher CLI)",
    }


def _check_awesome_mcp_servers(repo: str) -> dict:
    if not repo or "/" not in repo:
        return {"listed": None, "skipped": "no github_repo provided"}
    url = "https://raw.githubusercontent.com/punkpeye/awesome-mcp-servers/main/README.md"
    status, body, err = _fetch(url, timeout=12)
    if err:
        return {"listed": None, "error": err}
    listed = repo.lower() in (body or "").lower()
    return {
        "listed": listed,
        "url": "https://github.com/punkpeye/awesome-mcp-servers",
        "submission_endpoint": "PR to punkpeye/awesome-mcp-servers (requires Glama badge first per their bot)",
    }


def run(
    server_url: str | None = None,
    github_repo: str | None = None,
    **_: object,
) -> dict:
    if not server_url and not github_repo:
        raise ValueError("provide server_url and/or github_repo")

    # SSRF check on server_url
    if server_url:
        parsed = urllib.parse.urlparse(server_url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("server_url must be http:// or https://")
        if parsed.hostname and not _is_public(parsed.hostname):
            return {"ok": False, "error": "server_url not on a public address"}

    if github_repo and not re.match(r"^[\w.-]+/[\w.-]+$", github_repo):
        raise ValueError("github_repo must be 'owner/repo' format")

    registries = {
        "bazaar":      _check_bazaar(server_url) if server_url else {"listed": None, "skipped": "no server_url"},
        "smithery":    _check_smithery(github_repo) if github_repo else {"listed": None, "skipped": "no github_repo"},
        "glama":       _check_glama(github_repo) if github_repo else {"listed": None, "skipped": "no github_repo"},
        "mcp_registry": _check_mcp_registry(github_repo) if github_repo else {"listed": None, "skipped": "no github_repo"},
        "awesome_mcp_servers": _check_awesome_mcp_servers(github_repo) if github_repo else {"listed": None, "skipped": "no github_repo"},
    }

    listed_count = sum(1 for r in registries.values() if r.get("listed") is True)
    checked_count = sum(1 for r in registries.values() if r.get("listed") is not None)
    coverage = int(100 * listed_count / max(checked_count, 1)) if checked_count else 0

    missing = [name for name, r in registries.items() if r.get("listed") is False]

    return {
        "ok": True,
        "server_url": server_url,
        "github_repo": github_repo,
        "registries_checked": checked_count,
        "registries_listed_in": listed_count,
        "coverage_score": coverage,
        "missing_from": missing,
        "registries": registries,
        "remediation": [
            f"To add to {name}: {registries[name].get('submission_endpoint', 'see registry')}"
            for name in missing
        ],
    }


run.__when_to_use__ = (
    "An MCP server operator wants to know exactly where their server IS and "
    "ISN'T listed across the 5 main discovery surfaces, with remediation paths "
    "for unlisted registries. Or an agent prefers cross-validated servers."
)
run.__vs_alternatives__ = (
    "No cross-registry MCP listing checker exists today. Each registry has its "
    "own search UI; nobody aggregates. This is the first lookup; one call "
    "replaces 5 manual searches."
)
run.__example_request__ = {
    "server_url": "https://onyx-actions.onrender.com",
    "github_repo": "onyx/onyx-mcp",
}
run.__example_response__ = {
    "ok": True,
    "registries_checked": 5,
    "registries_listed_in": 1,
    "coverage_score": 20,
    "missing_from": ["bazaar", "smithery", "glama", "mcp_registry"],
    "remediation": ["To add to bazaar: ...", "..."],
}
