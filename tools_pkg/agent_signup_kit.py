"""Bundled signup-flow tool — agents pay once, get the whole pre-flight check.

The OATP playbook (430 paying agents on a single $0.10 tx_explainer endpoint)
proves agents prefer one tool that does the whole job over four they have to
compose. This bundles email+DNS+captcha+SMS into a single $0.058 call —
discounted ~7% vs. unit pricing — for agent runtimes that hit a signup wall
and need everything in one shot.
"""
from __future__ import annotations

import time

from . import dns_lookup, email_validate, solve_captcha, sms_verify

NAME = "onyx_agent_signup_kit"
PRICE_USDC = "0.058"
TIER = "metered"
DESCRIPTION = (
    "One-call signup-flow pre-flight for autonomous agents. Validates an "
    "email (syntax + DNS + disposable check), confirms the target domain "
    "resolves, optionally solves a captcha image, and optionally fetches an "
    "SMS OTP via real carrier SIM. Returns the consolidated pass/fail per "
    "step plus the OTP and captcha answer. Replaces four separate calls with "
    "one $0.058 USDC payment — saves agents ~7% vs unit pricing and a full "
    "round-trip per step. Ideal for browser agents at signup walls. Demo "
    "mode returns synthetic captcha + OTP so the payment loop is testable "
    "for free."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "email": {"type": "string", "description": "Email to validate"},
        "domain": {"type": "string", "description": "Service domain to confirm resolves"},
        "captcha_image_url": {"type": "string", "description": "Optional captcha image URL"},
        "captcha_image_b64": {"type": "string", "description": "Optional captcha base64"},
        "phone_number": {"type": "string", "description": "Optional phone for SMS OTP"},
    },
    "required": ["email"],
}


def run(email: str,
        domain: str | None = None,
        captcha_image_url: str | None = None,
        captcha_image_b64: str | None = None,
        phone_number: str | None = None,
        **_: object) -> dict:
    started = time.time()
    out: dict = {"ok": True, "email": None, "domain": None, "captcha": None, "sms": None}

    # 1) email
    try:
        out["email"] = email_validate.run(email=email)
        if not out["email"].get("deliverable"):
            out["ok"] = False
    except Exception as e:
        out["email"] = {"error": str(e)}
        out["ok"] = False

    # 2) domain DNS (defaults to email's domain if not provided)
    target = domain or (email.rsplit("@", 1)[-1] if "@" in (email or "") else None)
    if target:
        try:
            out["domain"] = dns_lookup.run(host=target)
            if not out["domain"].get("resolved"):
                out["ok"] = False
        except Exception as e:
            out["domain"] = {"error": str(e)}

    # 3) captcha (optional)
    if captcha_image_url or captcha_image_b64:
        try:
            out["captcha"] = solve_captcha.run(
                image_url=captcha_image_url, image_b64=captcha_image_b64
            )
        except Exception as e:
            out["captcha"] = {"error": str(e)}

    # 4) SMS (optional)
    if phone_number:
        try:
            out["sms"] = sms_verify.run(phone_number=phone_number)
        except Exception as e:
            out["sms"] = {"error": str(e)}

    out["elapsed_ms"] = int((time.time() - started) * 1000)
    out["unit_price_total"] = "0.0628"
    out["bundle_savings_pct"] = 7.6
    return out
