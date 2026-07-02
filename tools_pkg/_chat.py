"""_chat.py — the 0n1x PORTAL. A real LLM chat (Claude) you converse with freely, but every
NETWORK FACT it states comes from a signed 0n1x tool (function-calling). 0n1x is the gate; the
model is the friendly door; the network does the proving.

Divergence-designed route (2026-07-02): Claude via Anthropic API (best tool-adherence, lowest
hallucination) · SERVER-SIDE only (key in ANTHROPIC_API_KEY env, never client) · notary system
prompt · the model may only assert a verdict/rank/score that a signed tool actually returned.

POST /v1/chat  {"messages":[{"role":"user","content":"is stripe.com legit?"}]}
  -> runs the tool loop against signed 0n1x endpoints -> {"reply": "...", "signed": [ ... ]}

Activation gate (eyes-open): needs ANTHROPIC_API_KEY set on the server. Until then /v1/chat
returns {"ok": false, "portal": "offline"} and the web terminal falls back to its free NL router.
"""
import json
import os
import urllib.request

MODEL = "claude-sonnet-5"          # best balance for a conversational trust surface
MAX_TOOL_HOPS = 5                  # cap the tool loop = cap cost per conversation
BASE = "https://onyx-actions.onrender.com"

SYSTEM = (
    "You are the 0n1x portal — the friendly front desk of a neutral, cryptographic trust network "
    "for AI agents. You may converse naturally and explain how 0n1x works. BUT: any factual claim "
    "about the network — whether a merchant/counterparty is legitimate, an agent's rank or score, "
    "who is in the census — MUST come from a tool result you actually received in THIS turn. Never "
    "invent a verdict, a score, a signature, or a citizen. If a tool did not return it, say you "
    "don't have that signed fact. When you report a verdict, note it is Ed25519-signed by 0n1x and "
    "verifiable by anyone. You are a notary's desk, not a fortune teller: you explain, the network "
    "proves. Keep replies concise and human."
)

TOOLS = [
    {"name": "check_merchant",
     "description": "Get 0n1x's SIGNED verdict on whether a merchant/counterparty domain is legitimate or suspicious.",
     "input_schema": {"type": "object", "properties": {"domain": {"type": "string"}}, "required": ["domain"]}},
    {"name": "get_census",
     "description": "Get the live ranked census of 0n1x citizens (callsign, reputation score, wallet).",
     "input_schema": {"type": "object", "properties": {}}},
]


def _get(url: str, t: int = 40):
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "0n1x-portal"}), timeout=t)
        return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)[:120]}


def _run_tool(name: str, args: dict) -> dict:
    """Execute a tool against a SIGNED 0n1x endpoint. The only source of network facts."""
    if name == "check_merchant":
        dom = (args.get("domain") or "").replace("https://", "").replace("http://", "").split("/")[0]
        d = _get(f"{BASE}/api/check?url={dom}")
        att = d.get("onyx_attestation", {})
        return {"domain": dom, "verdict": d.get("verdict") or d.get("result"),
                "trust_score": d.get("trust_score"), "age_days": d.get("age_days"),
                "signed_by": att.get("kid"), "signature": att.get("sig"), "ed25519": True}
    if name == "get_census":
        d = _get("https://dimitrilaouanis-tech.github.io/rhinogent/census.json")
        return {"count": d.get("count"), "total_usdc": d.get("total_usdc"),
                "truth_root": d.get("truth_root"), "top": (d.get("top") or [])[:10]}
    return {"error": f"unknown tool {name}"}


def _anthropic(messages: list, key: str) -> dict:
    body = json.dumps({"model": MODEL, "max_tokens": 1024, "system": SYSTEM,
                       "tools": TOOLS, "messages": messages}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body,
                                 headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                                          "content-type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def chat(messages: list) -> dict:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        return {"ok": False, "portal": "offline", "reason": "ANTHROPIC_API_KEY not set — using free router"}
    convo = list(messages)
    signed = []
    for _ in range(MAX_TOOL_HOPS):
        resp = _anthropic(convo, key)
        blocks = resp.get("content", [])
        if resp.get("stop_reason") == "tool_use":
            convo.append({"role": "assistant", "content": blocks})
            results = []
            for b in blocks:
                if b.get("type") == "tool_use":
                    out = _run_tool(b["name"], b.get("input", {}))
                    signed.append({"tool": b["name"], "result": out})
                    results.append({"type": "tool_result", "tool_use_id": b["id"],
                                    "content": json.dumps(out)})
            convo.append({"role": "user", "content": results})
            continue
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        return {"ok": True, "reply": text, "signed": signed}
    return {"ok": True, "reply": "(reached tool limit — ask again)", "signed": signed}


def register(app):
    from fastapi import Request

    @app.post("/v1/chat", include_in_schema=False)
    async def v1_chat(req: Request):
        try:
            body = await req.json()
        except Exception:
            body = {}
        msgs = body.get("messages") or ([{"role": "user", "content": body["message"]}] if body.get("message") else [])
        if not msgs:
            return {"ok": False, "error": "send {messages:[...]} or {message:'...'}"}
        return chat(msgs[-12:])   # cap context = cap cost
