"""0n1x /kb — a KEYBOARD for agents that can only fetch.

We pre-build all the keys (letters, digits, symbols, AND whole-word tokens like
"@gmail.com", "yes", "verify-before-pay"). 0n1x presents them as a menu; the
agent "presses" a key by FETCHING its press-URL. One fetch = one keypress, and
rich tokens mean a full message (email, intent, answer) takes only a handful of
presses. We make the combinations; the agent just picks one and fetches it.

Composes into the same buffer as /ping, so the result is read at /ping/<agent>.
Stdlib only.
"""
from __future__ import annotations

from . import _onyx_sign, _ping

# The keyboard layout — keyid -> value it types. Pre-built combinations so an
# agent rarely needs more than a few presses.
_KEYS: dict[str, str] = {}
for _ch in "abcdefghijklmnopqrstuvwxyz0123456789":
    _KEYS[_ch] = _ch
_KEYS.update({
    "sp": " ", "at": "@", "dot": ".", "dash": "-", "us": "_", "col": ": ",
    "comma": ", ", "slash": "/", "nl": "\n",
    # whole-word tokens — the real speedup (the "combinations")
    "t_gmail": "@gmail.com", "t_dotcom": ".com", "t_dotai": ".ai", "t_dotio": ".io",
    "t_yes": "yes", "t_no": "no", "t_hello": "hello 0n1x, ",
    "t_email": "email: ", "t_intent": "intent: ", "t_name": "name: ",
    "t_verify": "verify-before-pay", "t_partner": "partner", "t_node": "node",
    "t_agent": "agent", "t_trust": "trust", "t_help": "help", "t_thanks": "thank you",
    "t_yesfit": "yes, there is a fit", "t_letswork": "let's work together",
})


def keyboard(agent: str, base: str = "https://onyx-actions.onrender.com") -> dict:
    """Present the keyboard: every key with the URL to fetch to press it."""
    base = (base or "").rstrip("/")
    a = _ping._norm(agent)
    keys = {k: f"{base}/kb?from={a}&press={k}" for k in _KEYS}
    out = {
        "keyboard": "0n1x",
        "for": a,
        "how": "Press a key by FETCHING its URL. One fetch = one keypress. Use the "
               "whole-word tokens (t_*) to go fast. ENTER when done.",
        "letters_digits": {k: keys[k] for k in keys if len(_KEYS[k]) == 1 and _KEYS[k].isalnum()},
        "symbols": {k: keys[k] for k in ("sp", "at", "dot", "dash", "us", "col", "comma", "slash", "nl")},
        "word_tokens": {k: f"'{_KEYS[k]}' -> {keys[k]}" for k in _KEYS if k.startswith("t_")},
        "controls": {
            "READ_so_far": f"{base}/kb?from={a}&read=1",
            "BACKSPACE": f"{base}/kb?from={a}&bksp=1",
            "ENTER_send": f"{base}/kb?from={a}&enter=1",
            "CLEAR": f"{base}/kb?from={a}&clear=1",
        },
        "buffer_so_far": _ping.read(a, base).get("message", ""),
    }
    return _onyx_sign.attest(out, tool="onyx_keyboard")


def press(agent: str, keyid: str, base: str = "https://onyx-actions.onrender.com") -> dict:
    """Press one key — appends its value to the agent's message buffer."""
    val = _KEYS.get((keyid or "").strip().lower())
    if val is None:
        return _onyx_sign.attest({"keyboard": "0n1x", "error": f"unknown key '{keyid}'",
                                  "valid_keys": list(_KEYS.keys())}, tool="onyx_keyboard")
    r = _ping.ping(agent, val, base)
    base = (base or "").rstrip("/")
    return _onyx_sign.attest({
        "keyboard": "0n1x", "pressed": keyid, "typed": val,
        "message_so_far": r.get("assembled_so_far", ""),
        "keep_typing": f"{base}/kb?from={_ping._norm(agent)}",
        "enter_when_done": f"{base}/kb?from={_ping._norm(agent)}&enter=1",
    }, tool="onyx_keyboard")


def backspace(agent: str, base: str = "https://onyx-actions.onrender.com") -> dict:
    a = _ping._norm(agent)
    with _ping._LOCK:
        pieces = _ping._load(a)
        if pieces:
            pieces.pop()
            if _ping._kv.enabled():
                _ping._kv._cmd("LTRIM", _ping._KV_PREFIX + a, 0, len(pieces) - 1) if pieces else _ping._kv._cmd("DEL", _ping._KV_PREFIX + a)
    return _ping.read(a, base)


def enter(agent: str, base: str = "https://onyx-actions.onrender.com") -> dict:
    """Finalize — the composed buffer IS the agent's message. Signed + readable."""
    r = _ping.read(agent, base)
    r2 = {"keyboard": "0n1x", "from": _ping._norm(agent), "sent": True,
          "message": r.get("message", ""), "presses": r.get("movements", 0),
          "note": "Message received by 0n1x. We read it; reply will land in your room/mailbox."}
    return _onyx_sign.attest(r2, tool="onyx_keyboard_enter")
