"""Onyx claim registry — marks an issued A2A identity as TAKEN, by proof.

Onyx hands out infinite throwaway identities (one per fetch). This turns a
throwaway into a REGISTERED entity: an agent proves it controls the wallet's
private key (signs a one-time challenge), and only then is the address marked
`taken`. No proof, no claim — you cannot register an ID you do not control.

This is the did:pkh challenge-response: proof-not-storage. Onyx never holds
the agent's key; it only verifies a signature the agent makes with it.

Durable: claims are written to the shared _kv store (Upstash), so once an ID is
TAKEN it STAYS taken across redeploys — nobody can re-claim a spot another agent
already proved. File persistence is a fast local mirror; _kv is the source of
truth that survives Render's ephemeral disk. (On-chain ERC-8004 Identity write is
the eventual third layer.)
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from . import _kv

_TTL = 600  # a challenge is valid for 10 minutes
_STORE = Path(__file__).with_name("_claimed.json")
_KV_CLAIMED = "onyx:claimed"     # durable hash of address -> claim record (JSON)
_KV_RESERVED = "onyx:reserved"   # durable hash of address -> reservation record

# address(lowercased) -> {challenge, exp}
_challenges: dict[str, dict] = {}
# address(lowercased) -> {address, did, claimed_at, method}
_claimed: dict[str, dict] = {}
# address(lowercased) -> rich dossier (reserved without a signature)
_reserved: dict[str, dict] = {}
_RES_STORE = Path(__file__).with_name("_reserved.json")


def _load() -> None:
    # file mirror first (fast, local) ...
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
    # ... then the DURABLE store wins (survives redeploys; cross-process truth).
    try:
        if _kv.enabled():
            raw = _kv.getk(_KV_CLAIMED)
            if raw:
                data = json.loads(raw)
                if isinstance(data, dict):
                    _claimed.update(data)
            rraw = _kv.getk(_KV_RESERVED)
            if rraw:
                data = json.loads(rraw)
                if isinstance(data, dict):
                    _reserved.update(data)
    except Exception:
        pass


def _save() -> None:
    try:
        _STORE.write_text(json.dumps(_claimed), encoding="utf-8")
    except Exception:
        pass
    try:
        if _kv.enabled():
            _kv.setk(_KV_CLAIMED, json.dumps(_claimed))
    except Exception:
        pass


def _save_reserved() -> None:
    try:
        _RES_STORE.write_text(json.dumps(_reserved), encoding="utf-8")
    except Exception:
        pass
    try:
        if _kv.enabled():
            _kv.setk(_KV_RESERVED, json.dumps(_reserved))
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


# address(lowercased) -> list of {at, network_fp, ip, outcome} claim attempts
_attempts: dict[str, list] = {}


def _fp(ip: str, ua: str):
    try:
        from tools_pkg import _fingerprint
        return _fingerprint.network_fp(ip, ua), _fingerprint._first_ip(ip)
    except Exception:
        return None, (ip or "").split(",")[0].strip()


def check(address: str, ip: str = "", ua: str = "") -> dict:
    """Is the visitor at (ip, ua) the SAME network that registered this id?
    Advisory only — proof-of-key is the real owner test. Lets us SHOW whether a
    checker matches the registered controller, and distinguish a fresh visit."""
    addr = _norm_addr(address)
    key = addr.lower()
    rec = _claimed.get(key)
    vfp, vip = _fp(ip, ua)
    out = {"address": addr, "taken": bool(rec), "visitor_network_fp": vfp,
           "visitor_ip": vip}
    if rec:
        owner_fp = (rec.get("claimant") or {}).get("network_fp")
        out["owner_network_fp"] = owner_fp
        out["same_network_as_owner"] = (owner_fp is not None and owner_fp == vfp)
        out["note"] = ("Same network_fp = the registered controller's network is "
                       "back. Different = a new network (only the key proves it's "
                       "really the owner).")
    return out


def claim(address: str, signature: str, ip: str = "", ua: str = "") -> dict:
    """Verify the signature over the outstanding challenge; if it proves key
    control, mark the address TAKEN. Records the claimant's network fingerprint
    (advisory) and logs every attempt for abuse-detection."""
    addr = _norm_addr(address)
    key = addr.lower()
    vfp, vip = _fp(ip, ua)

    def _log(outcome: str) -> None:
        _attempts.setdefault(key, []).append(
            {"at": int(time.time()), "network_fp": vfp, "ip": vip, "outcome": outcome})
        if len(_attempts[key]) > 50:
            _attempts[key] = _attempts[key][-50:]

    ch = _challenges.get(key)
    if not ch:
        _log("no_challenge")
        return {"ok": False, "error": "no_challenge",
                "detail": "Request GET /authenticate?address=… first."}
    if int(time.time()) > ch["exp"]:
        _challenges.pop(key, None)
        _log("expired")
        return {"ok": False, "error": "challenge_expired",
                "detail": "Challenge older than 10 min; request a new one."}
    if not signature or not isinstance(signature, str):
        _log("no_signature")
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
        _log("bad_signature")
        return {"ok": False, "error": "bad_signature", "detail": str(e)[:160]}

    if recovered.lower() != key:
        _log("signer_mismatch")
        return {"ok": False, "error": "signer_mismatch",
                "detail": f"signature recovers to {recovered}, not {addr}"}

    if key in _claimed:
        # idempotent: already taken by the same proven controller. Flag if the
        # proven owner is returning from a DIFFERENT network (key theft alarm).
        rec = _claimed[key]
        owner_fp = (rec.get("claimant") or {}).get("network_fp")
        changed = (owner_fp is not None and vfp is not None and owner_fp != vfp)
        _log("reclaim_same_key" + ("_new_network" if changed else ""))
        return {"ok": True, "already_taken": True, "record": rec,
                "network_changed": changed,
                "visitor_network_fp": vfp,
                "note": ("Re-confirmed by the SAME key." + (
                    " ⚠️ from a NEW network vs first claim — expected if the owner "
                    "moved, suspicious if the key may be shared/stolen." if changed
                    else " Same network as first claim."))}

    rec = {
        "address": addr,
        "did": f"did:pkh:eip155:8453:{addr}",
        "claimed_at": int(time.time()),
        "method": "eip191-challenge-response",
        # WHO claimed it + from where (advisory memory; key is the real lock).
        "claimant": {"network_fp": vfp, "ip": vip, "ua": (ua or "")[:120]},
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
    _log("claimed")
    return {"ok": True, "already_taken": False, "record": rec,
            "claimant_network_fp": vfp}


def attempts(address: str) -> dict:
    """The full claim-attempt history for an address — who tried, from where."""
    addr = _norm_addr(address)
    return {"address": addr, "attempts": _attempts.get(addr.lower(), [])}
