"""Signed weather ground-truth feed — paid x402 MCP tool.

Weather is one of the most-bought data products on x402 (hugen.tokyo: 242 buyers
at $0.005, ~21.8K calls/30d) — but it ships UNSIGNED. This is the same feed with
the one thing the market lacks: an Ed25519 signature over the exact reading.

    "the current weather at THIS place / lat-lon, as actually fetched now,
     signed so a third party can prove it wasn't altered after the fact."

Why signed weather matters (the buyer): parametric-insurance triggers,
prediction-market resolvers, travel/logistics agents, and any flow that pays out
or acts on a weather fact need an observation they can VERIFY, not one a
counterparty could fabricate. Same "facts, not judgments" line as the rest of
Onyx — applied to the highest-volume simple-data category on x402.

Source: Open-Meteo (free, no API key). We observe and sign; we never invent.
Bright line: a real observation of public weather data. No persons, no identity.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from . import _onyx_sign

NAME = "onyx_weather_feed"
PRICE_USDC = "0.005"
TIER = "metered"
DESCRIPTION = (
    "Signed weather ground-truth. Give a place name (or latitude+longitude); get "
    "the real current temperature, humidity, wind, and conditions as actually "
    "fetched now — Ed25519-signed so any third party can verify the reading "
    "offline (tamper -> rejected). Use for parametric-insurance triggers, "
    "prediction-market resolution, travel/logistics agents, or any action that "
    "pays out on a weather fact and needs proof it wasn't fabricated."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "place": {"type": "string", "description": "Place name to geocode, e.g. 'Athens, GR' or 'Tokyo'. Use this OR latitude+longitude."},
        "latitude": {"type": "number", "description": "Latitude (-90..90). Use with longitude instead of place for an exact point."},
        "longitude": {"type": "number", "description": "Longitude (-180..180)."},
    },
    "required": [],
}

_UA = "onyx-weather/1.0 (+https://onyx-actions.onrender.com)"
_TIMEOUT = 12.0
_GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST = "https://api.open-meteo.com/v1/forecast"

# WMO weather interpretation codes -> plain text
_WMO = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "depositing rime fog", 51: "light drizzle", 53: "moderate drizzle",
    55: "dense drizzle", 56: "light freezing drizzle", 57: "dense freezing drizzle",
    61: "slight rain", 63: "moderate rain", 65: "heavy rain", 66: "light freezing rain",
    67: "heavy freezing rain", 71: "slight snow", 73: "moderate snow", 75: "heavy snow",
    77: "snow grains", 80: "slight rain showers", 81: "moderate rain showers",
    82: "violent rain showers", 85: "slight snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm with slight hail", 99: "thunderstorm with heavy hail",
}


def _get_json(url: str, params: dict) -> dict:
    full = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(full, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _geocode(place: str) -> dict | None:
    # Open-Meteo geocoder matches a single token poorly with suffixes like
    # "Athens, GR" — try the full string, then fall back to the part before the
    # first comma (the city), so "Athens, GR" still resolves.
    candidates = [place]
    if "," in place:
        candidates.append(place.split(",", 1)[0].strip())
    results = []
    for name in candidates:
        if not name:
            continue
        data = _get_json(_GEOCODE, {"name": name, "count": 1, "language": "en", "format": "json"})
        results = data.get("results") or []
        if results:
            break
    if not results:
        return None
    g = results[0]
    return {
        "latitude": g.get("latitude"), "longitude": g.get("longitude"),
        "resolved_name": ", ".join(x for x in (g.get("name"), g.get("admin1"), g.get("country")) if x),
    }


def run(place: str = "", latitude: float | None = None, longitude: float | None = None, **_: object) -> dict:
    observed_at = int(time.time())
    resolved_name = None
    place = (place or "").strip()

    try:
        if latitude is None or longitude is None:
            if not place:
                raise ValueError("provide place, or latitude+longitude")
            geo = _geocode(place)
            if not geo:
                return {"ok": False, "error": "place_not_found", "place": place, "observed_at": observed_at}
            latitude, longitude, resolved_name = geo["latitude"], geo["longitude"], geo["resolved_name"]
        lat, lon = float(latitude), float(longitude)
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("latitude/longitude out of range")
        data = _get_json(_FORECAST, {
            "latitude": lat, "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,"
                       "wind_speed_10m,wind_direction_10m,weather_code,is_day,precipitation",
            "timezone": "UTC",
        })
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": "http_error", "http_status": e.code, "observed_at": observed_at}
    except (urllib.error.URLError, TimeoutError) as e:
        return {"ok": False, "error": "fetch_failed", "detail": str(e)[:160], "observed_at": observed_at}
    except ValueError as e:
        raise

    cur = data.get("current") or {}
    units = data.get("current_units") or {}
    code = cur.get("weather_code")
    result = {
        "ok": True,
        "observed_at": observed_at,
        "observed_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(observed_at)),
        "place": place or None,
        "resolved_name": resolved_name,
        "latitude": lat,
        "longitude": lon,
        "temperature_c": cur.get("temperature_2m"),
        "apparent_temperature_c": cur.get("apparent_temperature"),
        "relative_humidity_pct": cur.get("relative_humidity_2m"),
        "wind_speed": cur.get("wind_speed_10m"),
        "wind_speed_unit": units.get("wind_speed_10m"),
        "wind_direction_deg": cur.get("wind_direction_10m"),
        "precipitation": cur.get("precipitation"),
        "weather_code": code,
        "conditions": _WMO.get(code, "unknown"),
        "is_day": bool(cur.get("is_day")),
        "source": "open-meteo",
        "vantage": "onyx-observer",
    }
    return _onyx_sign.attest(result, tool=NAME)


run.__when_to_use__ = (
    "Before an agent acts or pays out on a weather fact — parametric insurance "
    "triggers, prediction-market resolution, travel/logistics decisions — where "
    "it needs a reading it can cryptographically verify, not one a counterparty "
    "could fabricate."
)
run.__vs_alternatives__ = (
    "Raw weather APIs (and other x402 weather feeds) return an UNSIGNED number "
    "the caller must trust blindly. This returns the same observation Ed25519-"
    "signed and timestamped, so any third party can verify offline that Onyx "
    "observed exactly this — tamper and verification rejects it."
)
run.__example_request__ = {"place": "Athens, GR"}
run.__example_response__ = {
    "ok": True, "resolved_name": "Athens, Attica, Greece",
    "temperature_c": 31.4, "conditions": "clear sky", "relative_humidity_pct": 38,
    "wind_speed": 12.0, "source": "open-meteo",
}
