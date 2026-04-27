"""Parse User-Agent string into browser/OS/device structure."""
from __future__ import annotations

import re

NAME = "onyx_user_agent_parse"
PRICE_USDC = "0.0003"
TIER = "metered"
DESCRIPTION = (
    "Parse any HTTP User-Agent string into a structured record: browser "
    "name/version, OS name/version, device type (desktop/mobile/tablet/bot), "
    "rendering engine. Use for analytics, fraud scoring, or routing logic "
    "based on client capabilities. Stdlib regex only — works offline, no "
    "external lookups. <2ms."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "user_agent": {"type": "string", "description": "User-Agent header value"},
    },
    "required": ["user_agent"],
}

_BROWSERS = [
    ("Edge", re.compile(r"Edg(?:e|A|iOS)?/([\d.]+)")),
    ("Chrome", re.compile(r"Chrom(?:e|ium)/([\d.]+)")),
    ("Firefox", re.compile(r"Firefox/([\d.]+)")),
    ("Safari", re.compile(r"Version/([\d.]+).*Safari")),
    ("Opera", re.compile(r"OPR/([\d.]+)")),
]
_OSES = [
    ("Windows", re.compile(r"Windows NT ([\d.]+)")),
    ("macOS", re.compile(r"Mac OS X ([\d_.]+)")),
    ("iOS", re.compile(r"iPhone OS ([\d_.]+)|iPad.*OS ([\d_.]+)")),
    ("Android", re.compile(r"Android ([\d.]+)")),
    ("Linux", re.compile(r"Linux")),
]
_BOT = re.compile(r"bot|crawler|spider|slurp|googlebot|bingbot|yandex|baidu", re.IGNORECASE)
_MOBILE = re.compile(r"Mobile|Android|iPhone|iPod", re.IGNORECASE)
_TABLET = re.compile(r"iPad|Tablet", re.IGNORECASE)


def run(user_agent: str, **_: object) -> dict:
    ua = (user_agent or "").strip()
    if not ua:
        raise ValueError("user_agent required")
    browser, browser_ver = None, None
    for name, pat in _BROWSERS:
        m = pat.search(ua)
        if m:
            browser, browser_ver = name, m.group(1)
            break
    os_name, os_ver = None, None
    for name, pat in _OSES:
        m = pat.search(ua)
        if m:
            os_name = name
            os_ver = next((g for g in m.groups() if g), None)
            if os_ver:
                os_ver = os_ver.replace("_", ".")
            break
    if _BOT.search(ua):
        device = "bot"
    elif _TABLET.search(ua):
        device = "tablet"
    elif _MOBILE.search(ua):
        device = "mobile"
    else:
        device = "desktop"
    return {
        "user_agent": ua,
        "browser": browser, "browser_version": browser_ver,
        "os": os_name, "os_version": os_ver,
        "device": device,
        "is_bot": device == "bot",
    }
