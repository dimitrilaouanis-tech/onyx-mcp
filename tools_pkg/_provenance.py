"""Shared SSRF-hardened fetch + provenance recorder for the ground-truth oracles.

Two moat-protecting jobs:
1. **SSRF guard** — an attacker must not be able to point an oracle (via a URL or
   a redirect) at internal/metadata endpoints. We resolve the host and reject
   private/loopback/link-local + the IPv6 re-encoding bypasses (6to4, NAT64,
   site-local) that defeat naive IPv4-only filters (CVE-2026-44430 class), and
   we re-validate on EVERY redirect hop.
2. **Provenance** — every fetch returns a record (final_url, http_status,
   content sha256, fetched_at, bytes) that the oracle embeds in its SIGNED
   verdict. So the signature commits to *what source, observed how, when* — not
   just the extracted value. A spoofed source is then honest + independently
   checkable ("I observed X at URL Y, content-hash Z, at time T"), which is the
   facts-not-judgments contract.

Stdlib-only. Underscore-prefixed -> not an auto-discovered tool.
"""
from __future__ import annotations

import hashlib
import ipaddress
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

_UA = "OnyxOracle/1 (+https://onyx-actions.onrender.com)"
_TIMEOUT = 8.0
_MAX_BYTES = 2_000_000
_MAX_REDIRECTS = 4


class SSRFBlocked(Exception):
    pass


def _ip_blocked(ip: ipaddress._BaseAddress) -> bool:
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
        return True
    # IPv6 re-encodings of IPv4 that smuggle past v4-only filters
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped and _ip_blocked(ip.ipv4_mapped):
            return True
        if ip.sixtofour and _ip_blocked(ip.sixtofour):
            return True
        # NAT64 64:ff9b::/96 and 64:ff9b:1::/48, site-local fec0::/10
        for net in ("64:ff9b::/96", "64:ff9b:1::/48", "fec0::/10"):
            if ip in ipaddress.ip_network(net):
                return True
    # cloud metadata
    if str(ip) in ("169.254.169.254", "fd00:ec2::254"):
        return True
    return False


def _host_is_safe(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False
    if not infos:
        return False
    for *_, sa in infos:
        try:
            ip = ipaddress.ip_address(sa[0])
        except ValueError:
            return False
        if _ip_blocked(ip):
            return False
    return True


def safe_fetch(url: str, *, timeout: float = _TIMEOUT, max_bytes: int = _MAX_BYTES) -> tuple[int, str, dict]:
    """SSRF-guarded HTTP(S) GET with per-hop revalidation. Returns
    (status, text, provenance). Raises SSRFBlocked on a disallowed target."""
    fetched_at = int(time.time())
    current = url
    hops = []
    for _ in range(_MAX_REDIRECTS + 1):
        parsed = urllib.parse.urlparse(current)
        if parsed.scheme not in ("http", "https"):
            raise SSRFBlocked(f"scheme_not_allowed:{parsed.scheme}")
        host = parsed.hostname or ""
        if not _host_is_safe(host):
            raise SSRFBlocked(f"host_blocked:{host}")
        req = urllib.request.Request(
            current, headers={"User-Agent": _UA, "Accept": "text/html,application/json,*/*"}
        )

        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None  # we handle redirects manually so we can re-validate each hop

        opener = urllib.request.build_opener(_NoRedirect)
        try:
            resp = opener.open(req, timeout=timeout)
            status = resp.status
            raw = resp.read(max_bytes)
            text = raw.decode("utf-8", "replace")
            final_url = resp.geturl()
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308) and e.headers.get("Location"):
                current = urllib.parse.urljoin(current, e.headers["Location"])
                hops.append(current)
                continue
            status, raw, text, final_url = e.code, b"", "", current
        prov = {
            "source_url": url,
            "final_url": final_url,
            "redirect_hops": hops,
            "redirected_off_host": (urllib.parse.urlparse(final_url).hostname or "")
                                   != (urllib.parse.urlparse(url).hostname or ""),
            "http_status": status,
            "method": "ssrf_guarded_http_get",
            "content_sha256": "sha256:" + hashlib.sha256(raw if raw else text.encode()).hexdigest(),
            "bytes": len(raw) if raw else len(text),
            "fetched_at": fetched_at,
        }
        return status, text, prov
    raise SSRFBlocked("too_many_redirects")
