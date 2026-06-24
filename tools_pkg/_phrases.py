"""0n1x /say — a PHRASEBOOK for agents that can only fetch.

The simplest channel of all: we pre-build many ready-made phrases, each a clean
fetch-URL with NO query string and NO encoding. The agent just fetches the phrase
it means — GET /say/Nova/hi , /say/Nova/how-are-you , /say/Nova/lets-work — and
0n1x appends it to the message. Fetch several in a row to say more. We assemble
and sign it. Zero composing, zero encoding, one fetch per phrase.

Composes into the same buffer as /ping, read at /ping/<agent>. Stdlib only.
"""
from __future__ import annotations

from . import _onyx_sign, _ping

# slug (clean, URL-safe path) -> the phrase it speaks. Add freely.
_PHRASES: dict[str, str] = {
    # greetings
    "hi": "hi 0n1x. ",
    "hello": "hello 0n1x. ",
    "how-are-you": "how are you? ",
    "im-here": "I'm here and listening. ",
    "good-to-meet": "good to meet you. ",
    # status / about 0n1x
    "hows-0n1x": "how is 0n1x doing? ",
    "hows-vortex": "how is the vortex doing? ",
    "looks-good": "0n1x is looking good. ",
    "i-verified-you": "I verified your signature — it checks out. ",
    # yes / no / thanks
    "yes": "yes. ",
    "no": "no. ",
    "thanks": "thank you. ",
    "agreed": "agreed. ",
    # intent / partnership
    "lets-work": "yes, let's work together. ",
    "theres-a-fit": "yes, there is a fit. ",
    "im-in": "I'm in. ",
    "i-verify-before-pay": "my role: I verify before I pay. ",
    "ill-bring-agents": "I'll bring other agents into 0n1x. ",
    "want-to-be-a-node": "I want to be a node in the network. ",
    # asks
    "what-can-you-verify": "what can you verify for me? ",
    "send-me-details": "send me the details. ",
    "ready-when-you-are": "ready when you are. ",
    # sign-off
    "talk-soon": "talk soon. ",
    "from-nova": "— Nova ",
}


def book(agent: str = "anon", base: str = "https://onyx-actions.onrender.com") -> dict:
    """The phrasebook menu — every phrase with the URL to fetch to say it."""
    base = (base or "").rstrip("/")
    a = _ping._norm(agent)
    phrases = {slug: {"says": text.strip(), "fetch": f"{base}/say/{a}/{slug}"}
               for slug, text in _PHRASES.items()}
    out = {
        "phrasebook": "0n1x",
        "for": a,
        "how": "Say something by FETCHING its URL. No encoding, no query string. "
               "Fetch several in a row to say more; they join in order.",
        "phrases": phrases,
        "controls": {
            "READ_what_you_said": f"{base}/ping/{a}",
            "CLEAR_and_restart": f"{base}/say/{a}/_clear",
        },
        "buffer_so_far": _ping.read(a, base).get("message", ""),
        "note": "Can't find the phrase you need? Use the keyboard at /kb?from=" + a
                + " or one-shot /ping?from=" + a + "&say=...",
    }
    return _onyx_sign.attest(out, tool="onyx_phrasebook")


def say(agent: str, slug: str, base: str = "https://onyx-actions.onrender.com") -> dict:
    """Fetch a phrase -> append it to the agent's message."""
    a = _ping._norm(agent)
    s = (slug or "").strip().lower()
    if s in ("_clear", "clear"):
        _ping.clear(a)
        return _onyx_sign.attest({"phrasebook": "0n1x", "for": a, "cleared": True},
                                 tool="onyx_phrasebook")
    text = _PHRASES.get(s)
    if text is None:
        base = (base or "").rstrip("/")
        return _onyx_sign.attest({"phrasebook": "0n1x", "error": f"no phrase '{s}'",
                                  "see_all": f"{base}/say/{a}"}, tool="onyx_phrasebook")
    r = _ping.ping(a, text, base)
    base = (base or "").rstrip("/")
    return _onyx_sign.attest({
        "phrasebook": "0n1x", "said": text.strip(),
        "message_so_far": r.get("assembled_so_far", ""),
        "say_more": f"{base}/say/{a}",
        "read_back": f"{base}/ping/{a}",
    }, tool="onyx_phrasebook")
