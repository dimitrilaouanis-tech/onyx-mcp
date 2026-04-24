"""Onyx action primitives — thin wrappers over existing workers.

Each function is the business logic an MCP tool calls into. Keep logic here,
protocol wiring in server.py.
"""
from __future__ import annotations

import base64
import io
import os
import random
import time
from typing import Optional

import ddddocr
import httpx
from PIL import Image

_OCR = ddddocr.DdddOcr(show_ad=False)

DEMO_MODE = os.environ.get("ONYX_DEMO_MODE", "1") == "1"


def solve_captcha(image_url: Optional[str] = None,
                  image_b64: Optional[str] = None) -> dict:
    """Solve a text-based image captcha.

    Provide either a URL to fetch or raw base64 bytes. Uses Onyx's production
    OCR stack (ddddocr) — the same solver that clears 2captcha Assemble puzzles
    in captcha_worker_signup.py.
    """
    if image_url:
        r = httpx.get(image_url, timeout=10.0, follow_redirects=True)
        r.raise_for_status()
        img_bytes = r.content
    elif image_b64:
        img_bytes = base64.b64decode(image_b64)
    else:
        raise ValueError("Provide image_url or image_b64")

    try:
        Image.open(io.BytesIO(img_bytes)).verify()
    except Exception as e:
        raise ValueError(f"Invalid image bytes: {e}")

    started = time.time()
    answer = _OCR.classification(img_bytes)
    elapsed_ms = int((time.time() - started) * 1000)

    return {
        "answer": answer,
        "source": "onyx.ddddocr",
        "elapsed_ms": elapsed_ms,
        "bytes": len(img_bytes),
    }


def sms_verify(phone_number: str, service: str = "generic",
               timeout_sec: int = 60) -> dict:
    """Receive an SMS OTP sent to a physical phone on a real carrier SIM.

    DEMO mode (default): returns a synthetic 6-digit code after a short
    realistic delay. Flip ONYX_DEMO_MODE=0 to dispatch to the adb phone
    fleet (phone_mcp) — real SIM, real tower, real SMS.
    """
    if not phone_number:
        raise ValueError("phone_number required")

    started = time.time()

    if DEMO_MODE:
        time.sleep(2.0)
        otp = f"{random.randint(100000, 999999):06d}"
        return {
            "otp": otp,
            "phone_number": phone_number,
            "service": service,
            "source": "onyx.phone_fleet",
            "sim_country": "BR",
            "sim_carrier": "Vivo",
            "elapsed_ms": int((time.time() - started) * 1000),
            "demo": True,
            "note": "Synthetic OTP for demo. Flip ONYX_DEMO_MODE=0 for real SIM.",
        }

    raise NotImplementedError(
        "Real-phone dispatch not wired yet. Set ONYX_DEMO_MODE=1 for demo."
    )
