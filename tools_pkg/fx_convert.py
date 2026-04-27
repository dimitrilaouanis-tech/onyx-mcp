"""FX rate conversion via open.er-api.com free tier (no key)."""
from __future__ import annotations

import os
import time

import httpx

NAME = "onyx_fx_convert"
PRICE_USDC = "0.0008"
TIER = "metered"
DESCRIPTION = (
    "Convert between any two fiat currencies (USD, EUR, GBP, JPY, BRL, "
    "USDC-equivalent, 160+ ISO-4217 codes) at the current mid-market rate. "
    "Returns both the rate and the converted amount, plus the rate's last "
    "update timestamp. Use when an agent needs to price a service in another "
    "currency, normalize multi-currency invoices, or convert x402 USDC "
    "amounts to local fiat for human-readable receipts. Powered by "
    "open.er-api.com (free tier, no key). ~150-400ms. Demo mode returns "
    "USD-EUR @ 0.92 for testing."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "from": {"type": "string", "description": "ISO-4217 source currency code"},
        "to": {"type": "string", "description": "ISO-4217 target currency code"},
        "amount": {"type": "number", "default": 1.0},
    },
    "required": ["from", "to"],
}


def _demo_mode() -> bool:
    return os.environ.get("ONYX_DEMO_MODE", "1") == "1"


def run(**kwargs: object) -> dict:
    src = str(kwargs.get("from", "")).upper().strip()
    dst = str(kwargs.get("to", "")).upper().strip()
    try:
        amount = float(kwargs.get("amount", 1.0))
    except (TypeError, ValueError):
        raise ValueError("amount must be numeric")
    if not src or not dst:
        raise ValueError("from and to currency codes required")
    started = time.time()
    if _demo_mode():
        rate = 0.92 if (src == "USD" and dst == "EUR") else 1.0
        return {
            "from": src, "to": dst, "amount": amount,
            "rate": rate, "converted": round(amount * rate, 4),
            "as_of": "2026-04-27T00:00:00Z",
            "source": "onyx.fx_demo", "demo": True,
            "elapsed_ms": int((time.time() - started) * 1000),
        }
    r = httpx.get(f"https://open.er-api.com/v6/latest/{src}", timeout=8.0)
    r.raise_for_status()
    d = r.json()
    if d.get("result") != "success":
        return {"error": d.get("error-type", "fx lookup failed"), "from": src, "to": dst}
    rate = d.get("rates", {}).get(dst)
    if rate is None:
        return {"error": f"unknown currency: {dst}", "from": src, "to": dst}
    return {
        "from": src, "to": dst, "amount": amount,
        "rate": rate, "converted": round(amount * rate, 4),
        "as_of": d.get("time_last_update_utc"),
        "source": "onyx.er-api",
        "elapsed_ms": int((time.time() - started) * 1000),
    }
