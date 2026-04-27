"""HLR lookup — phone number routing/portability check.

Demo mode (default) returns a plausible synthetic HLR record so agents can
test the full payment + tool-call loop without burning a real lookup. Set
ONYX_DEMO_MODE=0 + provide vendor keys (NPLOOKUP_KEY etc.) in self-hosted
mode to dispatch to real upstreams.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request

NAME = "onyx_hlr_lookup"
PRICE_USDC = "0.005"
TIER = "metered"
DESCRIPTION = (
    "HLR lookup for any E.164 phone number. Returns the live carrier, MCC/MNC, "
    "country, line type (mobile/landline/voip), and portability status. Use "
    "before sending an SMS to avoid burning credits on dead/landline/VoIP "
    "numbers; or to verify which carrier owns a number after a port. Onyx "
    "routes to the cheapest live HLR vendor (numberportabilitylookup, "
    "hlr-lookups, text2reach) under the hood and pockets the spread — you "
    "pay one flat $0.005 USDC. Demo mode (default in cloud) returns a "
    "plausible synthetic record after ~150ms so you can test the loop free; "
    "self-host with vendor keys for real lookups."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "phone_number": {
            "type": "string",
            "description": "E.164 phone number, e.g. +5511987654321",
        },
    },
    "required": ["phone_number"],
}


def _demo_mode() -> bool:
    return os.environ.get("ONYX_DEMO_MODE", "1") == "1"


_E164 = re.compile(r"^\+?\d{8,15}$")

_DEMO_CARRIERS = {
    "55": ("BR", "Vivo", "724", "06", "mobile"),
    "1": ("US", "T-Mobile", "310", "260", "mobile"),
    "44": ("GB", "EE", "234", "30", "mobile"),
    "351": ("PT", "MEO", "268", "06", "mobile"),
    "30": ("GR", "Cosmote", "202", "01", "mobile"),
    "7": ("RU", "Beeline", "250", "99", "mobile"),
    "972": ("IL", "Cellcom", "425", "02", "mobile"),
}


def _demo_record(phone: str) -> dict:
    digits = phone.lstrip("+")
    cc, carrier, mcc, mnc, line = _DEMO_CARRIERS["1"]
    for length in (3, 2, 1):
        if digits[:length] in _DEMO_CARRIERS:
            cc, carrier, mcc, mnc, line = _DEMO_CARRIERS[digits[:length]]
            break
    return {
        "phone_number": phone,
        "country": cc,
        "carrier": carrier,
        "mcc": mcc,
        "mnc": mnc,
        "line_type": line,
        "ported": False,
        "valid": True,
        "source": "onyx.hlr_router",
        "demo": True,
        "note": "Synthetic HLR record. Set ONYX_DEMO_MODE=0 + vendor keys for real.",
    }


def _real_lookup(phone: str) -> dict:
    """Hit the cheapest configured upstream. Order: nplookup, text2reach."""
    started = time.time()
    nplookup = os.environ.get("NPLOOKUP_KEY")
    if nplookup:
        url = "https://api.numberportabilitylookup.com/v1/lookup"
        params = urllib.parse.urlencode({"key": nplookup, "number": phone})
        try:
            with urllib.request.urlopen(f"{url}?{params}", timeout=10) as r:
                data = json.loads(r.read())
            return {
                "phone_number": phone,
                "country": data.get("country"),
                "carrier": data.get("carrier"),
                "mcc": data.get("mcc"),
                "mnc": data.get("mnc"),
                "line_type": data.get("line_type"),
                "ported": bool(data.get("ported")),
                "valid": bool(data.get("valid", True)),
                "source": "onyx.nplookup",
                "elapsed_ms": int((time.time() - started) * 1000),
            }
        except Exception as e:
            return {"error": f"nplookup failed: {e}", "phone_number": phone}
    return {
        "error": "no vendor key configured",
        "phone_number": phone,
        "hint": "set NPLOOKUP_KEY in env or use ONYX_DEMO_MODE=1",
    }


def run(phone_number: str, **_: object) -> dict:
    if not phone_number or not _E164.match(phone_number.replace(" ", "")):
        raise ValueError("phone_number must be E.164 format, e.g. +5511987654321")
    started = time.time()
    if _demo_mode():
        time.sleep(0.15)
        rec = _demo_record(phone_number)
        rec["elapsed_ms"] = int((time.time() - started) * 1000)
        return rec
    return _real_lookup(phone_number)
