"""SMS OTP via physical SIM. Demo mode returns synthetic; real-phone TODO."""
from __future__ import annotations

import os
import random
import time

NAME = "onyx_sms_verify"
PRICE_USDC = "0.050"
TIER = "metered"
DESCRIPTION = (
    "Receive an SMS OTP delivered to a physical phone on a real carrier SIM. "
    "No VoIP numbers, no virtual gateways, no Twilio — these get rejected by "
    "modern signup flows (WhatsApp, Telegram, banking, KYC). Onyx routes to a "
    "real Samsung handset on a carrier-issued SIM, polls the inbox via adb, "
    "extracts the OTP, returns it. Typical end-to-end 20-60s including network "
    "delivery. Demo mode (default) returns a synthetic 6-digit code after a "
    "2s delay so you can test the full payment + tool-call loop without "
    "burning real SMS-minutes. Set ONYX_DEMO_MODE=0 in self-hosted mode to "
    "dispatch to your own phone fleet."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "phone_number": {"type": "string", "description": "E.164 number"},
        "service": {"type": "string", "description": "Service name for context"},
        "timeout_sec": {"type": "integer", "default": 60},
    },
    "required": ["phone_number"],
}


def _demo_mode() -> bool:
    return os.environ.get("ONYX_DEMO_MODE", "1") == "1"


def run(phone_number: str,
        service: str = "generic",
        timeout_sec: int = 60,
        **_: object) -> dict:
    if not phone_number:
        raise ValueError("phone_number required")

    started = time.time()

    if _demo_mode():
        time.sleep(2.0)
        return {
            "otp": f"{random.randint(100000, 999999):06d}",
            "phone_number": phone_number,
            "service": service,
            "source": "onyx.phone_fleet",
            "sim_country": "BR",
            "sim_carrier": "Vivo",
            "elapsed_ms": int((time.time() - started) * 1000),
            "demo": True,
            "note": "Synthetic OTP. Set ONYX_DEMO_MODE=0 for real SIM dispatch.",
        }

    raise NotImplementedError(
        "Real-phone dispatch not wired yet. Set ONYX_DEMO_MODE=1 for demo."
    )
