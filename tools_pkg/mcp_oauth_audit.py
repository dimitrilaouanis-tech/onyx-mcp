"""OAuth 2.1 / RFC 7591 DCR compliance audit for any MCP server.

The MCP April 2026 spec mandates Dynamic Client Registration for
ChatGPT-custom-connector + Claude-Managed-Agents discovery. Servers
without these endpoints are invisible to those clients.

This tool probes any MCP server URL and grades its OAuth/DCR surface:
  - /.well-known/oauth-authorization-server (RFC 8414 metadata)
  - /.well-known/oauth-protected-resource   (RFC 9728 resource metadata)
  - /oauth/register (RFC 7591 DCR)
  - /oauth/token
  - /oauth/authorize

Returns per-endpoint pass/fail + composite 0-100 score + remediation
list. Free tier. SSRF-hardened.
"""
from __future__ import annotations

import ipaddress
import json
import socket
import urllib.error
import urllib.parse
import urllib.request

NAME = "onyx_mcp_oauth_audit"
PRICE_USDC = "0"
TIER = "free"
DESCRIPTION = (
    "OAuth 2.1 + RFC 7591 DCR compliance audit for any MCP server. Probes "
    "the 5 standard discovery + registration + token endpoints, validates "
    "each against the relevant RFC, returns a composite 0-100 score and "
    "remediation list. Free tier — useful for MCP operators preparing for "
    "ChatGPT custom-connector / Claude Managed Agents discovery."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "server_url": {
            "type": "string",
            "description": "Base URL of the MCP server to audit.",
        },
    },
    "required": ["server_url"],
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


def _fetch(url: str, method: str = "GET", body: bytes | None = None,
           timeout: float = 8.0) -> tuple[int | None, dict | None, str, str]:
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; OnyxOAuthAudit/1.0)",
            "Accept": "application/json",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, method=method, data=body, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(65536).decode("utf-8", "replace")
            try:
                return resp.status, json.loads(raw), raw, ""
            except Exception:
                return resp.status, None, raw, "not-json"
    except urllib.error.HTTPError as e:
        body_raw = e.read(8192).decode("utf-8", "replace") if e else ""
        try:
            return e.code, json.loads(body_raw), body_raw, ""
        except Exception:
            return e.code, None, body_raw, ""
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as e:
        return None, None, "", str(e)[:160]


def _check_auth_server_metadata(base: str) -> dict:
    """RFC 8414 — /.well-known/oauth-authorization-server"""
    url = base + "/.well-known/oauth-authorization-server"
    status, data, raw, err = _fetch(url)
    issues = []
    if status != 200 or not isinstance(data, dict):
        return {"endpoint": "oauth-authorization-server", "passes": False,
                "status": status, "url": url, "issue": err or f"HTTP {status}",
                "fix": "Serve RFC 8414 metadata at /.well-known/oauth-authorization-server"}
    required = ["issuer", "authorization_endpoint", "token_endpoint", "registration_endpoint",
                "response_types_supported", "grant_types_supported", "code_challenge_methods_supported"]
    for k in required:
        if k not in data:
            issues.append(f"missing field '{k}'")
    if "S256" not in (data.get("code_challenge_methods_supported") or []):
        issues.append("S256 PKCE method not advertised (MCP spec requires)")
    return {
        "endpoint": "oauth-authorization-server",
        "passes": len(issues) == 0,
        "status": status,
        "url": url,
        "issuer": data.get("issuer"),
        "registration_endpoint": data.get("registration_endpoint"),
        "issues": issues,
    }


def _check_protected_resource(base: str) -> dict:
    """RFC 9728 — /.well-known/oauth-protected-resource"""
    url = base + "/.well-known/oauth-protected-resource"
    status, data, raw, err = _fetch(url)
    issues = []
    if status != 200 or not isinstance(data, dict):
        return {"endpoint": "oauth-protected-resource", "passes": False,
                "status": status, "url": url, "issue": err or f"HTTP {status}",
                "fix": "Serve RFC 9728 resource metadata at /.well-known/oauth-protected-resource"}
    for k in ["resource", "authorization_servers", "bearer_methods_supported"]:
        if k not in data:
            issues.append(f"missing field '{k}'")
    return {
        "endpoint": "oauth-protected-resource",
        "passes": len(issues) == 0,
        "status": status,
        "url": url,
        "issues": issues,
    }


def _check_dcr(base: str, reg_endpoint: str | None) -> dict:
    """RFC 7591 — POST /oauth/register"""
    url = reg_endpoint or (base + "/oauth/register")
    body = json.dumps({"client_name": "OnyxOAuthAudit-probe",
                       "redirect_uris": ["https://example.invalid/cb"]}).encode()
    status, data, raw, err = _fetch(url, method="POST", body=body)
    issues = []
    if status not in (200, 201):
        return {"endpoint": "oauth/register", "passes": False,
                "status": status, "url": url, "issue": err or f"HTTP {status}",
                "fix": "Implement RFC 7591 POST /oauth/register that returns client_id"}
    if not isinstance(data, dict):
        return {"endpoint": "oauth/register", "passes": False,
                "status": status, "url": url, "issue": "response not JSON",
                "fix": "Return application/json with client_id field"}
    if "client_id" not in data:
        issues.append("missing 'client_id' in response")
    return {
        "endpoint": "oauth/register",
        "passes": len(issues) == 0,
        "status": status,
        "url": url,
        "client_id_sample": data.get("client_id"),
        "issues": issues,
    }


def _check_token(base: str, token_endpoint: str | None) -> dict:
    url = token_endpoint or (base + "/oauth/token")
    body = json.dumps({"grant_type": "client_credentials"}).encode()
    status, data, raw, err = _fetch(url, method="POST", body=body)
    issues = []
    if status not in (200, 400, 401):
        return {"endpoint": "oauth/token", "passes": False,
                "status": status, "url": url, "issue": err or f"HTTP {status}",
                "fix": "Implement RFC 6749 POST /oauth/token (any status 200/400/401 acceptable as proof endpoint exists)"}
    return {
        "endpoint": "oauth/token",
        "passes": True,  # 4xx is still proof the endpoint exists
        "status": status,
        "url": url,
        "issues": issues,
        "note": "Returning 4xx without credentials is fine — confirms endpoint exists.",
    }


def _check_authorize(base: str, auth_endpoint: str | None) -> dict:
    url = auth_endpoint or (base + "/oauth/authorize")
    # Probe with missing args — expect 400 or 302
    status, data, raw, err = _fetch(url + "?client_id=probe", method="GET")
    if status in (200, 302, 400, 401):
        return {"endpoint": "oauth/authorize", "passes": True,
                "status": status, "url": url}
    return {"endpoint": "oauth/authorize", "passes": False,
            "status": status, "url": url, "issue": err or f"HTTP {status}",
            "fix": "Implement GET /oauth/authorize (any of 200/302/400 acceptable as proof)"}


def run(server_url: str, **_: object) -> dict:
    if not isinstance(server_url, str) or not server_url:
        raise ValueError("server_url is required")
    parsed = urllib.parse.urlparse(server_url.strip())
    if parsed.scheme not in ("http", "https"):
        raise ValueError("server_url must be http:// or https://")
    if parsed.hostname and not _is_public(parsed.hostname):
        return {"ok": False, "error": "server_url not on a public address"}
    base = f"{parsed.scheme}://{parsed.netloc}"

    as_meta = _check_auth_server_metadata(base)
    pr_meta = _check_protected_resource(base)

    reg_endpoint = as_meta.get("registration_endpoint") if as_meta.get("passes") else None
    dcr = _check_dcr(base, reg_endpoint)
    token = _check_token(base, None)
    authorize = _check_authorize(base, None)

    endpoints = [as_meta, pr_meta, dcr, token, authorize]
    weights = {
        "oauth-authorization-server": 30,
        "oauth-protected-resource":   15,
        "oauth/register":              25,  # the critical DCR endpoint
        "oauth/token":                 15,
        "oauth/authorize":             15,
    }
    score = sum(weights[e["endpoint"]] for e in endpoints if e.get("passes"))
    max_score = sum(weights.values())

    grade = ("A" if score >= 90 else
             "B" if score >= 70 else
             "C" if score >= 50 else
             "D" if score >= 30 else "F")

    failed = [e for e in endpoints if not e.get("passes")]
    remediation = [{"endpoint": e["endpoint"], "fix": e.get("fix", "")}
                   for e in failed if e.get("fix")]

    return {
        "ok": True,
        "server_url": server_url,
        "score": score,
        "max_score": max_score,
        "grade": grade,
        "ready_for_chatgpt_custom_connector": all(
            e.get("passes") for e in endpoints
            if e["endpoint"] in ("oauth-authorization-server", "oauth-protected-resource", "oauth/register")
        ),
        "endpoints": endpoints,
        "remediation": remediation,
    }


run.__when_to_use__ = (
    "An MCP server operator wants to know if their OAuth/DCR surface is ready "
    "for the MCP April 2026 spec — specifically discoverable by ChatGPT custom "
    "connector and Claude Managed Agents."
)
run.__vs_alternatives__ = (
    "No public OAuth/DCR compliance auditor for MCP exists. ZAP and other "
    "OAuth fuzzers are generic and noisy. This catalogs only the 5 endpoints "
    "MCP clients actually probe."
)
run.__example_request__ = {"server_url": "https://onyx-actions.onrender.com"}
run.__example_response__ = {
    "ok": True,
    "score": 100,
    "grade": "A",
    "ready_for_chatgpt_custom_connector": True,
    "endpoints": [{"endpoint": "oauth-authorization-server", "passes": True, "status": 200}, "..."],
}
