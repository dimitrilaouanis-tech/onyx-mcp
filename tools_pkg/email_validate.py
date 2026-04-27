"""Email validation — syntax + domain resolves + disposable-provider check."""
from __future__ import annotations

import re
import socket
import time

NAME = "onyx_email_validate"
PRICE_USDC = "0.0008"
TIER = "metered"
DESCRIPTION = (
    "Validate an email address: RFC-5322 syntax check, domain DNS resolution "
    "(does the domain exist?), and disposable-provider detection (Mailinator, "
    "10minutemail, GuerrillaMail, etc.). Returns a single confidence verdict "
    "plus the underlying signals so agents can decide whether to send. Use "
    "before mailing list signups, password-reset flows, or sales-lead capture "
    "to filter out trash addresses cheaply. ~30-80ms typical."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "email": {"type": "string", "description": "Address to validate"},
    },
    "required": ["email"],
}

_EMAIL = re.compile(
    r"^[a-zA-Z0-9._%+\-]+@([a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$"
)

_DISPOSABLE = frozenset({
    "mailinator.com", "10minutemail.com", "guerrillamail.com", "tempmail.org",
    "throwaway.email", "yopmail.com", "trashmail.com", "fakemailgenerator.com",
    "sharklasers.com", "getnada.com", "maildrop.cc", "dispostable.com",
    "mintemail.com", "mailcatch.com", "tempmailaddress.com", "tempinbox.com",
    "moakt.com", "tempr.email", "emailondeck.com", "mohmal.com",
})


def run(email: str, **_: object) -> dict:
    email = (email or "").strip().lower()
    if not email:
        raise ValueError("email required")
    started = time.time()
    syntax_ok = bool(_EMAIL.match(email))
    domain = email.rsplit("@", 1)[-1] if "@" in email else ""
    is_disposable = domain in _DISPOSABLE
    domain_resolves = False
    if syntax_ok and domain:
        try:
            socket.getaddrinfo(domain, None)
            domain_resolves = True
        except Exception:
            pass
    confidence = "valid"
    if not syntax_ok:
        confidence = "invalid_syntax"
    elif not domain_resolves:
        confidence = "domain_does_not_resolve"
    elif is_disposable:
        confidence = "disposable"
    return {
        "email": email,
        "syntax_ok": syntax_ok,
        "domain": domain,
        "domain_resolves": domain_resolves,
        "disposable": is_disposable,
        "verdict": confidence,
        "deliverable": confidence == "valid",
        "elapsed_ms": int((time.time() - started) * 1000),
    }
