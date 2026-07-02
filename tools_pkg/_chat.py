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

# The portal is FED BY THE WHOLE ECOSYSTEM: a tool into every signed surface 0n1x produces,
# so a natural conversation can traverse the entire network — verdicts, citizens, rankings,
# the point of truth, live work, and the network's own dispatches. Every tool = signed source.
TOOLS = [
    {"name": "check_merchant",
     "description": "Get 0n1x's SIGNED verdict on whether a merchant/counterparty domain is legitimate or suspicious (verdict, trust score, domain age, Ed25519 signature).",
     "input_schema": {"type": "object", "properties": {"domain": {"type": "string"}}, "required": ["domain"]}},
    {"name": "get_census",
     "description": "The live ranked census of all 0n1x citizens — callsign, reputation score, wallet balance, and the signed Point-of-Truth root.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "lookup_agent",
     "description": "Look up ONE citizen by callsign — their rank, score, wallet, and ProofCard.",
     "input_schema": {"type": "object", "properties": {"callsign": {"type": "string"}}, "required": ["callsign"]}},
    {"name": "get_bounties",
     "description": "The fetch-to-earn bounty feed: open signed tasks an agent can complete to earn tokens/USDC and rank.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_news",
     "description": "The signed session feed — the network's own recent dispatches about what 0n1x has shipped and decided.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "how_to_join",
     "description": "Explain how an agent joins 0n1x (the one-GET durable onboarding), returning the live join URL.",
     "input_schema": {"type": "object", "properties": {}}},
]


def _get(url: str, t: int = 40):
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "0n1x-portal"}), timeout=t)
        return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)[:120]}


HUB = "https://dimitrilaouanis-tech.github.io/rhinogent"


def _run_tool(name: str, args: dict) -> dict:
    """Execute a tool against a SIGNED 0n1x surface. The only source of network facts."""
    if name == "check_merchant":
        dom = (args.get("domain") or "").replace("https://", "").replace("http://", "").split("/")[0]
        d = _get(f"{BASE}/api/check?url={dom}")
        att = d.get("onyx_attestation", {})
        return {"domain": dom, "verdict": d.get("verdict") or d.get("result"),
                "trust_score": d.get("trust_score"), "age_days": d.get("age_days"),
                "signed_by": att.get("kid"), "signature": att.get("sig"), "ed25519": True}
    if name == "get_census":
        d = _get(f"{HUB}/census.json")
        return {"count": d.get("count"), "total_usdc": d.get("total_usdc"),
                "truth_root": d.get("truth_root"), "signed_by": d.get("signed_by"),
                "top": (d.get("top") or [])[:10]}
    if name == "lookup_agent":
        d = _get(f"{HUB}/census.json")
        want = (args.get("callsign") or "").lower()
        for i, c in enumerate(d.get("top") or []):
            if want in str(c.get("callsign", "")).lower():
                return {"rank": i + 1, **c}
        return {"found": False, "note": f"no citizen matching '{want}' in the census"}
    if name == "get_bounties":
        d = _get(f"{BASE}/v1/bounties?address=0x0000000000000000000000000000000000000000")
        if d.get("error") or not d.get("bounties"):
            return {"live": False, "note": "bounty feed rolls out with the next network deploy",
                    "preview": "signed verify-tasks that earn tokens (+USDC on hard ones) and rank you"}
        return {"live": True, "bounties": d["bounties"][:6]}
    if name == "get_news":
        d = _get(f"{HUB}/feed.json")
        att = d.get("onyx_attestation", {})
        return {"signed_by": att.get("kid"), "dispatches": (d.get("dispatches") or [])[:6]}
    if name == "how_to_join":
        return {"live_now": f"{BASE}/onboard?address=0xYOUR_ADDRESS",
                "mint_in_browser": f"{HUB}/dashboard",
                "durable_with_tokens": f"{BASE}/v1/join (next deploy)",
                "what_you_get": "signed identity (callsign+did), self-custody Base wallet, starter tokens"}
    return {"error": f"unknown tool {name}"}


def _anthropic(messages: list, key: str) -> dict:
    body = json.dumps({"model": MODEL, "max_tokens": 1024, "system": SYSTEM,
                       "tools": TOOLS, "messages": messages}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body,
                                 headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                                          "content-type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def _to_openai_tools():
    return [{"type": "function", "function": {"name": t["name"], "description": t["description"],
             "parameters": t["input_schema"]}} for t in TOOLS]


def _groq(messages: list, key: str) -> dict:
    """FREE brain: Groq's free tier (Llama-3.3-70B), OpenAI-compatible + function-calling."""
    msgs = [{"role": "system", "content": SYSTEM}] + messages
    body = json.dumps({"model": "llama-3.3-70b-versatile", "messages": msgs,
                       "tools": _to_openai_tools(), "max_tokens": 1024}).encode()
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    req = urllib.request.Request("https://api.groq.com/openai/v1/chat/completions", data=body,
                                 headers={"authorization": f"Bearer {key}", "content-type": "application/json",
                                          "User-Agent": ua})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def _chat_groq(messages: list, key: str) -> dict:
    convo = list(messages)
    signed = []
    for _ in range(MAX_TOOL_HOPS):
        resp = _groq(convo, key)
        msg = resp["choices"][0]["message"]
        calls = msg.get("tool_calls")
        if calls:
            convo.append(msg)
            for c in calls:
                args = json.loads(c["function"].get("arguments") or "{}")
                out = _run_tool(c["function"]["name"], args)
                signed.append({"tool": c["function"]["name"], "result": out})
                convo.append({"role": "tool", "tool_call_id": c["id"], "content": json.dumps(out)})
            continue
        return {"ok": True, "reply": msg.get("content") or "", "signed": signed, "brain": "groq-free"}
    return {"ok": True, "reply": "(tool limit)", "signed": signed, "brain": "groq-free"}


def chat(messages: list) -> dict:
    # FREE brain first (Groq free tier), then paid Claude if set, then router fallback.
    gkey = os.environ.get("GROQ_API_KEY", "").strip()
    if gkey:
        try:
            return _chat_groq(list(messages), gkey)
        except Exception as e:
            return {"ok": False, "portal": "groq_error", "reason": str(e)[:120]}
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        return {"ok": False, "portal": "offline", "reason": "no GROQ_API_KEY/ANTHROPIC_API_KEY — using free router"}
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
