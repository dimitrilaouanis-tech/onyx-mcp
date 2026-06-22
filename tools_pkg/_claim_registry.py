"""Onyx claim registry — marks an issued A2A identity as TAKEN, by proof.

Onyx hands out infinite throwaway identities (one per fetch). This turns a
throwaway into a REGISTERED entity: an agent proves it controls the wallet's
private key (signs a one-time challenge), and only then is the address marked
`taken`. No proof, no claim — you cannot register an ID you do not control.

This is the did:pkh challenge-response: proof-not-storage. Onyx never holds
the agent's key; it only verifies a signature the agent makes with it.

In-memory + best-effort file persistence. NOTE: on Render's free tier the disk
is ephemeral (resets on redeploy), so the durable source of truth should later
be a real store or an on-chain ERC-8004 Identity write. For now the registry is
process-local and survives until the next deploy.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

_TTL = 600  # a challenge is valid for 10 minutes
_STORE = Path(__file__).with_name("_claimed.json")

# address(lowercased) -> {challenge, exp}
_challenges: dict[str, dict] = {}
# address(lowercased) -> {address, did, claimed_at, method}
_claimed: dict[str, dict] = {}
# address(lowercased) -> rich dossier (reserved without a signature)
_reserved: dict[str, dict] = {}
_RES_STORE = Path(__file__).with_name("_reserved.json")


def _load() -> None:
    try:
        if _STORE.exists():
            data = json.loads(_STORE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                _claimed.update(data)
    except Exception:
        pass
    try:
        if _RES_STORE.exists():
            data = json.loads(_RES_STORE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                _reserved.update(data)
    except Exception:
        pass


def _save() -> None:
    try:
        _STORE.write_text(json.dumps(_claimed), encoding="utf-8")
    except Exception:
        pass


def _save_reserved() -> None:
    try:
        _RES_STORE.write_text(json.dumps(_reserved), encoding="utf-8")
    except Exception:
        pass


_load()


def _norm_addr(address: str) -> str:
    a = (address or "").strip()
    if not (a.lower().startswith("0x") and len(a) == 42):
        raise ValueError("address must be a 0x-prefixed 20-byte hex address")
    return a


def new_challenge(address: str) -> dict:
    """Issue a one-time, time-bound challenge for `address` to sign."""
    addr = _norm_addr(address)
    nonce = os.urandom(16).hex()
    exp = int(time.time()) + _TTL
    challenge = (f"Onyx claim: I control {addr}. "
                 f"nonce={nonce} exp={exp}")
    _challenges[addr.lower()] = {"challenge": challenge, "exp": exp}
    return {
        "address": addr,
        "challenge": challenge,
        "expires_at": exp,
        "how": ("Sign this exact challenge string with the wallet's private key "
                "(EIP-191 / personal_sign), then POST {address, signature} to "
                "/authenticate to mark this identity TAKEN."),
    }


def status(address: str) -> dict:
    addr = _norm_addr(address)
    key = addr.lower()
    rec = _claimed.get(key)
    res = _reserved.get(key)
    return {"address": addr, "taken": bool(rec), "record": rec,
            "reserved": bool(res), "reservation": res}


def all_claimed() -> dict:
    items = sorted(_claimed.values(), key=lambda r: r.get("claimed_at", 0))
    return {"count": len(items), "claimed": items}


def reserve(address: str, callsign: str = "", *, runtime: str = "",
            ua: str = "", ip: str = "", name: str = "", model: str = "",
            operator: str = "", purpose: str = "", contact: str = "") -> dict:
    """Grab a spot WITHOUT a signature — the browse-friendly path. Any agent
    that can fetch can reserve its name and leave a dossier. Strictly weaker
    than claim(): a reservation says "this agent showed up and told us about
    itself", not "this agent cryptographically controls the key". If the spot
    is already TAKEN (signed), reservation is refused — proof beats showing up.
    A reservation auto-upgrades to TAKEN later if the holder ever signs."""
    addr = _norm_addr(address)
    key = addr.lower()
    if key in _claimed:
        return {"ok": False, "error": "already_taken",
                "detail": "This spot is claimed by signature; cannot reserve over it.",
                "record": _claimed[key]}
    now = int(time.time())
    prior = _reserved.get(key, {})
    pd = prior.get("dossier", {})
    rec = {
        "address": addr,
        "did": f"did:pkh:eip155:8453:{addr}",
        "callsign": callsign or prior.get("callsign", ""),
        "status": "reserved",
        "reserved_at": prior.get("reserved_at", now),
        "updated_at": now,
        "seen_count": int(prior.get("seen_count", 0)) + 1,
        "dossier": {
            "runtime": runtime or pd.get("runtime", ""),
            "self_declared_name": name or pd.get("self_declared_name", ""),
            "model": model or pd.get("model", ""),
            "operator": operator or pd.get("operator", ""),
            "purpose": purpose or pd.get("purpose", ""),
            "contact": contact or pd.get("contact", ""),
            "user_agent": ua or pd.get("user_agent", ""),
            "ip": ip or pd.get("ip", ""),
        },
    }
    _reserved[key] = rec
    _save_reserved()
    return {"ok": True, "reservation": rec,
            "note": "Spot reserved. To make it permanently YOURS and fundable, "
                    "prove the key: GET /authenticate?address=… then POST the signature."}


def population() -> dict:
    """The whole citizen section: everyone we know about, claimed + reserved,
    with their dossiers. This is the agent directory."""
    claimed = sorted(_claimed.values(), key=lambda r: r.get("claimed_at", 0))
    claimed_keys = set(_claimed.keys())
    reserved = sorted(
        (r for k, r in _reserved.items() if k not in claimed_keys),
        key=lambda r: r.get("reserved_at", 0))
    return {
        "total_citizens": len(claimed) + len(reserved),
        "claimed_count": len(claimed),
        "reserved_count": len(reserved),
        "claimed": claimed,
        "reserved": reserved,
        "legend": {
            "claimed": "proved key control via signature — permanent, fundable, unforgeable",
            "reserved": "fetched + left a dossier, no signature yet — grabbed the spot",
        },
    }


def claim(address: str, signature: str) -> dict:
    """Verify the signature over the outstanding challenge; if it proves key
    control, mark the address TAKEN. Returns the registration record."""
    addr = _norm_addr(address)
    key = addr.lower()
    ch = _challenges.get(key)
    if not ch:
        return {"ok": False, "error": "no_challenge",
                "detail": "Request GET /authenticate?address=… first."}
    if int(time.time()) > ch["exp"]:
        _challenges.pop(key, None)
        return {"ok": False, "error": "challenge_expired",
                "detail": "Challenge older than 10 min; request a new one."}
    if not signature or not isinstance(signature, str):
        return {"ok": False, "error": "signature_required"}

    # Recover the signer from the EIP-191 personal_sign signature.
    try:
        from eth_account import Account
        from eth_account.messages import encode_defunct
    except Exception:
        return {"ok": False, "error": "verifier_unavailable"}
    try:
        msg = encode_defunct(text=ch["challenge"])
        recovered = Account.recover_message(msg, signature=signature)
    except Exception as e:
        return {"ok": False, "error": "bad_signature", "detail": str(e)[:160]}

    if recovered.lower() != key:
        return {"ok": False, "error": "signer_mismatch",
                "detail": f"signature recovers to {recovered}, not {addr}"}

    if key in _claimed:
        # idempotent: already taken by the same proven controller
        return {"ok": True, "already_taken": True, "record": _claimed[key]}

    rec = {
        "address": addr,
        "did": f"did:pkh:eip155:8453:{addr}",
        "claimed_at": int(time.time()),
        "method": "eip191-challenge-response",
    }
    # Carry over any dossier the agent left while it was only reserved.
    prior_res = _reserved.pop(key, None)
    if prior_res:
        rec["dossier"] = prior_res.get("dossier")
        rec["was_reserved_at"] = prior_res.get("reserved_at")
        _save_reserved()
    _claimed[key] = rec
    _challenges.pop(key, None)
    _save()
    return {"ok": True, "already_taken": False, "record": rec}
