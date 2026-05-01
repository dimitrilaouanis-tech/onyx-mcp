"""Run JavaScript on the current CDP page and return the value."""
from __future__ import annotations

import time
from . import _cdp_client as cdp

NAME = "onyx_browser_eval"
PRICE_USDC = "0.004"
TIER = "metered"
DESCRIPTION = (
    "Evaluate a JavaScript expression on the current CDP-controlled Chrome "
    "page and return the result by value. Use as a power-tool when the "
    "specific click/extract/type tools don't fit — pull deeply nested "
    "DOM data, dispatch synthetic events, read computed styles. Demo mode "
    "echoes the expression length without executing."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "expression": {"type": "string",
                       "description": "JavaScript expression. Last value is returned."},
        "await_promise": {"type": "boolean", "default": False,
                          "description": "If the expression returns a Promise, wait for it."},
    },
    "required": ["expression"],
}


def run(expression: str, await_promise: bool = False, **_: object) -> dict:
    if not expression:
        raise ValueError("expression required")
    started = time.time()
    if cdp.demo_mode():
        return {"demo": True, "expression_length": len(expression),
                "value": None,
                "note": "ONYX_DEMO_MODE=1. Self-host with ONYX_CDP_URL for real eval.",
                "elapsed_ms": int((time.time() - started) * 1000)}
    res = cdp.cdp_call(None, "Runtime.evaluate", {
        "expression": expression,
        "returnByValue": True,
        "awaitPromise": bool(await_promise),
    })
    val = res.get("result", {}).get("value")
    err = res.get("exceptionDetails")
    return {
        "value": val,
        "exception": (err.get("text") if err else None),
        "elapsed_ms": int((time.time() - started) * 1000),
    }
