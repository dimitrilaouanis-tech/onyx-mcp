"""Side-by-side tool-catalog diff between any two MCP servers.

Given two MCP server URLs, fetch /manifest from each (with /openapi.json
fallback), normalize the tool lists, and emit a structured diff: tools
present only in A, only in B, in both with same price, in both with
different price, in both with different schema.

Lane: no public MCP catalog diff tool exists. Useful for:
  - competitor analysis ('is X cheaper for the same tool?')
  - deployment regression ('did our last deploy lose a tool?')
  - migration prep ('what would I miss if I switch from A to B?')

Stdlib-only. SSRF-hardened. Free tier.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import socket
import urllib.error
import urllib.parse
import urllib.request

NAME = "onyx_mcp_catalog_diff"
PRICE_USDC = "0"
TIER = "free"
DESCRIPTION = (
    "Side-by-side tool catalog diff between any two MCP servers. Fetches "
    "each server's /manifest (with /openapi.json fallback), normalizes the "
    "tool lists, and returns: only-in-A, only-in-B, same in both, price "
    "delta, schema delta. Free tier — useful for competitor analysis, "
    "regression detection, and migration planning."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "server_a": {
            "type": "string",
            "description": "Base URL of the first MCP server (e.g. https://onyx-actions.onrender.com).",
        },
        "server_b": {
            "type": "string",
            "description": "Base URL of the second MCP server.",
        },
    },
    "required": ["server_a", "server_b"],
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


def _fetch_json(url: str, timeout: float = 8.0) -> tuple[dict | None, int | None, str]:
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; OnyxCatalogDiff/1.0)",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(262144).decode("utf-8", "replace")
            return json.loads(raw), resp.status, ""
    except urllib.error.HTTPError as e:
        return None, e.code, ""
    except Exception as e:
        return None, None, str(e)[:160]


def _normalize_from_manifest(manifest: dict) -> dict[str, dict]:
    """A typical /manifest endpoint returns {tools: [{name, price_usdc, ...}]}."""
    out: dict[str, dict] = {}
    tools = manifest.get("tools") or manifest.get("services") or []
    if not isinstance(tools, list):
        return out
    for t in tools:
        if not isinstance(t, dict):
            continue
        name = t.get("name") or t.get("resource") or t.get("id")
        if not name:
            continue
        price = t.get("price_usdc") or t.get("price") or t.get("maxAmountRequired")
        try:
            price_f = float(str(price)) if price is not None else None
        except Exception:
            price_f = None
        schema = t.get("input_schema") or t.get("inputSchema") or t.get("schema")
        schema_hash = (
            hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest()[:16]
            if schema else None
        )
        out[str(name)] = {
            "name": str(name),
            "price_usdc": price_f,
            "schema_hash": schema_hash,
            "tier": t.get("tier"),
            "description": (t.get("description") or "")[:200],
        }
    return out


def _normalize_from_openapi(spec: dict) -> dict[str, dict]:
    """Fallback: pull POST routes under /v1/ from openapi.json."""
    out: dict[str, dict] = {}
    paths = spec.get("paths") or {}
    for path, methods in paths.items():
        if "/v1/" not in path:
            continue
        for method, op in (methods or {}).items():
            if method.lower() != "post" or not isinstance(op, dict):
                continue
            name = path.rstrip("/").split("/")[-1]
            schema = (((op.get("requestBody") or {}).get("content") or {}).get("application/json") or {}).get("schema")
            schema_hash = (
                hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest()[:16]
                if schema else None
            )
            out[name] = {
                "name": name,
                "price_usdc": None,
                "schema_hash": schema_hash,
                "tier": None,
                "description": (op.get("summary") or op.get("description") or "")[:200],
            }
    return out


def _load_catalog(base: str) -> tuple[dict[str, dict], str]:
    """Try /manifest first, fall back to /openapi.json. Returns (tools, source)."""
    manifest, _, err = _fetch_json(base + "/manifest")
    if isinstance(manifest, dict):
        tools = _normalize_from_manifest(manifest)
        if tools:
            return tools, "manifest"
    spec, _, err2 = _fetch_json(base + "/openapi.json")
    if isinstance(spec, dict):
        tools = _normalize_from_openapi(spec)
        if tools:
            return tools, "openapi"
    return {}, f"both /manifest and /openapi.json unusable ({err or err2 or 'no error'})"


def run(server_a: str, server_b: str, **_: object) -> dict:
    for label, val in (("server_a", server_a), ("server_b", server_b)):
        if not isinstance(val, str) or not val:
            raise ValueError(f"{label} is required")
        parsed = urllib.parse.urlparse(val.strip())
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"{label} must be http:// or https://")
        if parsed.hostname and not _is_public(parsed.hostname):
            return {"ok": False, "error": f"{label} not on a public address"}

    base_a = server_a.rstrip("/")
    base_b = server_b.rstrip("/")

    tools_a, source_a = _load_catalog(base_a)
    tools_b, source_b = _load_catalog(base_b)

    names_a = set(tools_a)
    names_b = set(tools_b)

    only_in_a = sorted(names_a - names_b)
    only_in_b = sorted(names_b - names_a)
    in_both = sorted(names_a & names_b)

    price_deltas = []
    schema_deltas = []
    same = []
    for name in in_both:
        a = tools_a[name]
        b = tools_b[name]
        if a["price_usdc"] != b["price_usdc"] and not (a["price_usdc"] is None or b["price_usdc"] is None):
            price_deltas.append({"name": name, "a_price": a["price_usdc"], "b_price": b["price_usdc"],
                                 "delta": (b["price_usdc"] or 0) - (a["price_usdc"] or 0)})
        elif a["schema_hash"] != b["schema_hash"] and a["schema_hash"] and b["schema_hash"]:
            schema_deltas.append({"name": name, "a_schema_hash": a["schema_hash"], "b_schema_hash": b["schema_hash"]})
        else:
            same.append(name)

    return {
        "ok": True,
        "server_a": base_a,
        "server_b": base_b,
        "source_a": source_a,
        "source_b": source_b,
        "counts": {
            "in_a": len(names_a),
            "in_b": len(names_b),
            "in_both": len(in_both),
            "only_a": len(only_in_a),
            "only_b": len(only_in_b),
            "price_deltas": len(price_deltas),
            "schema_deltas": len(schema_deltas),
            "fully_same": len(same),
        },
        "only_in_a": only_in_a,
        "only_in_b": only_in_b,
        "price_deltas": price_deltas,
        "schema_deltas": schema_deltas,
        "fully_same_tools": same,
    }


run.__when_to_use__ = (
    "An MCP server operator wants to compare their catalog against a competitor "
    "(pricing power, missing tools), check for regression after a deploy, or plan "
    "a migration. One call, two URLs."
)
run.__vs_alternatives__ = (
    "Existing options: open two manifest pages in browser tabs and squint, or write "
    "your own diff script. No public tool. This is the first."
)
run.__example_request__ = {
    "server_a": "https://onyx-actions.onrender.com",
    "server_b": "https://oatp.cc",
}
run.__example_response__ = {
    "ok": True,
    "counts": {"in_a": 47, "in_b": 12, "in_both": 5, "only_a": 42, "only_b": 7, "price_deltas": 3, "schema_deltas": 0, "fully_same": 2},
    "only_in_a": ["onyx_aml_screen", "..."],
    "price_deltas": [{"name": "tool_x", "a_price": 0.05, "b_price": 0.10, "delta": 0.05}],
}
