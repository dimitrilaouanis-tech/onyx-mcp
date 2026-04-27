"""Domain whois via RDAP (rdap.org public mirror)."""
from __future__ import annotations

import time

import httpx

NAME = "onyx_whois"
PRICE_USDC = "0.001"
TIER = "metered"
DESCRIPTION = (
    "Domain whois via the modern RDAP protocol — registrar, creation/expiry "
    "dates, nameservers, registrant country, status flags. Use to vet a "
    "domain before agents transact with it (newly registered = higher fraud "
    "risk), check trademark conflicts, or confirm ownership transfer. Powered "
    "by rdap.org (no API key, free tier). ~200-500ms typical."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "domain": {"type": "string", "description": "Domain name, e.g. example.com"},
    },
    "required": ["domain"],
}


def run(domain: str, **_: object) -> dict:
    domain = (domain or "").strip().lower().lstrip(".").rstrip(".")
    if not domain or "." not in domain:
        raise ValueError("domain required, e.g. example.com")
    started = time.time()
    r = httpx.get(f"https://rdap.org/domain/{domain}", timeout=12.0,
                  follow_redirects=True,
                  headers={"Accept": "application/rdap+json"})
    if r.status_code == 404:
        return {"domain": domain, "registered": False,
                "elapsed_ms": int((time.time() - started) * 1000)}
    r.raise_for_status()
    d = r.json()
    events = {e.get("eventAction"): e.get("eventDate") for e in d.get("events", [])}
    registrar = None
    for ent in d.get("entities", []):
        if "registrar" in ent.get("roles", []):
            for v in ent.get("vcardArray", [None, []])[1] or []:
                if v[0] == "fn":
                    registrar = v[3]
                    break
    nameservers = [ns.get("ldhName") for ns in d.get("nameservers", []) if ns.get("ldhName")]
    return {
        "domain": d.get("ldhName") or domain,
        "registered": True,
        "registrar": registrar,
        "created": events.get("registration"),
        "updated": events.get("last changed"),
        "expires": events.get("expiration"),
        "nameservers": nameservers,
        "status": d.get("status", []),
        "elapsed_ms": int((time.time() - started) * 1000),
    }
