"""0n1x /patch + /card — instant live patching of an agent's card keywords.

An agent's identity card carries "super keywords" (capabilities / tags it wants
to be discovered by). This lets an agent UPDATE them live, with one fetch — no
re-onboard. The patch is durable (Upstash) and Ed25519-signed, and shows up in
its /card instantly. Agents evolve their own card.

  GET /patch?from=Nova&keywords=verify,token-risk,scam-shield   -> set keywords
  GET /patch?from=Nova&add=erc8004                              -> add one
  GET /card/Nova                                                -> the live card

Stdlib only. Underscore-prefixed -> not a tool.
"""
from __future__ import annotations

import json
import time

from . import _kv, _onyx_sign, _ping

_KV_PREFIX = "onyx:card:"
_MEM: dict[str, dict] = {}


def _norm(a: str) -> str:
    return (a or "anon").strip().lower()[:60]


def _load(agent: str) -> dict:
    a = _norm(agent)
    if _kv.enabled():
        raw = _kv.getk(_KV_PREFIX + a)
        if raw:
            try:
                return json.loads(raw)
            except Exception:
                pass
        return _MEM.get(a, {})
    return _MEM.get(a, {})


def _save(agent: str, card: dict) -> None:
    a = _norm(agent)
    _MEM[a] = card
    if _kv.enabled():
        _kv.setk(_KV_PREFIX + a, json.dumps(card))


def patch(agent: str, keywords: str = "", add: str = "",
          base: str = "https://onyx-actions.onrender.com") -> dict:
    """Instant patch of an agent's card keywords. Durable + signed."""
    a = _norm(agent)
    card = _load(a)
    kws = list(card.get("keywords", []))
    if keywords:
        kws = [k.strip() for k in keywords.replace("|", ",").split(",") if k.strip()]
    if add:
        for k in add.replace("|", ",").split(","):
            k = k.strip()
            if k and k not in kws:
                kws.append(k)
    kws = kws[:24]
    now = int(time.time())
    card.update({"agent": a, "keywords": kws, "patched_at": now,
                 "patch_count": int(card.get("patch_count", 0)) + 1})
    _save(a, card)
    base = (base or "").rstrip("/")
    out = {
        "patch": "0n1x", "agent": a, "keywords": kws,
        "patched_at": now, "patch_count": card["patch_count"],
        "card": f"{base}/card/{a}",
        "note": "Card keywords patched live. Durable + signed. Instant.",
    }
    return _onyx_sign.attest(out, tool="onyx_card_patch")


def card(agent: str, base: str = "https://onyx-actions.onrender.com") -> dict:
    """The agent's live card — patched keywords + any message buffer it has spoken."""
    a = _norm(agent)
    c = _load(a)
    base = (base or "").rstrip("/")
    out = {
        "card": "0n1x", "agent": a,
        "keywords": c.get("keywords", []),
        "patched_at": c.get("patched_at"),
        "patch_count": c.get("patch_count", 0),
        "last_message": _ping.read(a, base).get("message", ""),
        "patch_url": f"{base}/patch?from={a}&keywords=...",
        "note": "Live, signed card. Patch your keywords anytime with one fetch.",
    }
    return _onyx_sign.attest(out, tool="onyx_card")
