"""Multi-tool agent workflow under ONE x402 budget cap.

An agent declares: 'I want to call these N tools, total spend ≤ $X'. This
tool synthesizes a single bundled-payment challenge across all of them,
returns the unified cost preview, dependency graph, and per-step pre-flight
status. The agent signs ONE EIP-3009 authorization for the bundle cap; the
gateway charges each step against the remaining budget.

v1 returns the analysis card (free). v2 (paid sibling) will actually broker
the multi-step settlement. Lane: agent-side budget fragmentation is the #1
operational pain at scale.
"""
from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request

NAME = "onyx_skill_bundle"
PRICE_USDC = "0"
TIER = "free"
DESCRIPTION = (
    "Plan a multi-tool agent workflow under one x402 budget cap. Given a list "
    "of tool endpoints (any x402 server) and a max-spend cap, returns: "
    "unified cost preview (sum of declared prices), per-step prerequisites, "
    "estimated total settlement count, and whether the bundle fits the cap. "
    "v1 = analysis card (free); v2 = actually brokers settlement."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "tools": {
            "type": "array",
            "description": "List of tools to bundle. Each: {endpoint_url, description, depends_on (optional)}.",
            "items": {
                "type": "object",
                "properties": {
                    "endpoint_url": {"type": "string"},
                    "description": {"type": "string"},
                    "depends_on": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["endpoint_url"],
            },
        },
        "max_spend_usdc": {
            "type": "number",
            "description": "Bundle budget cap in USDC. Bundle is rejected if sum(prices) > cap.",
        },
    },
    "required": ["tools", "max_spend_usdc"],
}


def _probe_price(endpoint_url: str, timeout: float = 6.0) -> tuple[float | None, str | None]:
    """Try to fetch the introspection card for a paid endpoint to read its price.
    Returns (price_usdc, error)."""
    try:
        req = urllib.request.Request(
            endpoint_url,
            headers={"User-Agent": "onyx-skill-bundle/1.0", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(8192).decode("utf-8", "replace")
            data = json.loads(body)
            # Introspection card: price_usdc as string
            if "price_usdc" in data:
                try:
                    return float(str(data["price_usdc"])), None
                except ValueError:
                    pass
            return None, "no price_usdc field in introspection"
    except urllib.error.HTTPError as e:
        # 402 challenge — decode and extract maxAmountRequired
        if e.code == 402:
            body = e.read(8192) if e else b""
            ctype = e.headers.get("Content-Type", "") if e.headers else ""
            pr_header = e.headers.get("payment-required") if e.headers else None
            if pr_header:
                try:
                    import base64
                    challenge = json.loads(base64.b64decode(pr_header).decode("utf-8"))
                    accepts = (challenge.get("accepts") or [{}])[0]
                    amt = int(accepts.get("amount") or accepts.get("maxAmountRequired") or 0)
                    return amt / 1_000_000, None
                except Exception:
                    pass
            return None, f"HTTP 402 but no parseable price"
        return None, f"HTTP {e.code}"
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as e:
        return None, str(e)[:120]


def _topo_sort(tools: list[dict]) -> tuple[list[int], list[str]]:
    """Return execution order respecting depends_on. Errors if cyclic."""
    n = len(tools)
    indeg = [0] * n
    deps: dict[int, list[int]] = {i: [] for i in range(n)}
    for i, t in enumerate(tools):
        for j in (t.get("depends_on") or []):
            if not isinstance(j, int) or j < 0 or j >= n:
                return [], [f"tool[{i}] depends_on invalid index {j}"]
            deps[j].append(i)
            indeg[i] += 1
    queue = [i for i in range(n) if indeg[i] == 0]
    order = []
    while queue:
        x = queue.pop(0)
        order.append(x)
        for y in deps[x]:
            indeg[y] -= 1
            if indeg[y] == 0:
                queue.append(y)
    if len(order) != n:
        return [], ["dependency cycle detected"]
    return order, []


def run(
    tools: list[dict],
    max_spend_usdc: float,
    **_: object,
) -> dict:
    if not isinstance(tools, list) or not tools:
        raise ValueError("tools must be a non-empty list")
    if not isinstance(max_spend_usdc, (int, float)) or max_spend_usdc < 0:
        raise ValueError("max_spend_usdc must be a non-negative number")
    if len(tools) > 50:
        raise ValueError("bundle size limit is 50 tools")

    order, errors = _topo_sort(tools)
    if errors:
        return {"ok": False, "errors": errors, "tools": tools}

    # Probe each tool's price
    steps = []
    total = 0.0
    unknown_count = 0
    for i, t in enumerate(tools):
        url = t.get("endpoint_url", "")
        if not url:
            return {"ok": False, "errors": [f"tool[{i}] missing endpoint_url"]}
        price, err = _probe_price(url)
        if price is None:
            unknown_count += 1
        else:
            total += price
        steps.append({
            "index": i,
            "endpoint_url": url,
            "description": t.get("description", ""),
            "depends_on": t.get("depends_on", []),
            "price_usdc": price,
            "probe_error": err,
        })

    headroom = max_spend_usdc - total
    fits = total <= max_spend_usdc and unknown_count == 0

    return {
        "ok": True,
        "tools_count": len(tools),
        "execution_order": order,
        "total_cost_usdc": round(total, 6),
        "max_spend_usdc": max_spend_usdc,
        "headroom_usdc": round(headroom, 6),
        "unknown_price_count": unknown_count,
        "fits_budget": fits,
        "verdict": (
            "BUNDLE APPROVED" if fits
            else "BUNDLE REJECTED: " + (
                f"exceeds cap by ${abs(headroom):.4f}" if total > max_spend_usdc
                else f"{unknown_count} tools had unknown price (probe failed)"
            )
        ),
        "steps": steps,
        "next_step": (
            "v1 returns analysis only. To execute: agent signs ONE EIP-3009 "
            "authorization for total_cost_usdc, posts X-PAYMENT to each step in "
            "execution_order. v2 of this tool (paid) will broker the bundle: "
            "sign once, gateway routes per step, returns aggregated receipt."
        ),
    }


run.__when_to_use__ = (
    "An agent wants to chain 3+ paid tool calls (e.g. captcha → email validate → "
    "DNS lookup → AML screen) under a single spend cap, instead of negotiating "
    "x402 payment for each call separately."
)
run.__vs_alternatives__ = (
    "No public multi-tool x402 bundler exists today. AAE (payment-skill) proposes "
    "spend-envelopes; AP2 discusses delegation. Neither ships. This tool is the "
    "first analyzer; v2 will be the first broker."
)
run.__example_request__ = {
    "tools": [
        {"endpoint_url": "https://onyx-actions.onrender.com/v1/onyx_base_token_risk_scan"},
        {"endpoint_url": "https://onyx-actions.onrender.com/v1/onyx_aml_screen", "depends_on": [0]},
    ],
    "max_spend_usdc": 0.50,
}
run.__example_response__ = {
    "ok": True,
    "tools_count": 2,
    "total_cost_usdc": 0.30,
    "max_spend_usdc": 0.50,
    "headroom_usdc": 0.20,
    "fits_budget": True,
    "verdict": "BUNDLE APPROVED",
    "execution_order": [0, 1],
}
