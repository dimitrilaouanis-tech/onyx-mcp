"""General x402 / MCP HTTP error explainer.

Sister tool to verify_explain (which only handles /verify failures). This
takes ANY HTTP error response from an x402 / MCP flow — 400, 401, 402,
403, 404, 405, 422, 429, 500, 502, 503 — and returns a plain-English
diagnosis with actionable fix.

Lane: when an agent fails to settle / register / call, the error body is
often opaque. This tool maps known error shapes (FastAPI, OAuth2, EIP-712,
x402 spec error codes, Coinbase facilitator) to specific causes.

Stdlib-only. No SSRF risk — pure local pattern matching.
"""
from __future__ import annotations

import json
import re

NAME = "onyx_x402_error_explain"
PRICE_USDC = "0"
TIER = "free"
DESCRIPTION = (
    "Plain-English explainer for any HTTP error in an x402 / MCP flow. "
    "Pass the status code + response body (or headers), get back a diagnosis "
    "with specific cause and actionable fix. Covers FastAPI validation, "
    "OAuth2 DCR failures, EIP-712 signature errors, x402 spec error codes, "
    "and Coinbase facilitator-specific responses. Free tier — local logic, "
    "no network calls."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "status_code": {
            "type": "integer",
            "description": "HTTP status code returned by the server (e.g. 402, 422, 401).",
        },
        "response_body": {
            "type": "string",
            "description": "Raw response body as text. JSON is auto-detected and parsed.",
        },
        "response_headers": {
            "type": "object",
            "description": "Optional. HTTP response headers, useful for 402 challenges that carry payment-required header.",
            "additionalProperties": {"type": "string"},
        },
        "request_summary": {
            "type": "string",
            "description": "Optional. One-line summary of what the caller was trying to do.",
        },
    },
    "required": ["status_code"],
}


# Pattern → (cause, fix) catalog
_PATTERNS = [
    # x402 spec / facilitator errors
    {
        "match": lambda code, body, hdr: code == 402 and "payment-required" in (hdr or {}),
        "title": "Standard x402 challenge",
        "cause": "Server is asking the agent to pay. This is the NORMAL first-call response in x402.",
        "fix": "Decode the payment-required header (base64 JSON), pick an accepts[] entry, sign EIP-3009 TransferWithAuthorization, retry with PAYMENT-SIGNATURE header.",
    },
    {
        "match": lambda code, body, hdr: code == 402 and "payment-required" not in (hdr or {}),
        "title": "402 with no payment-required header",
        "cause": "Server returned 402 but didn't expose the payment challenge. Either misconfigured server, or facilitator-returned error masked as 402.",
        "fix": "Inspect response body for an x402-style 'accepts' array. If absent, the server is broken — report to operator. Use onyx_verify_explain to probe.",
    },
    {
        "match": lambda code, body, hdr: code == 401 and "DPoP" in (body or ""),
        "title": "OAuth DPoP required",
        "cause": "MCP server expects DPoP proof-of-possession on bearer token. Plain bearer is rejected.",
        "fix": "Mint a DPoP key, attach DPoP header on every request, use it during token exchange. Most MCP servers don't require this — check if a simpler grant works.",
    },
    {
        "match": lambda code, body, hdr: code == 401 and "Bearer" in (hdr or {}).get("WWW-Authenticate", ""),
        "title": "Missing or invalid OAuth2 bearer token",
        "cause": "Server requires OAuth2 access token. None provided, or expired.",
        "fix": "Discover token endpoint at /.well-known/oauth-authorization-server, register via /oauth/register (DCR), call /oauth/token, attach Authorization: Bearer <token>.",
    },
    {
        "match": lambda code, body, hdr: code == 422 and "detail" in (body or "").lower(),
        "title": "FastAPI request validation failure",
        "cause": "Body fields don't match the route's input schema. FastAPI returns 'detail' array listing each violation.",
        "fix": "Parse 'detail' for {loc, msg, type}. For each, fix the field at body[loc[1:]]. Common: missing required field, wrong type, value out of range.",
    },
    {
        "match": lambda code, body, hdr: code == 400 and re.search(r"signature|sig.*invalid|recover", body or "", re.I),
        "title": "EIP-712 / EIP-3009 signature invalid",
        "cause": "Facilitator rejected the payment signature. Causes: wrong domain (chainId/contract), wrong primary type, validBefore in past, nonce already used, signer != from-address.",
        "fix": "Use onyx_verify_explain to diagnose. Verify EIP-712 domain matches the chain's USDC contract. Check validBefore > now+30s. Generate fresh nonce.",
    },
    {
        "match": lambda code, body, hdr: code == 400 and "nonce" in (body or "").lower(),
        "title": "Nonce error in payment authorization",
        "cause": "EIP-3009 nonce already used (replay protection) or malformed (must be 32-byte hex).",
        "fix": "Generate a new random 32-byte nonce per payment. Don't reuse nonces. Update payload.authorization.nonce.",
    },
    {
        "match": lambda code, body, hdr: code == 403,
        "title": "Authenticated but forbidden",
        "cause": "Token / signature valid, but caller lacks permission. Could be IP allowlist, scope mismatch, or tier-locked tool.",
        "fix": "Check WWW-Authenticate for required scope. If scope mismatch, request elevated token. If IP-locked, route through an allowlisted egress.",
    },
    {
        "match": lambda code, body, hdr: code == 404,
        "title": "Route not found",
        "cause": "Path doesn't exist on this server. Common: outdated tool name, /v1 vs /v2 prefix mismatch, server moved.",
        "fix": "GET /manifest to enumerate live tools. GET /openapi.json paths to list all routes. Compare against the path you called.",
    },
    {
        "match": lambda code, body, hdr: code == 405,
        "title": "Wrong HTTP method",
        "cause": "Endpoint exists but doesn't accept this verb. Paid x402 tools are typically POST; introspection is GET.",
        "fix": "Use POST for paid tool invocations. Check the Allow response header for accepted methods.",
    },
    {
        "match": lambda code, body, hdr: code == 429,
        "title": "Rate limited",
        "cause": "Too many requests in window. Most x402 servers do per-IP or per-wallet limits.",
        "fix": "Honor Retry-After header. Implement exponential backoff. For sustained traffic, raise the issue with operator or upgrade tier.",
    },
    {
        "match": lambda code, body, hdr: code == 500 and "facilitator" in (body or "").lower(),
        "title": "Facilitator-side 500",
        "cause": "Coinbase CDP or x402 facilitator returned an error. Often a transient outage or auth misconfiguration on the server side.",
        "fix": "Try again in 30s. If persistent, check facilitator status. Server operator should verify CDP_API_KEY_ID/SECRET env vars are set.",
    },
    {
        "match": lambda code, body, hdr: code == 500,
        "title": "Server-side error",
        "cause": "Unhandled exception in the server. Could be missing env var, downstream API failure, or code bug.",
        "fix": "Retry once. If persistent, capture the request and report to operator. Operator should check stderr logs for traceback.",
    },
    {
        "match": lambda code, body, hdr: code in (502, 503, 504),
        "title": "Upstream / gateway error",
        "cause": "Edge proxy (Cloudflare, Render router) couldn't reach origin, or origin returned bad gateway. Often a cold-start on serverless.",
        "fix": "Retry after 5-15s; origins often warm up. If persistent, status page may have details.",
    },
]


def _try_parse_json(body: str) -> dict | None:
    if not body:
        return None
    try:
        return json.loads(body)
    except Exception:
        return None


def run(
    status_code: int,
    response_body: str = "",
    response_headers: dict | None = None,
    request_summary: str = "",
    **_: object,
) -> dict:
    if not isinstance(status_code, int):
        raise ValueError("status_code must be an integer")
    response_body = response_body or ""
    response_headers = response_headers or {}
    # Normalize header names to capitalised
    norm_hdr = {str(k): str(v) for k, v in response_headers.items()}
    norm_hdr_lc = {k.lower(): v for k, v in norm_hdr.items()}
    if "payment-required" in norm_hdr_lc and "payment-required" not in norm_hdr:
        norm_hdr["payment-required"] = norm_hdr_lc["payment-required"]

    matches = []
    for pat in _PATTERNS:
        try:
            if pat["match"](status_code, response_body, norm_hdr):
                matches.append({"title": pat["title"], "cause": pat["cause"], "fix": pat["fix"]})
        except Exception:
            pass

    if not matches:
        # Generic fallback by code
        if 200 <= status_code < 300:
            matches.append({
                "title": "Not an error",
                "cause": f"Status {status_code} is a success code. Nothing to diagnose.",
                "fix": "If the call succeeded but result is wrong, inspect the parsed body, not the status code.",
            })
        elif 300 <= status_code < 400:
            matches.append({
                "title": "Redirect",
                "cause": f"Status {status_code} is a redirect. Caller may not be following Location header.",
                "fix": "Follow the Location header (most HTTP clients do automatically; if not, enable redirect-following).",
            })
        else:
            matches.append({
                "title": f"Unrecognized {status_code}",
                "cause": "No pattern matched. The error body is unfamiliar.",
                "fix": "Capture body + headers + request_summary, ask the server operator. Or run onyx_mcp_health on the server URL for a broader probe.",
            })

    json_body = _try_parse_json(response_body)

    return {
        "ok": True,
        "status_code": status_code,
        "request_summary": request_summary,
        "match_count": len(matches),
        "primary_explanation": matches[0],
        "all_explanations": matches,
        "parsed_body": json_body,
        "next_step": (
            "Apply the 'fix' from primary_explanation. If still failing, "
            "call onyx_verify_explain (for /verify) or onyx_mcp_health "
            "(for server-wide audit)."
        ),
    }


run.__when_to_use__ = (
    "An agent / client got back an HTTP error from an x402 or MCP server and "
    "doesn't know what it means. Pass status + body + headers, get a clear "
    "diagnosis. Saves 20 min of doc-reading per opaque failure."
)
run.__vs_alternatives__ = (
    "HTTP spec lists 30+ codes generically; x402 / MCP / OAuth add layered "
    "meanings. No public 'explain this error in agent context' tool exists. "
    "This catalogs the 14 most common shapes."
)
run.__example_request__ = {
    "status_code": 422,
    "response_body": '{"detail":[{"loc":["body","wallet_address"],"msg":"field required","type":"value_error.missing"}]}',
    "request_summary": "POST /v1/onyx_agent_id with empty body",
}
run.__example_response__ = {
    "ok": True,
    "status_code": 422,
    "match_count": 1,
    "primary_explanation": {
        "title": "FastAPI request validation failure",
        "cause": "Body fields don't match the route's input schema...",
        "fix": "Parse 'detail' for {loc, msg, type}...",
    },
}
