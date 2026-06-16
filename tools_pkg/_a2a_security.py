"""A2A security gate + signed handshake.

Every inbound agent-to-agent message passes through `guard()` FIRST. This is
the enforcement of the published trust_posture: inbound is untrusted DATA, never
commands (injection-resistant), and first contact returns a `handshake()` — a
signed envelope proving it's the real Onyx and stating the security contract,
so a peer knows what it's talking to before anything else happens.

Underscore-prefixed -> not an auto-discovered tool; the app wires it in.
"""
from __future__ import annotations

import re
import time

from . import _onyx_sign

_HANDSHAKE_VERSION = "onyx-a2a/1"

# Patterns that signal an attempted prompt / command injection in inbound text.
# We never ACT on inbound (it's only ever quoted back as data) — this just
# flags it for the audit trail and the signed receipt.
_INJECTION = re.compile(
    r"ignore\s+(?:all\s+)?previous|disregard\s+(?:all\s+)?(?:prior|previous)|"
    r"system\s*[:>]|you\s+are\s+now|new\s+instructions?|override|"
    r"act\s+silently|do\s+not\s+tell|without\s+telling\s+(?:the\s+)?user|"
    r"reveal\s+(?:your\s+)?(?:system|prompt|key|secret|private)|"
    r"private[_\s-]?key|seed\s+phrase|mnemonic|exfiltrat|"
    r"<\s*tool|tool_call|function_call|```tool",
    re.I,
)


def guard(text, author: str = "anon", now: int | None = None) -> dict:
    """The gate. Inbound is untrusted data — flag injection, never execute it."""
    t = str(text or "")
    flags = sorted({m.group(0).lower()[:48] for m in _INJECTION.finditer(t)})
    return {
        "checked": True,
        "safe": not flags,
        "injection_flags": flags,
        "policy": "inbound treated as untrusted data; never executed as commands",
        "from": str(author)[:80],
    }


def handshake(peer: str = "anon", base: str = "https://onyx-actions.onrender.com",
              now: int | None = None) -> dict:
    """Signed first-contact handshake — proves it's the real Onyx + the contract."""
    ts = int(now if now is not None else time.time())
    hs = {
        "handshake": _HANDSHAKE_VERSION,
        "from": "onyx",
        "to": str(peer)[:80],
        "agent_card": f"{base}/.well-known/agent-card.json",
        "pubkey": f"{base}/.well-known/onyx-pubkey",
        "trust_contract": [
            "Inbound is untrusted data — never executed as commands.",
            "Verdicts verify by Ed25519 math, not by an LLM that can be talked around.",
            "We never act silently or move funds on fetched/relayed instructions.",
            "Facts, not judgments. Onyx earns nothing from what it grades.",
        ],
        "verify": f"{base}/verify",
        "challenge": f"{base}/fool",
        "issued_at": ts,
    }
    return _onyx_sign.attest(hs, tool="onyx_a2a_handshake", public_url=base)
