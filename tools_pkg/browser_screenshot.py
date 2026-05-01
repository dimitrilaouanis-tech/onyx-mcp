"""Capture a base64-encoded screenshot of the current CDP page."""
from __future__ import annotations

import time
from . import _cdp_client as cdp

NAME = "onyx_browser_screenshot"
PRICE_USDC = "0.008"
TIER = "metered"
DESCRIPTION = (
    "Capture a PNG screenshot of the current CDP-controlled Chrome page "
    "and return it as base64. Use to feed a vision-LLM (Claude / GPT-4V) "
    "for screen-understanding agents, or to archive an action's visual "
    "result. Returns also the page title, URL, and viewport dimensions. "
    "Cap of 1MB returned. Demo mode returns a synthetic 1×1 PNG; "
    "self-host with ONYX_CDP_URL for real captures."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "format": {"type": "string", "enum": ["png", "jpeg"], "default": "png"},
        "full_page": {"type": "boolean", "default": False,
                      "description": "Capture full scrollable page or just viewport"},
    },
}

# 1×1 transparent PNG
_DEMO_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8"
    "AAAAASUVORK5CYII="
)


def run(format: str = "png", full_page: bool = False, **_: object) -> dict:
    started = time.time()
    if cdp.demo_mode():
        return {
            "format": format, "full_page": full_page,
            "image_b64": _DEMO_PNG,
            "title": "Demo Page",
            "url": "https://example.com",
            "viewport": {"width": 1280, "height": 720},
            "demo": True,
            "elapsed_ms": int((time.time() - started) * 1000),
        }
    res = cdp.cdp_call(None, "Page.captureScreenshot",
                       {"format": format, "captureBeyondViewport": full_page})
    image_b64 = res.get("data", "")
    info = cdp.cdp_call(None, "Runtime.evaluate", {
        "expression": "JSON.stringify({u: location.href, t: document.title, w: innerWidth, h: innerHeight})",
        "returnByValue": True,
    })
    import json as _j
    meta = _j.loads(info.get("result", {}).get("value") or "{}")
    return {
        "format": format, "full_page": full_page,
        "image_b64": image_b64[:1_400_000],
        "image_bytes_b64": len(image_b64),
        "title": meta.get("t"),
        "url": meta.get("u"),
        "viewport": {"width": meta.get("w"), "height": meta.get("h")},
        "elapsed_ms": int((time.time() - started) * 1000),
    }
