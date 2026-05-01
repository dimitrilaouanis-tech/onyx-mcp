"""Tiny synchronous CDP client used by the browser_* tools.

Connects to an existing Chrome DevTools Protocol endpoint specified by
ONYX_CDP_URL (default http://127.0.0.1:9222). Cloud deployments rely on
ONYX_DEMO_MODE=1 to short-circuit since Render free tier has no Chrome;
self-hosted deployments set their own CDP URL.

Single underscore module — not a tool, not auto-discovered.
"""
from __future__ import annotations

import json
import os
from typing import Any

import httpx


def cdp_base_url() -> str:
    return os.environ.get("ONYX_CDP_URL", "http://127.0.0.1:9222").rstrip("/")


def demo_mode() -> bool:
    return os.environ.get("ONYX_DEMO_MODE", "1") == "1"


def list_tabs(timeout: float = 4.0) -> list[dict]:
    r = httpx.get(f"{cdp_base_url()}/json", timeout=timeout)
    r.raise_for_status()
    data = r.json()
    return [t for t in data if t.get("type") == "page"]


def first_tab() -> dict:
    tabs = list_tabs()
    if not tabs:
        raise RuntimeError("No CDP page targets available")
    return tabs[0]


def cdp_call(target_id: str | None, method: str, params: dict | None = None,
             timeout: float = 8.0) -> Any:
    """One-shot WebSocket call. Lightweight, no session reuse.

    For tools that need a few calls in sequence, just call this multiple times.
    """
    try:
        from websocket import create_connection
    except ImportError as e:
        raise RuntimeError(
            "websocket-client not installed; pip install websocket-client"
        ) from e
    if target_id is None:
        target_id = first_tab().get("id")
    ws_url = f"ws://{cdp_base_url().split('//', 1)[1]}/devtools/page/{target_id}"
    ws = create_connection(ws_url, timeout=timeout)
    try:
        ws.send(json.dumps({"id": 1, "method": method, "params": params or {}}))
        while True:
            raw = ws.recv()
            msg = json.loads(raw)
            if msg.get("id") == 1:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})
    finally:
        ws.close()
