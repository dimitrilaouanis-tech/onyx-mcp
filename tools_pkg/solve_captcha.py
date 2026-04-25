"""Captcha OCR tool — ddddocr backed."""
from __future__ import annotations

import base64
import io
import time
from typing import Optional

import ddddocr
import httpx
from PIL import Image

NAME = "onyx_solve_captcha"
PRICE_USDC = "0.003"
TIER = "metered"
DESCRIPTION = (
    "Solve an image-based text captcha. OCR via ddddocr (~30ms, 70-90% "
    "accuracy on standard web captchas)."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "image_url": {"type": "string", "description": "URL to fetch"},
        "image_b64": {"type": "string", "description": "Base64-encoded image bytes"},
    },
    "anyOf": [{"required": ["image_url"]}, {"required": ["image_b64"]}],
}

_OCR = ddddocr.DdddOcr(show_ad=False)


def run(image_url: Optional[str] = None,
        image_b64: Optional[str] = None,
        **_: object) -> dict:
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
    return {
        "answer": answer,
        "source": "onyx.ddddocr",
        "elapsed_ms": int((time.time() - started) * 1000),
        "bytes": len(img_bytes),
    }
