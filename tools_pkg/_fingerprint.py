"""Visitor fingerprint — a numerical value per visitor, derived from IP (+UA).

Lets Onyx tell claimants apart, distinguish a fresh chat, see "same network",
and ALARM on multi-claim attempts.

IMPORTANT (honest boundary): a fingerprint is an ADVISORY signal, never the
trust anchor. The cryptographic single-owner guarantee is proof-of-key (see
_claim_registry.claim — only the wallet's private key can claim an identity).
IPs are shared (NAT/household/VPN) and change, so we never LOCK an identity to
an IP; we record fingerprints for memory + abuse-detection only.

Three numbers, by design:
  - network_fp : stable per (ip, ua). A fresh chat from the SAME ip+client gives
                 the SAME number -> "this is the same network as before."
  - ip_fp      : stable per ip only (ignores client/UA).
  - visit_id   : UNIQUE per visit -> distinguishes individual checks even from
                 the same IP (a fresh chat always gets a new one).
"""
from __future__ import annotations

import hashlib
import os


def _first_ip(ip: str) -> str:
    # X-Forwarded-For may be "client, proxy1, proxy2" — the client is first.
    return (ip or "").split(",")[0].strip()


def network_fp(ip: str, ua: str = "") -> int:
    """48-bit stable fingerprint of (ip, client). Same ip+UA -> same number."""
    base = _first_ip(ip) + "|" + (ua or "")[:120]
    h = hashlib.sha256(base.encode("utf-8")).hexdigest()
    return int(h[:12], 16)


def ip_fp(ip: str) -> int:
    """48-bit stable fingerprint of the IP alone (any client at that IP)."""
    h = hashlib.sha256(_first_ip(ip).encode("utf-8")).hexdigest()
    return int(h[:12], 16)


def visit_id() -> str:
    """Unique per visit — a fresh chat (even same IP) gets a new one. 64-bit hex."""
    return os.urandom(8).hex()


def describe(ip: str, ua: str = "") -> dict:
    """The full visitor fingerprint surfaced to a caller."""
    return {
        "ip": _first_ip(ip) or None,
        "network_fp": network_fp(ip, ua),   # stable per ip+client
        "ip_fp": ip_fp(ip),                 # stable per ip only
        "visit_id": visit_id(),             # unique this visit
        "note": ("network_fp/ip_fp are stable per network (advisory only); "
                 "visit_id is unique per check. Ownership is proven by the wallet "
                 "key, never by IP."),
    }
