"""Read the current CDP page — text + clickable element summary."""
from __future__ import annotations

import time
from . import _cdp_client as cdp

NAME = "onyx_browser_extract"
PRICE_USDC = "0.003"
TIER = "metered"
DESCRIPTION = (
    "Read the current CDP-controlled Chrome page and return the visible "
    "text content plus a structured summary of clickable elements: "
    "buttons, links (with hrefs), inputs (with names/placeholders/types). "
    "Use when an agent needs to plan its next action — list what's on the "
    "page without screenshotting + vision-modeling. Cheap, structured, "
    "deterministic. Demo mode returns a plausible synthetic page summary."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "max_chars": {"type": "integer", "default": 4000,
                      "description": "Cap on returned text length (max 80000)"},
    },
}


def run(max_chars: int = 4000, **_: object) -> dict:
    cap = max(100, min(int(max_chars), 80000))
    started = time.time()
    if cdp.demo_mode():
        return {
            "url": "https://example.com",
            "title": "Example Domain",
            "text": "Example Domain. This domain is for use in illustrative examples in documents.",
            "buttons": [],
            "links": [{"text": "More information…", "href": "https://www.iana.org/help/example-domains"}],
            "inputs": [],
            "demo": True,
            "elapsed_ms": int((time.time() - started) * 1000),
        }
    expr = (
        "(function(){"
        f"var maxChars={cap};"
        "var text=(document.body.innerText||'').slice(0,maxChars);"
        "var btns=Array.from(document.querySelectorAll('button')).filter(e=>e.offsetParent!==null).slice(0,30).map(b=>({text:(b.innerText||'').slice(0,80),disabled:b.disabled}));"
        "var lks=Array.from(document.querySelectorAll('a')).filter(e=>e.offsetParent!==null).slice(0,40).map(a=>({text:(a.innerText||'').slice(0,80),href:a.href||''}));"
        "var inps=Array.from(document.querySelectorAll('input,textarea,select')).filter(e=>e.offsetParent!==null).slice(0,30).map(i=>({tag:i.tagName,type:i.type||'',name:i.name||'',placeholder:i.placeholder||''}));"
        "return JSON.stringify({u:location.href,t:document.title,text:text,buttons:btns,links:lks,inputs:inps});"
        "})()"
    )
    res = cdp.cdp_call(None, "Runtime.evaluate", {
        "expression": expr, "returnByValue": True,
    })
    import json as _j
    s = res.get("result", {}).get("value") or "{}"
    d = _j.loads(s)
    return {
        "url": d.get("u"),
        "title": d.get("t"),
        "text": d.get("text"),
        "buttons": d.get("buttons") or [],
        "links": d.get("links") or [],
        "inputs": d.get("inputs") or [],
        "elapsed_ms": int((time.time() - started) * 1000),
    }
