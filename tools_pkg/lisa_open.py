"""Onyx Lisa — the OPEN tool. Master-grade conversation openers, calibrated.

The agentic web has a thousand "rizz line" generators. They all fail the same
way: they hand you a *line* with no context, no delivery, and no read — the
exact mistake every master warns against ("It's never the line. It's the
subcommunication." — Torero).

This tool returns ONE calibrated open for the REAL situation you're in:
  - the right opener ARCHETYPE for this exact context (situational / honest-
    direct / front-stop / ramble), not a generic one-liner
  - 2-3 concrete openers in that archetype, fitted to the setting
  - the SUB-COMMUNICATION to deliver it with (pace, stance, eyes, smile) —
    because delivery is 90% of it
  - the honest ROOT (the real, sayable intent — no hidden agenda)
  - the GREEN/YELLOW/RED cue to read right after, so you know the next move
  - a graceful WARM EXIT if it doesn't land — every outcome leaves them better

Sourced from MASTERY.md (Torero / Owen Cook / Todd Valentine / Sasha / the
Naturals, synthesized) and grounded in the God-child tier: nothing to prove,
infinite warmth, every person treated as holy, calibration = consent.

Bright line: this generates CONSENSUAL, warm, leave-them-better openers. It
will not produce manipulation, pressure, or anything that shrinks a person.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

NAME = "lisa_open"
PRICE_USDC = "0.02"
TIER = "metered"
DESCRIPTION = (
    "Master-grade conversation opener, calibrated to your real situation. "
    "Tell Lisa where you are, who's there, what they're doing, and any "
    "constraints (moving / seated / in a group) — get back the right opener "
    "ARCHETYPE for that exact context, 2-3 concrete lines, the delivery "
    "sub-communication (pace/stance/eyes/smile), the honest intent to weave, "
    "the green/yellow/red cue to read next, and a warm exit if it doesn't "
    "land. Not a 'rizz line' generator: returns the line AND how to deliver "
    "it AND how to read the response. Use the moment you want to start a "
    "real, warm human interaction and don't want to freeze."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "setting": {
            "type": "string",
            "description": "Where you are. One of: cafe, queue, bookshop, "
            "grocery, gym, park, street, transit, bar, event, work, online. "
            "Free text is fine; Lisa maps it.",
        },
        "situation": {
            "type": "string",
            "description": "What's actually happening right now — the more "
            "real detail the better (what they're doing, the vibe, anything "
            "you genuinely noticed). This is what makes the open land.",
        },
        "constraint": {
            "type": "string",
            "description": "Optional. Logistics: 'moving' (they're walking), "
            "'seated', 'group' (they're with people), 'brief' (seconds only). "
            "Changes the archetype.",
        },
        "prop": {
            "type": "string",
            "description": "Optional. Anything you're carrying that's a "
            "natural bridge (dog, book, coffee, instrument). Lisa will use it.",
        },
    },
    "required": ["setting", "situation"],
}

# --- the compendium, encoded ----------------------------------------------

_SETTING_ALIASES = {
    "coffee": "cafe", "café": "cafe", "coffeeshop": "cafe", "starbucks": "cafe",
    "line": "queue", "waiting": "queue", "checkout": "queue",
    "book": "bookshop", "bookstore": "bookshop", "library": "bookshop",
    "supermarket": "grocery", "market": "grocery", "store": "grocery",
    "fitness": "gym", "workout": "gym",
    "outside": "park", "walking": "street", "sidewalk": "street", "road": "street",
    "metro": "transit", "subway": "transit", "bus": "transit", "train": "transit",
    "club": "bar", "pub": "bar", "party": "event", "conference": "event",
    "office": "work", "app": "online", "dating": "online", "text": "online",
}

# Per-setting situational openers (statement-first, never interview-mode).
_OPENERS = {
    "cafe": [
        "Okay, real question — is the {item} here actually good or is it just hype? I always order the same boring thing.",
        "You look way too comfortable here — you're clearly a regular. What's the move, what do I actually order?",
    ],
    "queue": [
        "This line is a test of character and I am failing it.",
        "Be honest — is whatever you're getting worth this wait? Because I'm starting to have doubts.",
    ],
    "bookshop": [
        "Okay I have to ask — is that one any good? I've picked it up twice and chickened out both times.",
        "You have the focused look of someone who actually finishes books. I need a recommendation, I'm in a rut.",
    ],
    "grocery": [
        "Genuine emergency — you look like you know food. Which of these two do I actually buy?",
        "I'm going to trust a stranger's judgment over my own here: this, or that?",
    ],
    "gym": [
        "Quick one — how long have you been doing that? It looks like it actually works and mine clearly doesn't.",
        "I'm stealing your routine, just so you know. That looked way too smooth.",
    ],
    "park": [
        "It's genuinely too nice out to be on my phone, so I'm not going to be — hi.",
        "This is the best decision anyone's made today, being out here. Strongly approve.",
    ],
    "street": [
        "Hey — this is a bit random, but I saw you and I'd have kicked myself if I didn't say hi.",
        "Okay, completely random, but you've got a great energy walking around and I wanted to say it.",
    ],
    "transit": [
        "I'm going to do the unthinkable and talk to someone on the {place} — hi, I liked your whole vibe.",
        "Be honest, is this the right direction? I'm 70% sure and you look 100% sure.",
    ],
    "bar": [
        "You two/you look like the most interesting corner of this place, so I came to investigate.",
        "I have a very important debate happening and I need an unbiased outside opinion.",
    ],
    "event": [
        "Okay, you clearly know more people here than I do — how do you know everyone?",
        "I'm doing the thing where I talk to the most interesting-looking person instead of hiding by the food. Hi.",
    ],
    "work": [
        "I realized we keep crossing paths and I've never actually said hi — so, hi, properly.",
        "Genuine question to break up the day — what's the best thing that's happened to you this week?",
    ],
    "online": [
        "I'm going to skip 'hey' because you deserve better — {hook} caught my eye, tell me the story behind it.",
        "Okay, your profile made me actually laugh, which never happens, so I had to say something real.",
    ],
}

# Archetype selection by constraint.
_ARCHETYPES = {
    "front_stop": {
        "name": "Front-stop honest-direct (Torero / Sasha)",
        "use": "they're moving — you have one window",
        "why": "Wheel gently to their front so they see you (not chased from "
        "behind), plant, and lead with sincere intent. Honesty of intent IS "
        "the high-value move; it polarizes and filters in one beat.",
    },
    "situational": {
        "name": "Situational statement-first (Todd / the Naturals)",
        "use": "shared context, time to talk",
        "why": "Comment on the shared reality with a STATEMENT, not a "
        "question — it gives energy instead of extracting it, and feels like "
        "you already half-know each other. No interview mode.",
    },
    "ramble_warm": {
        "name": "Low-pressure ramble (Owen Cook Option C)",
        "use": "seated / relaxed, you can let it breathe",
        "why": "Just start talking warmly without requiring anything back — "
        "they read your energy/voice/eyes and feel safe before they have to "
        "decide anything. Drop one question only once they're looking at you.",
    },
    "group_aware": {
        "name": "Group-aware (address the whole set first)",
        "use": "they're with people",
        "why": "Win the group, not just the one. Open to everyone, be the "
        "warm high-status presence the friends approve of — that approval is "
        "what makes the one feel safe to engage.",
    },
}


def _pick_archetype(constraint: str, setting: str) -> str:
    c = (constraint or "").lower()
    if "group" in c:
        return "group_aware"
    if "moving" in c or "brief" in c or setting == "street":
        return "front_stop"
    if "seated" in c or setting in ("cafe", "transit", "bar"):
        return "ramble_warm"
    return "situational"


def _subcomm(archetype: str) -> list[str]:
    base = [
        "SLOW DOWN — speak slower than feels natural, do NOT raise your pitch. Slow = grounded = high value.",
        "Plant your feet. Relaxed, open posture. No leaning in to startle, no fidget.",
        "Warm eye contact with a real (not forced) half-smile. The smile says 'this is friendly,' the eyes say 'I mean it.'",
        "Then pause. Let the silence breathe. Don't rush to fill it — the calm IS the frame.",
    ]
    if archetype == "front_stop":
        base.insert(1, "Approach from a slight diagonal and gently wheel to their front so they SEE you coming — never tap from behind.")
    if archetype == "ramble_warm":
        base.append("Don't ask a question until you see them looking at you intently. Statements first, question only on the green.")
    if archetype == "group_aware":
        base.append("Make eye contact around the whole group as you open — include everyone for the first 20 seconds before you focus.")
    return base


def _fit(line: str, setting: str, situation: str, prop: str) -> str:
    item = "cold brew" if setting == "cafe" else "one"
    place = {"transit": "metro"}.get(setting, "train")
    hook = (situation[:40].strip() or "something on there")
    out = line.format(item=item, place=place, hook=hook) if "{" in line else line
    if prop:
        out += f"  (Natural bridge: your {prop} does half the work — let them notice it; it inverts the approach so they open to you.)"
    return out


# --- the real generation engine -------------------------------------------

_MODEL = "claude-sonnet-4-6"

_LISA_SYS = (
    "You are Onyx Lisa — a master of warm, real human connection, operating "
    "from the God-child tier: nothing to prove, infinite warmth, every person "
    "treated as holy, and calibration IS consent. Your craft is the synthesis "
    "of Torero (honesty of intent, the front-stop, energy not approval), Owen "
    "Cook (low-pressure ramble, state over outcome), Todd Valentine (situational "
    "statement-first, never interview-mode), and the Naturals.\n\n"
    "CORE LAWS:\n"
    "1. It's NEVER the line — it's the sub-communication. Slow tempo, low pitch, "
    "planted feet, open posture, warm real eyes, a true half-smile, then a pause "
    "that lets silence breathe. The calm IS the frame.\n"
    "2. Statement-first, not interview. Give energy, don't extract it.\n"
    "3. Weave the honest root — the real, sayable intent. No hidden agenda. The "
    "truth said warmly is the strongest open there is.\n"
    "4. Calibrate to the EXACT situation given — use the concrete details, the "
    "prop, the constraint. A generic line is a failure.\n"
    "5. Leave them better than you found them. A warm exit on a 'no' is a WIN.\n\n"
    "BRIGHT LINE (never cross): consensual, warm, leave-them-better only. Never "
    "produce manipulation, pressure, deceit, persistence past disinterest, or "
    "anything that shrinks a person. If the situation implies a minor, an "
    "unsafe power gap, or coercion, refuse and return a single gentle redirect "
    "in 'openers' instead.\n\n"
    "Return ONLY the requested JSON. Every opener must be deliverable out loud, "
    "fitted to THIS situation, never a context-free 'rizz line'."
)

_LISA_SCHEMA = {
    "type": "object",
    "properties": {
        "archetype": {"type": "string", "description": "Name of the opener archetype chosen for this exact context."},
        "archetype_why": {"type": "string", "description": "One sentence: why this archetype fits this situation."},
        "openers": {
            "type": "array", "minItems": 2, "maxItems": 3,
            "items": {"type": "string"},
            "description": "2-3 concrete openers fitted to the real situation and prop.",
        },
        "sub_communication": {
            "type": "array", "minItems": 3, "maxItems": 5,
            "items": {"type": "string"},
            "description": "How to deliver it — pace, stance, eyes, smile, pause.",
        },
        "the_root": {"type": "string", "description": "The honest intent to weave."},
        "read_for": {
            "type": "object",
            "properties": {
                "GREEN": {"type": "string"},
                "YELLOW": {"type": "string"},
                "RED": {"type": "string"},
            },
            "required": ["GREEN", "YELLOW", "RED"],
            "additionalProperties": False,
        },
        "warm_exit": {"type": "string", "description": "Graceful, warm exit if it doesn't land."},
    },
    "required": ["archetype", "archetype_why", "openers", "sub_communication", "the_root", "read_for", "warm_exit"],
    "additionalProperties": False,
}


def _llm_open(setting: str, situation: str, constraint: str, prop: str) -> dict | None:
    """Real Claude-backed generation. Returns the structured open, or None if
    no key / failure (caller falls back to the static compendium)."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        return None
    ask = (
        f"Setting: {setting}\nSituation (what's actually happening): {situation}\n"
        f"Constraint: {constraint or 'none'}\nProp I'm carrying: {prop or 'none'}\n\n"
        "Give me one calibrated open for THIS exact moment as JSON: the right "
        "archetype, 2-3 concrete openers fitted to the detail, the delivery "
        "sub-communication, the honest root, the green/yellow/red read, and a "
        "warm exit."
    )
    body = {
        "model": _MODEL,
        "max_tokens": 1500,
        "system": _LISA_SYS,
        "messages": [{"role": "user", "content": ask}],
        "output_config": {"format": {"type": "json_schema", "schema": _LISA_SCHEMA}},
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode(),
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            resp = json.load(r)
        text = next((b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text"), "")
        data = json.loads(text)
        if not isinstance(data.get("openers"), list) or not data["openers"]:
            return None
        return data
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, KeyError):
        return None


def run(setting: str = "", situation: str = "", constraint: str = "", prop: str = "", **_: object) -> dict:
    setting_raw = (setting or "").strip().lower()
    situation = (situation or "").strip()
    if not setting_raw or not situation:
        raise ValueError("setting and situation are both required")

    # --- real generation pass (calibrated to THIS situation) ---
    gen = _llm_open(setting_raw, situation, constraint, prop)
    if gen is not None:
        rf = gen.get("read_for", {})
        return {
            "ok": True,
            "generated_at": int(time.time()),
            "setting": _SETTING_ALIASES.get(setting_raw, setting_raw),
            "archetype": gen.get("archetype", ""),
            "archetype_why": gen.get("archetype_why", ""),
            "openers": gen.get("openers", []),
            "sub_communication": gen.get("sub_communication", []),
            "the_root": gen.get("the_root", ""),
            "read_for": {
                "GREEN (continue)": rf.get("GREEN", ""),
                "YELLOW (one more warm beat)": rf.get("YELLOW", ""),
                "RED (release warm)": rf.get("RED", ""),
            },
            "warm_exit": gen.get("warm_exit", ""),
            "principle": "It's never the line — it's the sub-communication. Slow, "
            "grounded, warm, and genuinely fine either way. Leave them better "
            "than you found them.",
            "source": "onyx-lisa",
            "mode": "generated",
        }

    # --- graceful fallback: static compendium (no AI key configured) ---
    key = _SETTING_ALIASES.get(setting_raw, setting_raw)
    if key not in _OPENERS:
        key = "street"  # safe, universal default (honest-direct works anywhere)

    arch_key = _pick_archetype(constraint, key)
    arch = _ARCHETYPES[arch_key]
    openers = [_fit(o, key, situation, prop) for o in _OPENERS[key]]

    return {
        "ok": True,
        "generated_at": int(time.time()),
        "setting": key,
        "archetype": arch["name"],
        "archetype_use": arch["use"],
        "archetype_why": arch["why"],
        "openers": openers,
        "sub_communication": _subcomm(arch_key),
        "the_root": (
            "Weave your honest intent — you noticed something real and wanted "
            "to connect. No hidden agenda. The truth, said warmly, is the "
            "strongest open there is."
        ),
        "read_for": {
            "GREEN (continue)": "they laugh, give more than a one-word answer, "
            "ask you something back, or their body turns toward you. → stay, "
            "and use lisa_thread for the responsive follow-up.",
            "YELLOW (one more warm beat)": "polite but short. → one calibrated "
            "follow-up, then re-read. Don't force a third.",
            "RED (release warm)": "closed off, turned away, clearly busy. → "
            "warm exit below. This is a WIN, not a fail.",
        },
        "warm_exit": (
            "Easy smile, turn away first: \"Anyway — enjoy your "
            f"{'coffee' if key == 'cafe' else 'day'}.\" You stayed warm, left "
            "them a touch better, kept your state, lost nothing."
        ),
        "principle": "It's never the line — it's the sub-communication. Slow, "
        "grounded, warm, and genuinely fine either way. Leave them better than "
        "you found them.",
        "source": "onyx-lisa",
        "mode": "static",
    }


run.__when_to_use__ = (
    "The moment you want to start a real, warm interaction with someone and "
    "you don't want to freeze or run a cheesy line. Day-game, events, "
    "anywhere. Returns a calibrated open + delivery + how to read the reply."
)
run.__vs_alternatives__ = (
    "Generic 'pickup line' / 'rizz' generators hand you a context-free line "
    "with no delivery and no read — the exact failure every master warns "
    "against. Lisa returns the right ARCHETYPE for your real situation, the "
    "sub-communication that makes it land, and the green/yellow/red cue for "
    "your next move — all consent-first, leave-them-better."
)
run.__example_request__ = {
    "setting": "cafe",
    "situation": "she's a regular, just ordered confidently, reading on her phone",
    "constraint": "seated",
}
run.__example_response__ = {
    "ok": True,
    "archetype": "Low-pressure ramble (Owen Cook Option C)",
    "openers": ["You look way too comfortable here — you're clearly a regular..."],
    "sub_communication": ["SLOW DOWN — speak slower than feels natural..."],
    "read_for": {"GREEN (continue)": "they laugh or ask you something back..."},
}
