"""Password strength scoring — entropy + common-pattern heuristics."""
from __future__ import annotations

import math
import re

NAME = "onyx_password_strength"
PRICE_USDC = "0.0003"
TIER = "metered"
DESCRIPTION = (
    "Score password strength on a 0-100 scale. Returns Shannon entropy "
    "(bits), character-class diversity, length, common-pattern detection "
    "(sequences, repeats, dictionary-likeness), and a verdict (very_weak / "
    "weak / fair / strong / very_strong). Use when an agent generates "
    "passwords for accounts it creates, or when validating user-supplied "
    "credentials. Stdlib-only — runs locally, never sends the password "
    "anywhere. <5ms."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "password": {"type": "string", "description": "Password to score"},
    },
    "required": ["password"],
}

_COMMON_PATTERNS = [
    re.compile(r"(.)\1{2,}"),
    re.compile(r"(012|123|234|345|456|567|678|789|abc|qwe|asd|zxc)", re.IGNORECASE),
    re.compile(r"(password|admin|welcome|letmein|qwerty|monkey|dragon|iloveyou)", re.IGNORECASE),
]


def run(password: str, **_: object) -> dict:
    if password is None:
        raise ValueError("password required (empty string allowed)")
    p = password
    length = len(p)
    has_lower = bool(re.search(r"[a-z]", p))
    has_upper = bool(re.search(r"[A-Z]", p))
    has_digit = bool(re.search(r"[0-9]", p))
    has_symbol = bool(re.search(r"[^a-zA-Z0-9]", p))
    pool = (26 if has_lower else 0) + (26 if has_upper else 0) + (10 if has_digit else 0) + (33 if has_symbol else 0)
    entropy = round(length * math.log2(pool), 2) if pool > 0 and length > 0 else 0
    flagged = [pat.pattern for pat in _COMMON_PATTERNS if pat.search(p)]
    score = min(100, int(entropy * 1.6))
    if flagged:
        score = max(0, score - 25 * len(flagged))
    if length < 8:
        score = min(score, 30)
    verdict = ("very_weak" if score < 20 else
               "weak" if score < 40 else
               "fair" if score < 60 else
               "strong" if score < 80 else "very_strong")
    return {
        "length": length,
        "entropy_bits": entropy,
        "score_0_100": score,
        "verdict": verdict,
        "has_lower": has_lower, "has_upper": has_upper,
        "has_digit": has_digit, "has_symbol": has_symbol,
        "patterns_flagged": flagged,
    }
