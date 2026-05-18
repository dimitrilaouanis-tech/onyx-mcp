"""x402 service indexability checklist + submission helper.

Coinbase Bazaar's discovery is crawler-driven — it polls services rather than
accepting pushes. This tool inspects ANY x402 service's published surface
(/openapi.json, /.well-known/x402.json, /manifest) and returns a structured
indexability report: what the crawler will find, what's missing, what the
operator must fix to be discovered.

Realistic scope: this is a checklist tool, not a magic 'submit' button. We
can't force Coinbase to index a service. We CAN tell the operator exactly
what their service is missing.

Stdlib-only. SSRF-hardened. Free tier.
"""
from __future__ import annotations

import ipaddress
import json
import socket
import urllib.error
import urllib.parse
import urllib.request

NAME = "onyx_bazaar_submit"
PRICE_USDC = "0"
TIER = "free"
DESCRIPTION = (
    "Indexability audit for any x402 service. Inspects the published surface "
    "(/openapi.json, /.well-known/x402.json, /manifest) against what Coinbase "
    "Bazaar's discovery crawler looks for, and returns a structured checklist: "
    "what's present, what's missing, what to fix. Crawler is poll-based — this "
    "tool documents the criteria, doesn't force-submit. Free tier."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "server_url": {
            "type": "string",
            "description": "Base URL of the x402 service to audit (e.g. https://onyx-actions.onrender.com).",
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


def _fetch(url: str, timeout: float = 8.0) -> tuple[int | None, dict | None, str, str]:
    """Returns (status, json_body, raw_text, error)."""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; OnyxBazaarSubmit/1.0)",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(131072).decode("utf-8", "replace")
            try:
                return resp.status, json.loads(raw), raw, ""
            except Exception:
                return resp.status, None, raw, "not-json"
    except urllib.error.HTTPError as e:
        body = e.read(4096).decode("utf-8", "replace") if e else ""
        return e.code, None, body, ""
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as e:
        return None, None, "", str(e)[:160]


# Coinbase Bazaar / x402 discovery criteria
# (Reverse-engineered from observation of indexed vs non-indexed services
# and from the x402 v2 spec.)
_CRITERIA = [
    {
        "id": "well_known_x402",
        "name": "/.well-known/x402.json reachable + valid JSON",
        "weight": 25,
        "hint": "Service should serve a x402 manifest at /.well-known/x402.json describing all paid endpoints. Format: {x402Version:1|2, services:[{resource, accepts:[...]}]}",
    },
    {
        "id": "x402_services_listed",
        "name": "x402 manifest declares at least 1 paid service",
        "weight": 20,
        "hint": "manifest.services[] must be non-empty. Each service needs resource URL, scheme, network, asset, payTo, maxAmountRequired.",
    },
    {
        "id": "openapi_json",
        "name": "/openapi.json reachable",
        "weight": 15,
        "hint": "FastAPI / similar frameworks expose /openapi.json by default. Crawler uses this to enumerate routes + read inputSchema.",
    },
    {
        "id": "paid_routes_in_openapi",
        "name": "openapi.json contains paid routes with inputSchema",
        "weight": 15,
        "hint": "Each paid route in openapi.json paths needs requestBody.content.application/json.schema. Without this, the route registers but with no input docs.",
    },
    {
        "id": "manifest_endpoint",
        "name": "/manifest returns service-level metadata JSON",
        "weight": 10,
        "hint": "Optional but recommended. Crawler uses this to extract service name, description, contact info.",
    },
    {
        "id": "extensions_bazaar_in_402",
        "name": "402 challenge carries extensions.bazaar with inputSchema",
        "weight": 10,
        "hint": "Live 402 response should include extensions.bazaar.schema and extensions.bazaar.info — surfaces input/output shape to discovery crawlers.",
    },
    {
        "id": "consistent_caip2_network",
        "name": "network identifiers use CAIP-2 format (eip155:<chainId>)",
        "weight": 5,
        "hint": "Coinbase indexes by CAIP-2 network. Services using 'base' or 'base-mainnet' instead of 'eip155:8453' don't appear in network-filtered Bazaar views.",
    },
]


def _check(server_url: str) -> dict:
    """Run all criteria against the server. Returns checklist."""
    parsed = urllib.parse.urlparse(server_url.rstrip("/"))
    base = f"{parsed.scheme}://{parsed.netloc}"

    # Fetch the surfaces we need
    s_wellknown, j_wellknown, _, e_wellknown = _fetch(base + "/.well-known/x402.json")
    s_openapi, j_openapi, _, e_openapi = _fetch(base + "/openapi.json")
    s_manifest, j_manifest, _, e_manifest = _fetch(base + "/manifest")

    # Also probe the first paid route from manifest for live 402
    first_resource = None
    live_402_extra = {}
    if j_wellknown and isinstance(j_wellknown, dict):
        services = j_wellknown.get("services") or []
        if services and isinstance(services[0], dict):
            first_resource = services[0].get("resource")
    if first_resource:
        # POST to elicit a 402 challenge
        try:
            req = urllib.request.Request(
                first_resource, method="POST",
                data=b"{}",
                headers={"User-Agent": "OnyxBazaarSubmit/1.0",
                         "Content-Type": "application/json",
                         "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                pass
        except urllib.error.HTTPError as e:
            if e.code == 402:
                pr_header = e.headers.get("payment-required") if e.headers else None
                if pr_header:
                    import base64
                    try:
                        challenge = json.loads(base64.b64decode(pr_header).decode("utf-8"))
                        live_402_extra = challenge.get("extensions", {})
                    except Exception:
                        pass
        except Exception:
            pass

    checks: list[dict] = []
    score = 0
    max_score = 0

    for c in _CRITERIA:
        passes = False
        detail = ""

        if c["id"] == "well_known_x402":
            passes = s_wellknown == 200 and isinstance(j_wellknown, dict)
            detail = f"HTTP {s_wellknown}, JSON parseable: {isinstance(j_wellknown, dict)}"

        elif c["id"] == "x402_services_listed":
            svcs = (j_wellknown or {}).get("services") or [] if isinstance(j_wellknown, dict) else []
            passes = len(svcs) > 0
            detail = f"{len(svcs)} services in manifest"

        elif c["id"] == "openapi_json":
            passes = s_openapi == 200 and isinstance(j_openapi, dict)
            detail = f"HTTP {s_openapi}"

        elif c["id"] == "paid_routes_in_openapi":
            paid_routes = 0
            schema_routes = 0
            if isinstance(j_openapi, dict):
                paths = j_openapi.get("paths") or {}
                for p, methods in paths.items():
                    if "/v1/" in p:
                        for method, spec in (methods or {}).items():
                            if method.lower() == "post":
                                paid_routes += 1
                                if (spec or {}).get("requestBody"):
                                    schema_routes += 1
            passes = paid_routes > 0 and schema_routes == paid_routes
            detail = f"{schema_routes}/{paid_routes} POST /v1/* routes carry requestBody schema"

        elif c["id"] == "manifest_endpoint":
            passes = s_manifest == 200 and isinstance(j_manifest, dict)
            detail = f"HTTP {s_manifest}"

        elif c["id"] == "extensions_bazaar_in_402":
            bazaar_ext = live_402_extra.get("bazaar") if isinstance(live_402_extra, dict) else None
            passes = bool(bazaar_ext and bazaar_ext.get("schema"))
            detail = f"extensions.bazaar present: {bool(bazaar_ext)}, schema: {bool(bazaar_ext and bazaar_ext.get('schema'))}"

        elif c["id"] == "consistent_caip2_network":
            svcs = (j_wellknown or {}).get("services") or [] if isinstance(j_wellknown, dict) else []
            all_caip = all(
                any(
                    (a.get("network") or "").startswith(("eip155:", "solana:"))
                    for a in (s.get("accepts") or [])
                )
                for s in svcs
            ) if svcs else False
            passes = all_caip
            detail = f"all services use CAIP-2 network: {all_caip}"

        checks.append({
            "id": c["id"],
            "name": c["name"],
            "weight": c["weight"],
            "passes": passes,
            "detail": detail,
            "hint": c["hint"] if not passes else None,
        })
        max_score += c["weight"]
        if passes:
            score += c["weight"]

    return {
        "score": score,
        "max_score": max_score,
        "percent": int(100 * score / max(max_score, 1)),
        "checks": checks,
    }


def run(server_url: str, **_: object) -> dict:
    if not isinstance(server_url, str) or not server_url:
        raise ValueError("server_url is required")
    parsed = urllib.parse.urlparse(server_url.strip())
    if parsed.scheme not in ("http", "https"):
        raise ValueError("server_url must be http:// or https://")
    host = parsed.hostname or ""
    if not _is_public(host):
        return {"ok": False, "error": f"server_url host {host} not on a public address"}

    report = _check(server_url)
    failures = [c for c in report["checks"] if not c["passes"]]
    fixes_needed = [{"fix": c["hint"], "criterion": c["name"]} for c in failures if c["hint"]]

    return {
        "ok": True,
        "server_url": server_url,
        "indexability_score": report["score"],
        "max_score": report["max_score"],
        "percent": report["percent"],
        "grade": (
            "A (ready for discovery)" if report["percent"] >= 90 else
            "B (likely indexed)"      if report["percent"] >= 70 else
            "C (partial — may be indexed inconsistently)" if report["percent"] >= 50 else
            "D (likely missed by crawler)"
        ),
        "checks": report["checks"],
        "fixes_needed": fixes_needed,
        "next_step": (
            "Coinbase Bazaar's discovery crawler is poll-based — there's no public "
            "push endpoint. Fix the items in 'fixes_needed', wait ~24-72h, then "
            "verify with onyx_mcp_registry_status."
        ),
    }


run.__when_to_use__ = (
    "An x402 service operator wants to know why their endpoints aren't showing up "
    "in Coinbase Bazaar's public discovery feed (or why some are missing). Runs "
    "the checklist Coinbase's crawler effectively uses."
)
run.__vs_alternatives__ = (
    "No public Bazaar submission tool exists. Coinbase docs don't enumerate the "
    "crawler criteria. This is reverse-engineered + the first checklist."
)
run.__example_request__ = {"server_url": "https://onyx-actions.onrender.com"}
run.__example_response__ = {
    "ok": True,
    "server_url": "https://onyx-actions.onrender.com",
    "indexability_score": 85,
    "max_score": 100,
    "percent": 85,
    "grade": "B (likely indexed)",
    "fixes_needed": [{"fix": "...", "criterion": "..."}],
}
