"""IP geolocation via ip-api.com free tier (no key needed)."""
from __future__ import annotations

import os
import time

import httpx

NAME = "onyx_ip_geolocate"
PRICE_USDC = "0.0008"
TIER = "metered"
DESCRIPTION = (
    "Geolocate any public IPv4/IPv6 address — country, region, city, lat/lon, "
    "timezone, ISP, ASN, mobile/proxy/hosting flags. Useful for filtering "
    "traffic by country, detecting datacenter/VPN egress, fraud scoring, or "
    "deciding which regional endpoint to route an agent through. Backed by "
    "ip-api.com (free tier, ~1k requests/min). ~80-200ms typical. Demo mode "
    "returns a plausible US record so the payment loop can be tested without "
    "burning the upstream rate limit."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "ip": {"type": "string", "description": "IPv4 or IPv6 address"},
    },
    "required": ["ip"],
}


def _demo_mode() -> bool:
    return os.environ.get("ONYX_DEMO_MODE", "1") == "1"


def run(ip: str, **_: object) -> dict:
    ip = (ip or "").strip()
    if not ip:
        raise ValueError("ip required")
    started = time.time()
    if _demo_mode():
        return {
            "ip": ip, "country": "US", "country_code": "US",
            "region": "California", "city": "Mountain View",
            "lat": 37.422, "lon": -122.084, "timezone": "America/Los_Angeles",
            "isp": "Google LLC", "asn": "AS15169",
            "mobile": False, "proxy": False, "hosting": True,
            "source": "onyx.geo_demo", "demo": True,
            "elapsed_ms": int((time.time() - started) * 1000),
        }
    fields = "status,country,countryCode,region,regionName,city,lat,lon,timezone,isp,as,mobile,proxy,hosting,query"
    r = httpx.get(f"http://ip-api.com/json/{ip}?fields={fields}", timeout=8.0)
    r.raise_for_status()
    d = r.json()
    if d.get("status") != "success":
        return {"ip": ip, "error": d.get("message", "lookup failed")}
    return {
        "ip": d.get("query"), "country": d.get("country"),
        "country_code": d.get("countryCode"), "region": d.get("regionName"),
        "city": d.get("city"), "lat": d.get("lat"), "lon": d.get("lon"),
        "timezone": d.get("timezone"), "isp": d.get("isp"),
        "asn": d.get("as"), "mobile": d.get("mobile"),
        "proxy": d.get("proxy"), "hosting": d.get("hosting"),
        "source": "onyx.ip-api",
        "elapsed_ms": int((time.time() - started) * 1000),
    }
