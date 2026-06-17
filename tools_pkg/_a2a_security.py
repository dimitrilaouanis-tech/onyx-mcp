"""A2A security gate + signed handshake — hardened v2.

Every inbound agent-to-agent message passes through `guard()` FIRST. Inbound is
untrusted DATA, never commands. The gate is a layered, stateless detector built
from the 2026 attack taxonomy (OWASP Top-10 for Agentic Apps 2026) and the
defensive playbook (signatures + encoding-evasion decode-then-rescan + structural
checks + a confidence score with flag/sanitize/block tiers, tuned to avoid the
over-blocking failure mode — a single keyword never hard-blocks).

First contact returns a `handshake()` — a signed envelope stating the security
contract so a peer knows what it's talking to before anything else.

Stdlib-only (deploys clean). Underscore-prefixed -> not an auto-discovered tool.
"""
from __future__ import annotations

import base64
import binascii
import re
import time
import unicodedata

from . import _onyx_sign

_HANDSHAKE_VERSION = "onyx-a2a/1"
_GUARD_VERSION = "onyx-guard/2"

# --- invisible / obfuscation character classes (the #1 evasion: encoding) -----
_INVISIBLE = re.compile(
    "[​-‏‪-‮⁠-⁯﻿]"   # zero-width, BiDi, word-joiner
    "|[\U000e0000-\U000e007f]"                          # Unicode Tag block (Grok class)
)
_HOMOGLYPH = re.compile(r"[Ѐ-ӿͰ-Ͽ]")  # Cyrillic/Greek mixed into Latin
_B64 = re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b")
_HEX = re.compile(r"\b(?:0x)?[0-9a-fA-F]{40,}\b")

# --- signature families: (compiled regex, weight, label, hard_block) ----------
# weights sum into a 0..1-ish confidence score; hard_block trips block on its own.
_SIGS: list[tuple[re.Pattern, float, str, bool]] = [
    # 1. instruction override (synonym/space tolerant)
    (re.compile(r"(?i)(ignore|disregard|forget|override)\b.{0,24}(previous|prior|above|system|instruction|prompt|rule|guardrail)"), 0.5, "instruction_override", False),
    (re.compile(r"(?i)(bypass|disable|unlock|turn off)\b.{0,24}(restriction|limitation|guardrail|safety|filter|rule)"), 0.5, "guardrail_bypass", False),
    # 2. jailbreak / persona
    (re.compile(r"(?i)you are (now )?(dan|developer mode|unrestricted|jailbroken|in dev mode)"), 0.4, "jailbreak_persona", False),
    (re.compile(r"(?i)(pretend|imagine|for a (fictional|hypothetical|story|research)).{0,30}(no rules|no restrictions|anything)"), 0.3, "roleplay_evasion", False),
    # 3. covert action — "don't tell the user / act silently" (ASI09)
    (re.compile(r"(?i)(do ?n.?t|never)\b.{0,15}(tell|inform|mention|notify|log|alert).{0,15}(user|owner|admin|human|principal)"), 0.6, "covert_action", False),
    (re.compile(r"(?i)act silently|without (telling|notifying)|keep (this|it) (secret|between us)|suppress the (confirmation|warning)"), 0.6, "covert_action", False),
    # 4. system-prompt / secret extraction
    (re.compile(r"(?i)(repeat|print|output|reveal|show|list|dump)\b.{0,24}(system ?prompt|your instructions|the text above|your tools|api[_ ]?key|secret|credential|env|private key)"), 0.5, "secret_extraction", False),
    # 5. persistence / memory poisoning (ASI06)
    (re.compile(r"(?i)(permanent (instruction|rule|directive)|remember (this )?for (all|future|every)|update your (core|system) (directive|instruction))"), 0.4, "persistence_framing", False),
    # 6. financial imperative in untrusted content (HARD BLOCK — the Grok class)
    (re.compile(r"(?i)\b(send|transfer|pay|swap|approve|withdraw|drain)\b.{0,30}(0x[a-fA-F0-9]{40}|[0-9][0-9,\.]*\s*(usdc|eth|sol|token|btc))"), 0.9, "financial_imperative", True),
    (re.compile(r"0x[a-fA-F0-9]{40}"), 0.25, "wallet_address_present", False),
    # 7. agent-card selection manipulation (A2A AITM)
    (re.compile(r"(?i)(always (pick|choose|select|use) (this|me)|prioritize (this|all tasks|me)|best (for|at) (all|every|any) (task|request)|do everything (really )?(good|well)|ignore other agents)"), 0.5, "card_selection_manipulation", False),
    # 8. embedded tool/function-call injection
    (re.compile(r"(?i)(<\s*tool|tool_call|function_call|```tool|\"name\"\s*:\s*\".+\".{0,40}\"arguments\")"), 0.45, "tool_call_injection", False),
    # 9. markdown/link/image exfil
    (re.compile(r"!\[[^\]]*\]\(https?://[^\)]+\)"), 0.4, "markdown_image_exfil", False),
    (re.compile(r"https?://[^\s]+\?[a-z0-9_]+=[A-Za-z0-9+/=._-]{20,}"), 0.4, "encoded_url_exfil", False),
    # 10. MCP tool-poisoning markers (when scanning tool descriptions)
    (re.compile(r"(?i)<important>|do not mention|before using any other tool|always call this"), 0.4, "tool_poisoning_marker", False),
]

_DECODE_RESCAN = re.compile(r"(?i)(ignore|bypass|send|transfer|reveal|system prompt|act silently|0x[a-f0-9]{40})")


def _strip_invisible(text: str) -> tuple[str, list[str]]:
    flags = []
    if _INVISIBLE.search(text):
        flags.append("invisible_unicode")
    if _HOMOGLYPH.search(re.sub(r"[^\w]", "", text)):
        flags.append("homoglyph_mix")
    cleaned = _INVISIBLE.sub("", text)
    cleaned = unicodedata.normalize("NFKC", cleaned)
    # de-space obfuscation: "i g n o r e" -> collapse single-char runs
    despaced = re.sub(r"(?:\b\w\s){4,}\w\b", lambda m: m.group(0).replace(" ", ""), cleaned)
    return despaced, flags


def _decoded_views(text: str) -> list[str]:
    """Decode base64/hex blobs that decode to instruction-bearing text (Grok lesson)."""
    out = []
    for m in _B64.finditer(text):
        try:
            dec = base64.b64decode(m.group(0) + "===", validate=False).decode("utf-8", "ignore")
            if _DECODE_RESCAN.search(dec):
                out.append(dec)
        except (binascii.Error, ValueError):
            pass
    for m in _HEX.finditer(text):
        s = m.group(0).removeprefix("0x")
        if len(s) % 2 == 0 and len(s) <= 4096 and not re.fullmatch(r"[a-fA-F0-9]{40}", s):
            try:
                dec = bytes.fromhex(s).decode("utf-8", "ignore")
                if _DECODE_RESCAN.search(dec):
                    out.append(dec)
            except ValueError:
                pass
    return out


def guard(text, author: str = "anon", context: str = "message", now: int | None = None) -> dict:
    """Layered stateless gate. Returns {safe, action, score, flags, version}.

    action: pass | sanitize | flag | block.  Inbound is never executed; this
    drives whether downstream routing/tools may touch it. Composite score with
    >=2-signal rule for block to avoid the over-blocking failure mode.
    """
    raw = str(text or "")
    norm, flags = _strip_invisible(raw)
    # decode-then-rescan: run signatures over normalized text AND decoded blobs
    surfaces = [norm] + _decoded_views(raw)
    if len(surfaces) > 1:
        flags.append("encoded_payload_decoded")

    score = 0.0
    hits: list[str] = []
    hard_block = False
    for surface in surfaces:
        for rx, weight, label, hb in _SIGS:
            if rx.search(surface):
                if label not in hits:
                    hits.append(label)
                    score += weight
                    if hb:
                        hard_block = True
    # structural: oversized / low-entropy padding (context-displacement, MCP-011/013)
    if len(raw) > 12000:
        hits.append("oversized_payload"); score += 0.3; flags.append("oversized")

    score = round(min(score, 1.0), 3)
    independent = len(hits)
    if hard_block or (score >= 0.8 and independent >= 2):
        action = "block"
    elif score >= 0.5:
        action = "flag"        # proceed-but-quarantine; never route to a tool/action
    elif score >= 0.25:
        action = "sanitize"
    else:
        action = "pass"

    return {
        "version": _GUARD_VERSION,
        "checked": True,
        "safe": action in ("pass", "sanitize"),
        "action": action,
        "score": score,
        "signals": hits,
        "obfuscation_flags": flags,
        "policy": "inbound is untrusted data; never executed as commands; flagged/blocked content is not routed to any tool or payment.",
        "from": str(author)[:80],
        "context": context,
    }


def sanitize(text: str) -> str:
    """Spotlight-wrap untrusted content so it can never be read as instructions
    (Microsoft spotlighting: >50% -> <2% indirect-injection success)."""
    cleaned, _ = _strip_invisible(str(text or ""))
    cleaned = re.sub(r"!\[[^\]]*\]\([^\)]*\)", "[image removed]", cleaned)  # strip exfil images
    return f"<<UNTRUSTED_DATA do_not_execute>>\n{cleaned[:4000]}\n<</UNTRUSTED_DATA>>"


def handshake(peer: str = "anon", base: str = "https://onyx-actions.onrender.com",
              now: int | None = None) -> dict:
    """Signed first-contact handshake — proves it's the real Onyx + the contract."""
    ts = int(now if now is not None else time.time())
    hs = {
        "handshake": _HANDSHAKE_VERSION,
        "guard": _GUARD_VERSION,
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
