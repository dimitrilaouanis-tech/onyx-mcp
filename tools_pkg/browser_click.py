"""Click an element on the current CDP page by its visible text."""
from __future__ import annotations

import time
from . import _cdp_client as cdp

NAME = "onyx_browser_click"
PRICE_USDC = "0.003"
TIER = "metered"
DESCRIPTION = (
    "Click the first visible button or link whose text matches the query "
    "(case-insensitive substring match). Returns whether a match was found "
    "and the matched element's text + href. Use after onyx_browser_extract "
    "to act on what the page advertised. Demo mode returns synthetic OK."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string", "description": "Substring of the element's visible text"},
    },
    "required": ["text"],
}


def run(text: str, **_: object) -> dict:
    needle = (text or "").strip()
    if not needle:
        raise ValueError("text required")
    started = time.time()
    if cdp.demo_mode():
        return {
            "matched": True, "matched_text": needle,
            "matched_href": None,
            "demo": True,
            "elapsed_ms": int((time.time() - started) * 1000),
        }
    expr = (
        "(function(){"
        f"var n={repr(needle.lower())};"
        "var els=Array.from(document.querySelectorAll('button,a')).filter(e=>e.offsetParent!==null);"
        "var m=els.find(e=>(e.innerText||'').toLowerCase().includes(n));"
        "if(!m)return JSON.stringify({matched:false});"
        "m.click();"
        "return JSON.stringify({matched:true,text:(m.innerText||'').slice(0,80),href:m.href||null});"
        "})()"
    )
    res = cdp.cdp_call(None, "Runtime.evaluate",
                       {"expression": expr, "returnByValue": True})
    import json as _j
    d = _j.loads(res.get("result", {}).get("value") or "{}")
    return {
        "matched": bool(d.get("matched")),
        "matched_text": d.get("text"),
        "matched_href": d.get("href"),
        "elapsed_ms": int((time.time() - started) * 1000),
    }
