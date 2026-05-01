"""Type text into a focused field on the current CDP page."""
from __future__ import annotations

import time
from . import _cdp_client as cdp

NAME = "onyx_browser_type"
PRICE_USDC = "0.002"
TIER = "metered"
DESCRIPTION = (
    "Find an input/textarea/select on the current CDP page by its name, id, "
    "or visible label, set its value via the React-safe native setter, and "
    "fire input + change events so frameworks like React/Vue see the "
    "update. Use after onyx_browser_navigate when an agent fills a form. "
    "Returns the field selector matched and the final value. Demo mode "
    "returns synthetic OK."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "selector": {"type": "string",
                     "description": "Name, id (#foo), CSS selector, or visible label substring"},
        "value": {"type": "string", "description": "Text to enter"},
    },
    "required": ["selector", "value"],
}


def run(selector: str, value: str, **_: object) -> dict:
    sel = (selector or "").strip()
    if not sel:
        raise ValueError("selector required")
    started = time.time()
    if cdp.demo_mode():
        return {"selector": sel, "value": value, "demo": True,
                "elapsed_ms": int((time.time() - started) * 1000)}
    expr = (
        "(function(){"
        f"var s={repr(sel)};var v={repr(value)};"
        "var el=document.querySelector(s);"
        "if(!el){"
        "  var inps=Array.from(document.querySelectorAll('input,textarea,select')).filter(e=>e.offsetParent!==null);"
        "  el=inps.find(e=>e.name===s||e.id===s||(e.placeholder||'').toLowerCase().includes(s.toLowerCase()));"
        "}"
        "if(!el)return JSON.stringify({matched:false});"
        "var proto=el.tagName==='TEXTAREA'?window.HTMLTextAreaElement.prototype:window.HTMLInputElement.prototype;"
        "var setter=Object.getOwnPropertyDescriptor(proto,'value').set;"
        "el.focus();setter.call(el,v);"
        "el.dispatchEvent(new Event('input',{bubbles:true}));"
        "el.dispatchEvent(new Event('change',{bubbles:true}));"
        "return JSON.stringify({matched:true,tag:el.tagName,name:el.name||'',id:el.id||'',value:el.value.slice(0,80)});"
        "})()"
    )
    res = cdp.cdp_call(None, "Runtime.evaluate",
                       {"expression": expr, "returnByValue": True})
    import json as _j
    d = _j.loads(res.get("result", {}).get("value") or "{}")
    return {
        "matched": bool(d.get("matched")),
        "tag": d.get("tag"),
        "name": d.get("name"),
        "id": d.get("id"),
        "value": d.get("value"),
        "elapsed_ms": int((time.time() - started) * 1000),
    }
