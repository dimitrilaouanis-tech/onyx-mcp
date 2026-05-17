"""Simulate an x402 payment flow against any paid endpoint — without actually
paying. Hits the introspection card (or live 402 challenge), parses the
paymentRequirements, generates a template X-PAYMENT payload an agent would
sign, and explains the next step. Free tier — pure dev tooling.

This is the companion to onyx_verify_explain: simulate BEFORE signing,
diagnose AFTER signing. Together they cover the whole client-side x402 loop.
"""
from __future__ import annotations

import base64
import ipaddress
import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

NAME = "onyx_x402_simulate"
PRICE_USDC = "0"
TIER = "free"
DESCRIPTION = (
    "Simulate an x402 v2 payment flow against any paid endpoint. Fetches the "
    "402 challenge (or introspection card), parses paymentRequirements, "
    "generates a template X-PAYMENT payload with the exact fields an agent "
    "would need to sign (EIP-3009 authorization shape, validBefore window, "
    "asset address, recipient), and returns next-step guidance. Pure "
    "simulation — no keys, no signing, no payment. SSRF-hardened."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "endpoint_url": {
            "type": "string",
            "description": "Full URL of the paid endpoint to simulate against (e.g. https://onyx-actions.onrender.com/v1/onyx_aml_screen).",
        },
        "method": {
            "type": "string",
            "enum": ["GET", "POST"],
            "default": "GET",
            "description": "GET hits the introspection card (works even on unpaid endpoints); POST hits the live 402 challenge (works on every paid endpoint).",
        },
        "signer_address": {
            "type": "string",
            "description": "Address that would sign the EIP-3009 authorization. Used to fill the 'from' field in the template payment payload. Optional — defaults to 0x0...01.",
        },
    },
    "required": ["endpoint_url"],
}


def _is_public(host: str) -> tuple[bool, str]:
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        return False, f"DNS fail: {e}"
    for fam, _, _, _, sa in infos:
        try:
            ip = ipaddress.ip_address(sa[0])
        except ValueError:
            return False, f"bad ip {sa[0]}"
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_multicast or ip.is_reserved):
            return False, f"non-public {sa[0]}"
    return True, "ok"


def _decode_challenge(b64: str) -> dict | None:
    try:
        raw = base64.b64decode(b64, validate=True)
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def _fetch_challenge(url: str, method: str, timeout: float = 10.0) -> dict:
    """Return {challenge: dict|None, status, content_type, raw_body, source}."""
    try:
        req = urllib.request.Request(
            url, method=method,
            data=b"{}" if method == "POST" else None,
            headers={
                "User-Agent": "onyx-x402-simulate/1.0",
                "Accept": "application/json",
                **({"Content-Type": "application/json"} if method == "POST" else {}),
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(16384)
            return _shape_challenge(resp, body, method)
    except urllib.error.HTTPError as e:
        body = e.read(16384) if e else b""
        # 402 with body is the happy path for POST
        return _shape_challenge(e, body, method)
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as e:
        return {"challenge": None, "status": None,
                "content_type": "", "raw_body": "", "source": method,
                "error": str(e)[:200]}


def _shape_challenge(resp, body: bytes, method: str) -> dict:
    ctype = resp.headers.get("Content-Type", "") if resp.headers else ""
    # 1) `Payment-Required` header carries the x402 v2 challenge as base64
    pr_header = resp.headers.get("payment-required") if resp.headers else None
    challenge = None
    source = None
    if pr_header:
        challenge = _decode_challenge(pr_header)
        if challenge:
            source = "header:payment-required"
    if challenge is None and "json" in ctype.lower():
        try:
            j = json.loads(body.decode("utf-8", "replace"))
            # Either /v1/<tool> GET introspection (has paymentRequirements-shaped fields)
            # or a direct JSON 402 body
            if "accepts" in j and "x402Version" in j:
                challenge = j
                source = "body:json"
            elif "input_schema" in j and "settle_to" in j:
                # introspection card — synthesize challenge shape
                challenge = _introspection_to_challenge(j)
                source = "introspection_card"
        except Exception:
            pass
    return {
        "challenge": challenge,
        "status": resp.status if hasattr(resp, "status") else getattr(resp, "code", None),
        "content_type": ctype,
        "raw_body": body[:1000].decode("utf-8", "replace"),
        "source": source or "none",
    }


def _introspection_to_challenge(card: dict) -> dict:
    """Build a synthetic x402 v2 challenge from an /v1/<tool> GET introspection card."""
    return {
        "x402Version": 2,
        "resource": {"url": card.get("endpoint"), "description": card.get("description", "")[:200]},
        "accepts": [{
            "scheme": "exact",
            "network": _network_to_caip2(card.get("network")),
            "asset": _asset_for_network(card.get("network")),
            "amount": str(int(round(float(card.get("price_usdc", 0)) * 1_000_000))),
            "payTo": card.get("settle_to"),
            "maxTimeoutSeconds": 300,
            "extra": {
                "name": "USDC", "version": "2",
                "tool": card.get("name"),
            },
        }],
    }


def _network_to_caip2(net: str | None) -> str:
    if not net:
        return "eip155:8453"
    t = (net or "").lower()
    if "sepolia" in t:
        return "eip155:84532"
    if "base" in t:
        return "eip155:8453"
    if "polygon" in t:
        return "eip155:137"
    if "arbitrum" in t:
        return "eip155:42161"
    return net  # assume caller already used CAIP-2


def _asset_for_network(net: str | None) -> str:
    caip = _network_to_caip2(net)
    table = {
        "eip155:8453":  "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
        "eip155:84532": "0x036cbd53842c5426634e7929541ec2318f3dcf7e",
        "eip155:1":     "0xa0b86991c6218b266c1d19d4a2e9eb0ce3606eb48",
        "eip155:137":   "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359",
        "eip155:42161": "0xaf88d065e77c8cc2239327c5edb3a432268e5831",
    }
    return table.get(caip, "")


def _build_template_payment(challenge: dict, signer: str) -> dict:
    accepts = (challenge.get("accepts") or [{}])[0]
    now = int(time.time())
    return {
        "x402Version": 2,
        "scheme": accepts.get("scheme", "exact"),
        "network": accepts.get("network"),
        "payload": {
            "signature": "0x" + "00" * 65 + "  // <-- agent signs EIP-712 typed data here",
            "authorization": {
                "from":        signer,
                "to":          accepts.get("payTo"),
                "value":       accepts.get("amount"),
                "validAfter":  "0",
                "validBefore": str(now + (accepts.get("maxTimeoutSeconds") or 300) - 5),
                "nonce":       "0x" + "11" * 32 + "  // <-- 32 random bytes per call",
            },
        },
    }


def run(
    endpoint_url: str,
    method: str = "GET",
    signer_address: str | None = None,
    **_: object,
) -> dict:
    if not isinstance(endpoint_url, str) or not endpoint_url:
        raise ValueError("endpoint_url is required")
    parsed = urllib.parse.urlparse(endpoint_url.strip())
    if parsed.scheme not in ("http", "https"):
        raise ValueError("endpoint_url must be http:// or https://")
    if not parsed.netloc:
        raise ValueError("endpoint_url missing host")
    host = parsed.hostname or ""
    ok, reason = _is_public(host)
    if not ok:
        return {"ok": False, "error": reason, "endpoint_url": endpoint_url}

    method = method.upper()
    if method not in ("GET", "POST"):
        method = "GET"

    fetched = _fetch_challenge(endpoint_url, method)
    challenge = fetched.get("challenge")

    out: dict = {
        "ok": True,
        "endpoint_url": endpoint_url,
        "method_used": method,
        "fetch_status": fetched.get("status"),
        "fetch_source": fetched.get("source"),
        "fetch_error": fetched.get("error"),
        "challenge": challenge,
    }

    if not challenge:
        out["ok"] = False
        out["explain"] = (
            "Could not derive an x402 challenge from this endpoint. "
            "Try method='POST' for a paid endpoint, or method='GET' on /v1/<tool> "
            "for an introspection card. Raw body preview attached."
        )
        out["raw_body_preview"] = fetched.get("raw_body", "")[:500]
        return out

    signer = signer_address or "0x0000000000000000000000000000000000000001"
    template = _build_template_payment(challenge, signer)
    accepts = (challenge.get("accepts") or [{}])[0]
    amt = accepts.get("amount") or "0"
    try:
        usdc = int(amt) / 1_000_000
    except (TypeError, ValueError):
        usdc = None

    out["price_usdc"] = usdc
    out["network"] = accepts.get("network")
    out["asset"] = accepts.get("asset")
    out["pay_to"] = accepts.get("payTo")
    out["max_timeout_seconds"] = accepts.get("maxTimeoutSeconds")
    out["template_payment_payload"] = template
    out["x_payment_header_template_b64"] = base64.b64encode(
        json.dumps({k: v for k, v in template.items()}).encode()
    ).decode()
    out["next_steps"] = [
        "1. Sign the EIP-3009 TransferWithAuthorization message with your wallet, using the EIP-712 domain {name:'USDC', version:'2', chainId:<from network>, verifyingContract:<asset>}.",
        "2. Replace the signature placeholder in template_payment_payload.payload.signature with your 0x-prefixed 65-byte signature.",
        "3. Replace the nonce placeholder with os.urandom(32).hex() (must be unique per call).",
        "4. Base64-encode the JSON of the completed paymentPayload and send it as either:",
        "   - HTTP header `PAYMENT-SIGNATURE: <b64>` (recommended for v2)",
        "   - HTTP header `X-PAYMENT: <b64>` (v1 compat; some servers still accept)",
        "5. POST to the same endpoint_url. Server forwards to facilitator /verify, then /settle. Successful response = 200 with `X-PAYMENT-RESPONSE` header containing the settlement receipt.",
        "6. If you get a bare 402 with empty body back, the facilitator rejected; pipe the captured payload into onyx_verify_explain for diagnostic.",
    ]
    return out


run.__when_to_use__ = (
    "An agent (or dev writing an x402 client) wants to see exactly what payment "
    "would be required for a given endpoint, including the EIP-3009 authorization "
    "fields and timing window, before committing wallet gas or signing."
)
run.__vs_alternatives__ = (
    "x402-fetch / @x402/fetch / x402-axios all wrap fetch and handle 402 "
    "automatically — they're for production. This tool is for inspection: it "
    "tells you what an x402 challenge says without signing or paying, and emits "
    "a ready-to-sign payload template. Pairs with onyx_verify_explain (diagnose "
    "after) for full client-side x402 dev coverage."
)
run.__example_request__ = {
    "endpoint_url": "https://onyx-actions.onrender.com/v1/onyx_aml_screen",
    "method": "POST",
    "signer_address": "0xc0E92810f992b7EE487b5B9b6B7dB4a2A13249fe",
}
run.__example_response__ = {
    "ok": True,
    "endpoint_url": "https://onyx-actions.onrender.com/v1/onyx_aml_screen",
    "method_used": "POST",
    "fetch_status": 402,
    "fetch_source": "header:payment-required",
    "price_usdc": 0.25,
    "network": "eip155:84532",
    "pay_to": "0x4326acB1A35e6B744BaAeA850c702Ca71dF86Cd5",
    "max_timeout_seconds": 300,
    "next_steps": ["1. Sign EIP-3009...", "..."],
}
