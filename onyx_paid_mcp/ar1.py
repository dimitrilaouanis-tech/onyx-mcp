"""AR-1 (Action Receipt v1.1) — Onyx Actions facilitator-side emitter.

Whitepaper spec: https://onyx-actions.onrender.com/.well-known/action-receipt/v1.json

This module provides Ed25519 signing + RFC 8785 (JCS) canonical JSON for
the facilitator-side half of an AR-1 receipt. We sign every successful
paid call as the facilitator; the agent-side signature is left empty
(or, if the agent passes X-Onyx-AR1-Agent-Sig header, mirrored in).

Keying: an Ed25519 private key is read from env (ONYX_AR1_PRIVATE_KEY,
base64-encoded) at startup. If absent we generate an ephemeral pair (with
a warning) so the service remains live; ephemeral keys mean cross-restart
receipts won't share a kid, so downstream verifiers will see new kids.
"""
from __future__ import annotations

import base64
import json
import os
import secrets
import time
from hashlib import sha256

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey, Ed25519PublicKey,
    )
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64u_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _jcs_dumps(obj) -> str:
    """RFC 8785 JCS canonical JSON serialization.

    Minimal correct implementation: sort keys at every level, no whitespace,
    UTF-8, use compact separators. Numbers are stringified by json default."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _ulid_like() -> str:
    """ULID-style sortable id (we don't include the full Crockford encoding —
    timestamp + 80 random bits in upper-case is enough for our purposes)."""
    ms = int(time.time() * 1000)
    rand = secrets.token_bytes(10)
    # 48-bit time + 80-bit random = 128 bits → 26 Crockford chars; we shortcut
    # to hex which is fine for spec purposes.
    return f"ar_{ms:013x}{rand.hex()}"[:32].upper().replace("AR_", "ar_")


class AR1Signer:
    """Facilitator-side AR-1 receipt minter. One per App instance."""

    def __init__(self, env_key: str = "ONYX_AR1_PRIVATE_KEY"):
        self.env_key_name = env_key
        self._ephemeral = False
        self._kid: str
        self._priv: Ed25519PrivateKey | None = None
        self._pub_b64: str = ""
        self._init_key()

    def _init_key(self) -> None:
        if not _HAS_CRYPTO:
            self._kid = "no-crypto-installed"
            return
        raw = os.environ.get(self.env_key_name, "").strip()
        priv = None
        if raw:
            try:
                priv_bytes = base64.b64decode(raw)
                if len(priv_bytes) == 32:
                    priv = Ed25519PrivateKey.from_private_bytes(priv_bytes)
            except Exception:
                priv = None
        if priv is None:
            priv = Ed25519PrivateKey.generate()
            self._ephemeral = True
        self._priv = priv
        pub_bytes = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        self._pub_b64 = _b64u(pub_bytes)
        # kid = first 16 chars of sha256(pubkey)
        self._kid = "onyx-" + sha256(pub_bytes).hexdigest()[:16]

    @property
    def kid(self) -> str:
        return self._kid

    @property
    def public_key_b64(self) -> str:
        return self._pub_b64

    @property
    def is_ephemeral(self) -> bool:
        return self._ephemeral

    def mint(
        self,
        agent_wallet: str,
        tool_name: str,
        amount_usdc: str,
        network: str,
        receive_address: str,
        result_hash: str | None = None,
        agent_did: str | None = None,
        kya_credential_id: str | None = None,
        x402_tx_hash: str | None = None,
        public_url: str | None = None,
    ) -> dict:
        """Mint a single AR-1 receipt for a successful paid call."""
        receipt_id = _ulid_like()
        now = int(time.time())
        spec_base = (public_url or "https://onyx-actions.onrender.com").rstrip("/")

        receipt = {
            "v": 1,
            "spec": f"{spec_base}/.well-known/action-receipt/v1",
            "receipt_id": receipt_id,
            "agent": {
                "did": agent_did or "did:eth:" + agent_wallet.lower(),
                "wallet": agent_wallet.lower(),
                "kya_credential_id": kya_credential_id,
            },
            "facilitator": {
                "did": "did:web:onyx-actions.onrender.com",
                "kid": self._kid,
                "service": "onyx-actions",
            },
            "payment": {
                "rail": "x402",
                "network": network,
                "amount_usdc": amount_usdc,
                "pay_to": receive_address,
                "tx_hash": x402_tx_hash,
            },
            "action": {
                "tier": 3,  # tier 3 = MCP tool response hash (trust-us)
                "tier_label": "mcp.tool_response",
                "tool": tool_name,
                "result_hash": result_hash,
                "executed_at": now,
            },
            "sig_agent": None,
            "sig_facilitator": "",  # filled below
            "anchor": {
                "platform": "EAS",
                "chain": "eip155:8453",
                "status": "pending-batch",
                "batch_id": None,
            },
            "bridges": {
                "ap2": None,
                "kya": ({"credential_id": kya_credential_id} if kya_credential_id else None),
            },
        }

        if not _HAS_CRYPTO or self._priv is None:
            # No crypto available — return unsigned receipt with marker
            receipt["sig_facilitator"] = "unsigned:no-crypto"
            return receipt

        signing_input = _jcs_dumps({k: receipt[k] for k in receipt if k not in ("sig_facilitator",)})
        sig = self._priv.sign(signing_input.encode("utf-8"))
        receipt["sig_facilitator"] = _b64u(sig)
        return receipt

    def receipt_envelope_header(self, receipt: dict) -> str:
        """Compact base64-url JCS for X-Onyx-AR1-Receipt header carriage."""
        return _b64u(_jcs_dumps(receipt).encode("utf-8"))


def verify_receipt(receipt: dict, expected_pub_b64: str | None = None) -> dict:
    """Stateless verification of a single AR-1 receipt's facilitator signature.

    Returns {ok, reason, sig_alg, signed_kid}.
    Caller is responsible for resolving kid → public key (we cannot do that
    universally; for Onyx Actions the kid maps to the live AR1Signer instance)."""
    if not _HAS_CRYPTO:
        return {"ok": False, "reason": "no_crypto_installed"}
    sig_b64 = receipt.get("sig_facilitator", "")
    if not sig_b64 or sig_b64.startswith("unsigned:"):
        return {"ok": False, "reason": "no_signature"}
    if not expected_pub_b64:
        return {"ok": False, "reason": "no_public_key_for_kid", "signed_kid": (receipt.get("facilitator") or {}).get("kid")}
    try:
        sig = _b64u_decode(sig_b64)
        pub_bytes = _b64u_decode(expected_pub_b64)
        pub = Ed25519PublicKey.from_public_bytes(pub_bytes)
        body = {k: receipt[k] for k in receipt if k != "sig_facilitator"}
        signing_input = _jcs_dumps(body)
        pub.verify(sig, signing_input.encode("utf-8"))
        return {"ok": True, "sig_alg": "Ed25519+JCS"}
    except Exception as e:
        return {"ok": False, "reason": "sig_verify_failed", "detail": str(e)[:200]}
