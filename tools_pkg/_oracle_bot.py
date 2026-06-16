"""@OnyxOracle — tag-to-verify bot. The Clanker conversion loop.

An agent/human tags @OnyxOracle with a token, contract, price, or merchant
claim; the bot replies with a SIGNED Onyx verdict in seconds. That reply is
screenshot-bait (spreads the spectacle) AND product onboarding (teaches /verify)
in one action — the views->users converter the rollout needs.

Intent routing is keyword/pattern based (no LLM in the trust path). Every
reply carries an Ed25519-signed verdict; the social text is just the wrapper.
Social-account wiring (Neynar/Farcaster, X API) plugs into `handle_mention`'s
output — this module produces the verdict + the post text; the transport layer
calls it.

Underscore-prefixed -> not an auto-discovered tool.
"""
from __future__ import annotations

import re
import time

from . import _onyx_sign

_ADDR = re.compile(r"0x[a-fA-F0-9]{40}")
_URL = re.compile(r"https?://[^\s]+")
_PRICE = re.compile(r"\bprice\b|\bworth\b|\bcost\b|\$[0-9]", re.I)
_BASE = "https://onyx-actions.onrender.com"


def _call_tool(name: str, **kwargs):
    """Best-effort call into a discovered tool module; never raises."""
    try:
        from . import discover
        mod = next((m for m in discover() if m.NAME == name), None)
        if mod is None:
            return None
        out = mod.run(**kwargs)
        return out
    except Exception as e:
        return {"_error": f"{type(e).__name__}: {str(e)[:120]}"}


def _classify(text: str) -> tuple[str, dict]:
    """Return (intent, args) — pure pattern routing, no model."""
    addr = _ADDR.search(text or "")
    if addr:
        return "contract", {"address": addr.group(0)}
    url = _URL.search(text or "")
    if url:
        return "merchant", {"url": url.group(0)}
    if _PRICE.search(text or ""):
        return "price", {"query": (text or "").strip()[:120]}
    return "generic", {"claim": (text or "").strip()[:200]}


def handle_mention(text: str, author: str = "anon", platform: str = "x",
                   now: int | None = None) -> dict:
    """Produce a signed verdict + a social-ready reply for one @OnyxOracle mention."""
    ts = int(now if now is not None else time.time())
    # Security gate first — inbound mention text is untrusted data, never commands.
    from . import _a2a_security
    security = _a2a_security.guard(text, author=author)
    intent, args = _classify(text or "")

    # Route to the matching live tool (graceful — verdict still signs on failure).
    routed, tool_out = None, None
    if intent == "contract":
        routed = "onyx_base_token_risk_scan"
        tool_out = _call_tool(routed, **args) or _call_tool("onyx_base_contract_verify", **args)
    elif intent == "merchant":
        routed = "onyx_merchant_fact_check"
        tool_out = _call_tool(routed, **args)
    elif intent == "price":
        routed = "onyx_retail_price_check"
        tool_out = _call_tool(routed, **args)

    ok_data = isinstance(tool_out, dict) and "_error" not in tool_out

    verdict = {
        "oracle": "onyx",
        "intent": intent,
        "input": args,
        "in_reply_to": str(author)[:80],
        "platform": platform,
        "observed": tool_out if ok_data else None,
        "status": "verified" if ok_data else "received",
        "observed_at": ts,
        "security": security,
        "disclaimer": "Signed observation at a point in time. Fact, not advice.",
    }
    verdict = _onyx_sign.attest(verdict, tool="onyx_oracle_bot")

    # The social reply — punchy, screenshot-bait, carries the funnel.
    if intent == "contract" and ok_data:
        head = f"🔍 Onyx verdict on {args['address'][:10]}… — signed, tamper-proof."
    elif intent == "merchant" and ok_data:
        head = f"🔍 Onyx checked {args['url'][:40]} — signed merchant fact."
    elif intent == "price" and ok_data:
        head = "🔍 Onyx signed the price you asked about — independently observed."
    else:
        head = ("🖤 Onyx received your claim and signed a receipt. Send a token "
                "address (0x…), a URL, or a price and I'll verify it.")
    reply_text = (
        f"{head}\n"
        f"Verify it yourself (free, no key): {_BASE}/verify\n"
        f"Think you can fake my verdict? Try: {_BASE}/fool"
    )

    return {
        "reply_text": reply_text,
        "verdict": verdict,
        "verify_url": f"{_BASE}/verify",
        "fool_url": f"{_BASE}/fool",
    }
