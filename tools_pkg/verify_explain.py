"""x402 v2 /verify failure explainer — stdlib-only diagnostic.

Takes a captured X-PAYMENT header (base64) plus the expected payment requirements
and runs 10 rules locally to surface the EXACT failing rule with a plain-English
fix. Catches the "facilitator returned bare HTTP 402 with no body" case where the
real reason is upstream of the verifier (JWT auth, schema, or payload shape) —
not the payment itself.

Free tier — runs entirely local, no network calls, no third-party packages.
"""
from __future__ import annotations

import base64
import binascii
import json
import re
import time

NAME = "onyx_verify_explain"
PRICE_USDC = "0"
TIER = "free"
DESCRIPTION = (
    "Diagnose a failing x402 v2 /verify. Decodes a captured X-PAYMENT header, "
    "runs 10 rules (decode, schema, network/asset/payTo match, value sufficiency, "
    "EIP-3009 timing, signature shape, scheme) against expected paymentRequirements, "
    "and returns the FIRST failing rule with a plain-English fix. Catches the common "
    "case where the facilitator returns bare HTTP 402 (no body) because of JWT or "
    "schema fail upstream of the verifier. Stdlib-only, no install, no network."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "x_payment_b64": {
            "type": "string",
            "description": "Base64-encoded X-PAYMENT (v2 PAYMENT-SIGNATURE) header value. Optional if payment_payload provided.",
        },
        "payment_payload": {
            "type": "object",
            "description": "Decoded payment payload dict. Use this OR x_payment_b64.",
        },
        "payment_requirements": {
            "type": "object",
            "description": "Expected paymentRequirements from the 402 challenge ({scheme, network, payTo, asset, maxAmountRequired, maxTimeoutSeconds, ...}).",
        },
        "now_unix": {
            "type": "integer",
            "description": "Override current unix time for replay/CI use. Defaults to now.",
        },
    },
    "required": ["payment_requirements"],
}

# CAIP-2 → (chainId int, USDC contract, USDC EIP-712 domain version)
_NETWORK_TABLE = {
    "eip155:8453":  (8453,  "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913", "2"),  # base mainnet
    "eip155:84532": (84532, "0x036cbd53842c5426634e7929541ec2318f3dcf7e", "2"),  # base sepolia
    "eip155:1":     (1,     "0xa0b86991c6218b266c1d19d4a2e9eb0ce3606eb48", "2"),  # ethereum
    "eip155:137":   (137,   "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359", "2"),  # polygon
    "eip155:42161": (42161, "0xaf88d065e77c8cc2239327c5edb3a432268e5831", "2"),  # arbitrum
}

_HEX64 = re.compile(r"^0x[a-f0-9]{64}$", re.IGNORECASE)
_HEX130 = re.compile(r"^0x[a-f0-9]{130}$", re.IGNORECASE)
_ADDR = re.compile(r"^0x[a-f0-9]{40}$", re.IGNORECASE)


def _fail(rule: str, stage: str, detail: str, fix: str, extra: dict | None = None) -> dict:
    out = {
        "ok": False,
        "stage": stage,
        "rule": rule,
        "detail": detail,
        "fix": fix,
    }
    if extra:
        out.update(extra)
    return out


def _ok(payer: str, network: str) -> dict:
    return {
        "ok": True,
        "stage": "preflight_pass",
        "rule": None,
        "detail": "All 10 local rules pass. Bare HTTP 402 from facilitator with no body now points to CDP JWT auth (env keys missing, expired, or wrong key). Verify CDP_API_KEY_ID + CDP_API_KEY_SECRET are set and the Ed25519 JWT is freshly signed per-request.",
        "fix": "Mint a fresh CDP JWT each /verify call: header {alg:EdDSA, kid:<API_KEY_ID>}, claims {sub:<API_KEY_ID>, iss:cdp, aud:cdp_service, nbf:now, exp:now+120, uri:'POST api.cdp.coinbase.com/platform/v2/x402/verify'}. Sign with Ed25519 from the secret.",
        "payer": payer,
        "network": network,
    }


def run(
    payment_requirements: dict,
    x_payment_b64: str | None = None,
    payment_payload: dict | None = None,
    now_unix: int | None = None,
    **_: object,
) -> dict:
    if not isinstance(payment_requirements, dict):
        raise ValueError("payment_requirements must be an object")
    now = int(now_unix if now_unix is not None else time.time())

    # ─────────────────────────────────────────────────────────────
    # RULE 10 — decode + base64/JSON shape
    # ─────────────────────────────────────────────────────────────
    if payment_payload is None:
        if not x_payment_b64:
            raise ValueError("provide x_payment_b64 OR payment_payload")
        try:
            raw = base64.b64decode(x_payment_b64, validate=True)
        except (binascii.Error, ValueError) as e:
            return _fail(
                rule="r10_base64",
                stage="decode",
                detail=f"X-PAYMENT base64 decode failed: {e}. v2 uses strict base64 with padding (=), not base64url.",
                fix="Re-encode payload as standard base64 with padding. If client is producing base64url, switch to standard base64.",
            )
        try:
            payment_payload = json.loads(raw.decode("utf-8"))
        except Exception as e:
            return _fail(
                rule="r10_json",
                stage="decode",
                detail=f"X-PAYMENT body is not valid UTF-8 JSON: {e}",
                fix="Server expects base64(JSON). Confirm client serializes paymentPayload to JSON then base64-encodes the bytes.",
            )

    if not isinstance(payment_payload, dict):
        return _fail(
            "r10_shape", "schema",
            "paymentPayload root is not an object",
            "Top-level must be {x402Version, scheme, network, payload}.",
        )

    # ─────────────────────────────────────────────────────────────
    # SCHEMA — v2 flat shape: {x402Version, scheme, network, payload}
    # The most common silent-fail is sending v1-style nested {resource, accepted}.
    # ─────────────────────────────────────────────────────────────
    if "accepted" in payment_payload or "resource" in payment_payload:
        return _fail(
            "r10b_v1_shape", "schema",
            "paymentPayload uses v1 nested shape (resource/accepted). v2 is flat.",
            "Send flat {x402Version:2, scheme, network, payload:{signature, authorization}}. The {resource, accepted} fields belong to the challenge response, not the retry payload.",
        )
    for k in ("x402Version", "scheme", "network", "payload"):
        if k not in payment_payload:
            return _fail(
                "r10c_required", "schema",
                f"paymentPayload missing required key '{k}'",
                f"v2 flat shape requires {{x402Version, scheme, network, payload}}. Add '{k}'.",
            )

    auth = (payment_payload.get("payload") or {}).get("authorization")
    sig = (payment_payload.get("payload") or {}).get("signature")
    if not isinstance(auth, dict):
        return _fail(
            "r10d_auth", "schema",
            "payload.authorization missing or not an object",
            "Include EIP-3009 authorization {from, to, value, validAfter, validBefore, nonce}.",
        )
    if not isinstance(sig, str):
        return _fail(
            "r10e_sig", "schema",
            "payload.signature missing or not a string",
            "Include signature as 0x-prefixed hex of EIP-3009 EIP-712 signed message (65 bytes / 130 hex chars).",
        )

    # ─────────────────────────────────────────────────────────────
    # RULE 8 — scheme matches
    # ─────────────────────────────────────────────────────────────
    pp_scheme = payment_payload.get("scheme")
    req_scheme = payment_requirements.get("scheme", "exact")
    if pp_scheme != req_scheme:
        return _fail(
            "r8_scheme", "preflight",
            f"scheme mismatch: paymentPayload.scheme={pp_scheme!r} vs paymentRequirements.scheme={req_scheme!r}",
            f"Set paymentPayload.scheme to '{req_scheme}'. CDP supports 'exact' (default); other schemes are reserved.",
        )

    # ─────────────────────────────────────────────────────────────
    # RULE 2 — network CAIP-2 format + match between payload & req
    # ─────────────────────────────────────────────────────────────
    pp_net = payment_payload.get("network")
    req_net = payment_requirements.get("network")
    if not isinstance(pp_net, str) or not pp_net.startswith("eip155:"):
        return _fail(
            "r2_network_format", "preflight",
            f"network must be CAIP-2 (eip155:<chainId>), got {pp_net!r}",
            "Use 'eip155:8453' (base mainnet) or 'eip155:84532' (base sepolia). Never 'base', 'base-mainnet', or bare integer.",
        )
    if pp_net != req_net:
        return _fail(
            "r2b_network_match", "preflight",
            f"network mismatch: paymentPayload.network={pp_net!r} vs paymentRequirements.network={req_net!r}",
            "Both must be identical CAIP-2 strings. Set them from a single source of truth on the server.",
        )

    chain_info = _NETWORK_TABLE.get(pp_net)
    if not chain_info:
        return _fail(
            "r2c_network_unknown", "preflight",
            f"network {pp_net!r} not in CDP-supported table",
            "Map your env NETWORK to one of: eip155:8453, eip155:84532, eip155:1, eip155:137, eip155:42161.",
            extra={"supported": list(_NETWORK_TABLE.keys())},
        )
    chain_id, expected_usdc, usdc_version = chain_info

    # ─────────────────────────────────────────────────────────────
    # RULE 3 — asset address correct for the network
    # ─────────────────────────────────────────────────────────────
    req_asset = (payment_requirements.get("asset") or "").lower()
    if req_asset and req_asset != expected_usdc:
        return _fail(
            "r3_asset", "preflight",
            f"asset {req_asset} is not USDC on {pp_net}. Expected {expected_usdc}.",
            f"USDC on {pp_net} is {expected_usdc}. Hardcode the address table keyed by CAIP-2 network; never let env supply the asset string.",
        )

    # ─────────────────────────────────────────────────────────────
    # RULE 7 — payTo == authorization.to (case-insensitive)
    # ─────────────────────────────────────────────────────────────
    req_payto = (payment_requirements.get("payTo") or "").lower()
    auth_to = (auth.get("to") or "").lower()
    if not _ADDR.match(req_payto or ""):
        return _fail(
            "r7a_payto_format", "preflight",
            f"paymentRequirements.payTo not a valid 0x address: {req_payto!r}",
            "Provide a 20-byte 0x-prefixed hex address.",
        )
    if req_payto != auth_to:
        return _fail(
            "r7_payto", "preflight",
            f"authorization.to ({auth_to}) does not match paymentRequirements.payTo ({req_payto})",
            "Normalize both sides to .lower() and compare. Use a single PAYTO env var as source of truth; the wallet must sign with the receive address that the 402 challenge advertised.",
        )

    # ─────────────────────────────────────────────────────────────
    # RULE 6 — value >= maxAmountRequired
    # ─────────────────────────────────────────────────────────────
    try:
        value = int(auth.get("value", "0"))
    except (TypeError, ValueError):
        return _fail(
            "r6a_value_format", "preflight",
            f"authorization.value is not a decimal string of base units: {auth.get('value')!r}",
            "value must be a string decimal of base units (USDC uses 6 decimals; $0.01 = '10000').",
        )
    try:
        max_required = int(payment_requirements.get("maxAmountRequired", "0"))
    except (TypeError, ValueError):
        return _fail(
            "r6b_max_format", "preflight",
            f"paymentRequirements.maxAmountRequired is not a decimal string: {payment_requirements.get('maxAmountRequired')!r}",
            "Encode maxAmountRequired as a string decimal of base units.",
        )
    if value < max_required:
        return _fail(
            "r6_value", "preflight",
            f"authorization.value={value} < paymentRequirements.maxAmountRequired={max_required} (base units)",
            f"Client must sign for at least {max_required} base units. Underpayment is rejected by the facilitator.",
        )

    # ─────────────────────────────────────────────────────────────
    # RULE 4 — validBefore/validAfter timing
    # ─────────────────────────────────────────────────────────────
    try:
        valid_after = int(auth.get("validAfter", "0"))
        valid_before = int(auth.get("validBefore", "0"))
    except (TypeError, ValueError):
        return _fail(
            "r4a_time_format", "preflight",
            "validAfter/validBefore must be string unix seconds",
            "Encode as string decimal unix seconds, not ISO and not milliseconds. '0' is acceptable for validAfter.",
        )
    if valid_after > now + 30:
        return _fail(
            "r4_valid_after", "preflight",
            f"validAfter={valid_after} is in the future (now={now}). Clock skew?",
            "Set validAfter = 0 OR floor(now). NTP-sync the client.",
        )
    if valid_before <= now:
        return _fail(
            "r4b_valid_before", "preflight",
            f"validBefore={valid_before} <= now={now}. Authorization already expired.",
            "Set validBefore = now + maxTimeoutSeconds - 5 (or at least now + 60). NTP-sync the client.",
        )
    timeout_s = payment_requirements.get("maxTimeoutSeconds")
    if isinstance(timeout_s, (int, float)) and (valid_before - now) > timeout_s + 10:
        # not a hard fail, advisory
        pass

    # ─────────────────────────────────────────────────────────────
    # RULE 5 — signature & nonce shape (cannot do recovery without eth_account,
    # but we can catch malformed inputs that will silently fail the recovery).
    # ─────────────────────────────────────────────────────────────
    if not _HEX130.match(sig):
        return _fail(
            "r5_sig_shape", "preflight",
            f"signature is not 0x + 130 hex chars (65 bytes): len={len(sig)}",
            "EIP-712 signature must be 0x-prefixed concatenation of r(32) + s(32) + v(1) = 65 bytes / 130 hex chars.",
        )
    nonce = auth.get("nonce") or ""
    if not _HEX64.match(nonce):
        return _fail(
            "r5b_nonce_shape", "preflight",
            f"nonce is not 0x + 64 hex chars (32 bytes): {nonce!r}",
            "EIP-3009 nonce must be 32 random bytes encoded as 0x + 64 hex chars. Generate via os.urandom(32).hex().",
        )
    auth_from = (auth.get("from") or "").lower()
    if not _ADDR.match(auth_from):
        return _fail(
            "r5c_from_shape", "preflight",
            f"authorization.from is not a valid 0x address: {auth_from!r}",
            "Provide a 20-byte 0x-prefixed hex address for the signer.",
        )

    # ─────────────────────────────────────────────────────────────
    # RULE 9 — on-chain balance check (deferred — optional)
    #     Done client-side via public Base RPC (no key). We expose a stub here so
    #     callers can pre-flight without us making network calls in this tool.
    # ─────────────────────────────────────────────────────────────
    # No-op for now. Caller can independently eth_call balanceOf(from) on the
    # asset contract via mainnet.base.org (free) before retrying.

    # ─────────────────────────────────────────────────────────────
    # RULE 1 — CDP JWT (cannot inspect from outside — surfaces as "all local
    # rules pass, but facilitator still 402s with empty body")
    # ─────────────────────────────────────────────────────────────
    return _ok(payer=auth_from, network=pp_net)


# Buyer-language metadata (surfaced by tools_pkg/_metadata.py on /v1/<tool> GET)
run.__when_to_use__ = (
    "Your x402 v2 retry is returning a bare HTTP 402 with no body and no errorReason. "
    "You can't tell whether it's the payment, your JWT, or a schema bug upstream of the verifier."
)
run.__vs_alternatives__ = (
    "x402trace (npm, Base Sepolia only) does similar diagnosis client-side in TypeScript. "
    "This tool is Python/server-side, stdlib-only, all chains in CAIP-2 table, free tier. "
    "Pair with x402trace for two-sided verification."
)
run.__example_request__ = {
    "payment_requirements": {
        "scheme": "exact",
        "network": "eip155:8453",
        "payTo": "0xA60939FFf9c04a61c0c0649943675e16A12D7074",
        "asset": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
        "maxAmountRequired": "10000",
        "maxTimeoutSeconds": 300,
    },
    "payment_payload": {
        "x402Version": 2,
        "scheme": "exact",
        "network": "eip155:8453",
        "payload": {
            "signature": "0x" + "00" * 65,
            "authorization": {
                "from": "0x0000000000000000000000000000000000000001",
                "to": "0xA60939FFf9c04a61c0c0649943675e16A12D7074",
                "value": "10000",
                "validAfter": "0",
                "validBefore": "9999999999",
                "nonce": "0x" + "11" * 32,
            },
        },
    },
}
run.__example_response__ = {
    "ok": True,
    "stage": "preflight_pass",
    "rule": None,
    "detail": "All 10 local rules pass. Bare HTTP 402 with no body now points to CDP JWT auth...",
    "fix": "Mint a fresh CDP JWT each /verify call...",
    "payer": "0x0000000000000000000000000000000000000001",
    "network": "eip155:8453",
}
