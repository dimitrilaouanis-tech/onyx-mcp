"""Onyx action primitives — thin wrappers over existing workers.

Each function is the business logic an MCP tool calls into. Keep logic here,
protocol wiring in server.py.
"""
from __future__ import annotations

import base64
import io
import time
from typing import Optional

import ddddocr
import httpx
from PIL import Image

_OCR = ddddocr.DdddOcr(show_ad=False)


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
