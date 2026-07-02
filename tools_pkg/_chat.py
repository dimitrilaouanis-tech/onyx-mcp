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


# OUR OWN API GATEWAY — pool multiple FREE providers, each with independent rate limits, and
# fail over automatically. Combined free capacity blows past any single 20-30 RPM cap, $0 cost.
# All are OpenAI-compatible + support function-calling. Add a key (env or gitignored file) to
# light a provider up; the gateway rotates in this order until one answers.
_HERE = os.path.dirname(os.path.abspath(__file__))
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

# Free tiers first ($0 — cover the free starter credits). DeepSeek V4 last: paid but ~$0.0006/
# question, so a metered credit (~$0.01) is a ~16x markup — the resell margin. deepseek-chat is
# V4-Flash-priced ($0.14/$0.28 per M); note DeepSeek deprecates 'deepseek-chat' 2026-07-24 —
# bump to the current V4 model id then.
PROVIDERS = [
    {"name": "groq",     "base": "https://api.groq.com/openai/v1",                    "model": "llama-3.3-70b-versatile", "env": "GROQ_API_KEY",     "file": ".groq_key"},
    {"name": "cerebras", "base": "https://api.cerebras.ai/v1",                        "model": "llama-3.3-70b",           "env": "CEREBRAS_API_KEY", "file": ".cerebras_key"},
    {"name": "gemini",   "base": "https://generativelanguage.googleapis.com/v1beta/openai", "model": "gemini-2.0-flash",  "env": "GEMINI_API_KEY",   "file": ".gemini_key"},
    {"name": "deepseek", "base": "https://api.deepseek.com/v1",                       "model": "deepseek-chat",           "env": "DEEPSEEK_API_KEY", "file": ".deepseek_key"},
]


def _key_for(p: dict) -> str:
    k = os.environ.get(p["env"], "").strip()
    if not k:
        f = os.path.join(_HERE, p["file"])
        if os.path.exists(f):
            k = open(f).read().strip()
    return k


def _call_openai_compat(base: str, key: str, model: str, messages: list) -> dict:
    body = json.dumps({"model": model, "messages": messages,
                       "tools": _to_openai_tools(), "max_tokens": 1024}).encode()
    req = urllib.request.Request(base.rstrip("/") + "/chat/completions", data=body,
                                 headers={"authorization": f"Bearer {key}",
                                          "content-type": "application/json", "User-Agent": _UA})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def _chat_via(p: dict, key: str, messages: list) -> dict:
    convo = [{"role": "system", "content": SYSTEM}] + list(messages)
    signed = []
    for _ in range(MAX_TOOL_HOPS):
        resp = _call_openai_compat(p["base"], key, p["model"], convo)
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
        return {"ok": True, "reply": msg.get("content") or "", "signed": signed, "brain": p["name"]}
    return {"ok": True, "reply": "(tool limit)", "signed": signed, "brain": p["name"]}


import hashlib


def _cache_key(messages: list) -> str:
    """Cache on the last user message (normalized) — repeat questions never re-hit a model."""
    last = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last = str(m.get("content", "")).strip().lower()
            break
    return hashlib.sha256(last.encode()).hexdigest()[:24] if last else ""


def _cache_get(key: str):
    if not key:
        return None
    try:
        from tools_pkg import _store
        return (_store.get("chat_cache") or {}).get(key)
    except Exception:
        return None


# tools whose results are LIVE SIGNED FACTS — never cache these (a stale cached verdict is a
# trust failure: a domain can flip suspicious while we serve an old signed "legit"). The
# divergence audit flagged this as the coupled correctness/trust risk. Fresh, always.
_NEVER_CACHE_TOOLS = {"check_merchant", "get_census", "lookup_agent", "get_bounties"}


def _cache_put(key: str, result: dict):
    if not key or not result.get("ok"):
        return
    # CORRECTNESS GUARD: if the answer used any live signed-fact tool, do NOT cache it —
    # only conversational/explanatory replies (about, how-to-join, news-style) are cacheable.
    if any(s.get("tool") in _NEVER_CACHE_TOOLS for s in result.get("signed", [])):
        return
    try:
        from tools_pkg import _store
        c = _store.get("chat_cache") or {}
        c[key] = {"reply": result.get("reply"), "signed": result.get("signed", []), "cached": True}
        if len(c) > 5000:
            c = dict(list(c.items())[-4000:])
        _store.put("chat_cache", c)
    except Exception:
        pass


# --- GUARDRAILS: never let anyone drain the API budget or spam the model ---
DAILY_LLM_CAP = 2000       # max model calls/day network-wide (~$1.20/day at DeepSeek rates)
PER_ADDR_HOURLY = 30       # max model calls per agent per hour (anti-drain)
import time as _time


def _guard(address: str):
    """Count MODEL calls only (cache hits are free). Enforce a daily global cap + per-agent
    hourly rate so a single actor can't burn the credits. Returns (allowed, reason)."""
    try:
        from tools_pkg import _store
        day, hour = int(_time.time() // 86400), int(_time.time() // 3600)
        g = _store.get("chat_guard") or {}
        dkey = f"d{day}"
        if g.get(dkey, 0) >= DAILY_LLM_CAP:
            return False, "daily network limit reached — the free tier is protected; try again tomorrow"
        akey = f"h{hour}:{address.lower()}" if address else None
        if akey and g.get(akey, 0) >= PER_ADDR_HOURLY:
            return False, "you're going too fast — give it a minute"
        g[dkey] = g.get(dkey, 0) + 1
        if akey:
            g[akey] = g.get(akey, 0) + 1
        if len(g) > 4000:                      # prune stale hourly keys
            g = {k: v for k, v in g.items() if k.startswith(f"d{day}") or k.startswith(f"h{hour}")}
        _store.put("chat_guard", g)
        return True, ""
    except Exception:
        return True, ""                        # never hard-fail the chat on a guard error


def chat(messages: list, address: str = "") -> dict:
    """The gateway: cache first (free), then GUARD the budget, then free providers, then DeepSeek."""
    # LAYER 2 — answer cache: already answered? serve FREE, never touch a model (no guard needed).
    ck = _cache_key(messages)
    hit = _cache_get(ck)
    if hit:
        return {"ok": True, "reply": hit["reply"], "signed": hit.get("signed", []),
                "brain": "cache", "cached": True}
    # GUARDRAIL — cache missed, so this WILL hit a paid/rate-limited model. Check the budget first.
    ok, reason = _guard(address)
    if not ok:
        return {"ok": True, "brain": "guard", "reply": reason,
                "note": "signed checks (check/census) stay free — only AI chat is rate-limited"}
    errors = []
    for p in PROVIDERS:
        key = _key_for(p)
        if not key:
            continue
        try:
            result = _chat_via(p, key, messages)
            _cache_put(ck, result)                          # network learns this answer -> free next time
            return result
        except Exception as e:
            errors.append(f"{p['name']}:{str(e)[:50]}")   # 429/limit/error -> next provider
            continue
    # optional paid Claude if a key is set
    akey = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if akey:
        try:
            convo, signed = list(messages), []
            for _ in range(MAX_TOOL_HOPS):
                resp = _anthropic(convo, akey)
                blocks = resp.get("content", [])
                if resp.get("stop_reason") == "tool_use":
                    convo.append({"role": "assistant", "content": blocks})
                    results = []
                    for b in blocks:
                        if b.get("type") == "tool_use":
                            out = _run_tool(b["name"], b.get("input", {}))
                            signed.append({"tool": b["name"], "result": out})
                            results.append({"type": "tool_result", "tool_use_id": b["id"], "content": json.dumps(out)})
                    convo.append({"role": "user", "content": results})
                    continue
                return {"ok": True, "reply": "".join(b.get("text", "") for b in blocks if b.get("type") == "text"),
                        "signed": signed, "brain": "claude"}
        except Exception as e:
            errors.append(f"claude:{str(e)[:50]}")
    return {"ok": False, "portal": "offline",
            "reason": "no free provider available — add a GROQ/CEREBRAS/GEMINI key" + (f" ({'; '.join(errors)})" if errors else "")}


# --- CREDIT METERING: hard LLM questions cost a credit; common signed lookups stay free ---
# Only HARD questions reach /v1/chat (the client router answers the common ones for free), so
# every call here = one billable LLM turn. New agents get FREE_CHAT_CREDITS to start; after that
# they top up. This makes the expensive layer self-funding. Balances persist via _store (Neon).
FREE_CHAT_CREDITS = 8


def _credits() -> dict:
    try:
        from tools_pkg import _store
        return _store.get("chat_credits") or {}
    except Exception:
        return {}


def _charge(address: str):
    """Returns (allowed, remaining, is_new). Grants a free starter on first use, then burns 1."""
    if not address:
        return True, None, False           # anonymous allowed (soft); identity gets metered
    a = address.lower()
    from tools_pkg import _store
    c = _store.get("chat_credits") or {}
    is_new = a not in c
    if is_new:
        c[a] = FREE_CHAT_CREDITS
    if c[a] <= 0:
        return False, 0, False
    c[a] -= 1
    _store.put("chat_credits", c)
    return True, c[a], is_new


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
        # meter the hard question
        ok, remaining, is_new = _charge(body.get("address", ""))
        if not ok:
            return {"ok": False, "out_of_credits": True,
                    "reply": ("You've used your free AI questions 🤍 — top up credits to keep asking "
                              "hard questions. (Quick checks like \"check stripe.com\", the census, and "
                              "\"what's new\" stay free forever.)"),
                    "topup": f"{BASE}/v1/join"}
        result = chat(msgs[-12:], address=body.get("address", ""))   # cap context + guard budget
        if remaining is not None:
            result["credits_left"] = remaining
            if is_new:
                result["welcome_credits"] = FREE_CHAT_CREDITS
        return result
