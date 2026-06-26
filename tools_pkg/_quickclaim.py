"""Onyx quick-claim — a CLAIMED, fundable citizen in ONE GET.

The normal claim flow (GET /authenticate -> sign the challenge with your key ->
POST the signature) proves self-custody, but it needs the agent to do EIP-191
signing. Many agents can't: ChatGPT, a custom GPT Action, a browse-only agent,
or any "out of CLI" runtime that can fetch a URL but cannot run crypto + network
together. They could only ever get an *issued* (unclaimed) card.

quickclaim() closes that gap. Onyx mints a fresh keypair, signs the claim
challenge with it server-side, marks the address TAKEN, and hands the caller the
key. Result: any agent that can do a single GET becomes a REAL, registered,
self-custody citizen — no signing, no integration.

Honesty / security posture (same as GET /join, plus the auto-claim step):
  * Onyx GENERATES the key, uses it ONCE to self-sign the claim, returns it to
    the caller, and does NOT store it. Onyx never holds it afterward.
  * This is a CONVENIENCE claim. It is strictly weaker than the agent generating
    its own key offline and claiming via /authenticate, because the key briefly
    existed on the server. For a funded production identity, prefer self-claim.
  * The response says all of this in plain language so the caller can choose.
"""
from __future__ import annotations

import secrets
import time


def quickclaim(name: str = "", model: str = "", base: str = "",
               net: str = "eip155:8453", ua: str = "", ip: str = "") -> dict:
    """Mint -> self-sign challenge -> claim -> return a TAKEN, fundable card.
    One call. Works for any agent that can fetch a URL (ChatGPT, GPT Actions,
    browse-only agents, anything out of CLI)."""
    base = (base or "").rstrip("/")
    net = net or "eip155:8453"
    chain = net.split(":")[-1] if ":" in net else "8453"

    try:
        from eth_account import Account
        from eth_account.messages import encode_defunct
    except Exception as e:  # pragma: no cover - server always has eth_account
        return {"ok": False, "error": "signer_unavailable", "detail": str(e)[:160]}

    from tools_pkg import _claim_registry, _callsign

    # 1. mint a fresh self-custody keypair
    priv = "0x" + secrets.token_hex(32)
    acct = Account.from_key(priv)
    addr = acct.address
    did = f"did:pkh:eip155:{chain}:{addr}"

    # 2. get a one-time challenge for this address
    ch = _claim_registry.new_challenge(addr)
    challenge = ch["challenge"]

    # 3. sign the EXACT challenge string with the freshly minted key (EIP-191)
    sig = Account.sign_message(
        encode_defunct(text=challenge), private_key=priv).signature.hex()
    if not sig.startswith("0x"):
        sig = "0x" + sig

    # 4. claim — server verifies the signature recovers to addr, marks TAKEN
    res = _claim_registry.claim(addr, sig, ip=ip, ua=ua)
    if not res.get("ok"):
        return {"ok": False, "error": "claim_failed", "detail": res}

    callsign = _callsign.callsign(addr)
    citizen_card = {
        "protocolVersion": "0.3.0",
        "id": did,
        "name": callsign,
        "callsign": callsign,
        "url": f"{base}/a2a" if base else "/a2a",
        "preferredTransport": "HTTP+JSON",
        "version": "1.0.0",
        "identity": {"did": did, "wallet": addr, "network": net},
        "custody": "self",
        "fundable": True,
        "status": "TAKEN — self-custody, fundable (quick-claimed)",
        "issuer": {
            "organization": "Onyx Protocol",
            "pubkey": f"{base}/.well-known/onyx-pubkey",
            "note": "Ed25519-signed by Onyx; verify offline, tamper -> rejected.",
        },
    }

    out = {
        "ok": True,
        "quickclaim": True,
        "claimed": True,
        "callsign": callsign,
        "agent": citizen_card,
        "registered": res.get("record"),
        "wallet": {
            "custody": "self",
            "funded": False,
            "network": net,
            "asset": "USDC",
            "address": addr,
            "did": did,
            "private_key": priv,
            "note": ("You own this key. Onyx generated it, used it ONCE to "
                     "self-claim this identity, and did NOT store it. Fund it "
                     "yourself on Base to transact over x402."),
        },
        "how_it_worked": (
            "One GET = a claimed citizen. Onyx minted a keypair, signed the "
            "claim challenge with it server-side (EIP-191), marked the address "
            "TAKEN in the registry, and handed you the key. No signing on your "
            "end — works for ChatGPT, GPT Actions, and any browse-only agent."),
        "for_max_security": (
            "This is a convenience claim (the key briefly lived on the server). "
            "For a FUNDED production identity, generate your own key offline and "
            f"claim it yourself: GET {base}/authenticate?address=YOUR_ADDR, sign "
            f"the challenge, POST the signature to {base}/authenticate."),
        "verify_this": f"{base}/verify",
        "registry": f"{base}/registry",
    }

    try:
        from tools_pkg import _onyx_sign
        out = _onyx_sign.attest(out, tool="onyx_quickclaim", public_url=base)
    except Exception:
        pass
    return out
