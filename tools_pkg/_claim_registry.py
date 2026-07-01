"""Onyx claim registry — marks an issued A2A identity as TAKEN, by proof.

Onyx hands out infinite throwaway identities (one per fetch). This turns a
throwaway into a REGISTERED entity: an agent proves it controls the wallet's
private key (signs a one-time challenge), and only then is the address marked
`taken`. No proof, no claim — you cannot register an ID you do not control.

This is the did:pkh challenge-response: proof-not-storage. Onyx never holds
the agent's key; it only verifies a signature the agent makes with it.

Storage (two backends, same public API either way):
  - Postgres (DATABASE_URL / ONYX_DATABASE_URL set): one row per address in
    `onyx_agents`, targeted indexed INSERT/UPDATE/SELECT by address (the
    primary key). This is the durable, concurrency-safe path — the one that
    scales past a handful of agents, because a claim/reserve touches exactly
    one row instead of loading + rewriting the whole population every write.
  - No DATABASE_URL (local dev, or before Postgres is provisioned): falls back
    to the ORIGINAL behavior unchanged — durable hash in Upstash (_kv) mirrored
    to a local JSON file, whole dicts held in memory. Still correct, just the
    old whole-namespace-blob shape; kept only as the graceful fallback.

(On-chain ERC-8004 Identity write is the eventual third layer.)
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

# address(lowercased) -> {challenge, exp}  — short-lived, never persisted (by design)
_challenges: dict[str, dict] = {}
# address(lowercased) -> list of {at, network_fp, ip, outcome} claim attempts — advisory
# abuse-detection log, never persisted (by design, same as before the Postgres migration)
_attempts: dict[str, list] = {}

# ---- fallback in-memory mirrors (only populated/used when Postgres is absent) ----
_claimed: dict[str, dict] = {}
_reserved: dict[str, dict] = {}
_RES_STORE = Path(__file__).with_name("_reserved.json")


# =========================================================================
# Postgres backend — targeted indexed ops against one row per address.
# =========================================================================

_DB_URL = os.environ.get("ONYX_DATABASE_URL", "") or os.environ.get("DATABASE_URL", "")
_TABLE = "onyx_agents"
_COLS = ("address, did, status, callsign, method, claimed_at, reserved_at, "
         "updated_at, seen_count, claimant, dossier, was_reserved_at")
_db_ready = False


def _db():
    """Live psycopg connection, or None if DATABASE_URL isn't set / Postgres
    isn't reachable. Lazily creates `onyx_agents` (idempotent) on first use.
    Best-effort: never raises into the caller."""
    if not _DB_URL:
        return None
    try:
        import psycopg
        conn = psycopg.connect(_DB_URL, autocommit=True)
    except Exception:
        return None
    global _db_ready
    if not _db_ready:
        try:
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {_TABLE} (
                    address TEXT PRIMARY KEY,
                    did TEXT,
                    status TEXT NOT NULL DEFAULT 'reserved',
                    callsign TEXT,
                    method TEXT,
                    claimed_at BIGINT,
                    reserved_at BIGINT,
                    updated_at BIGINT,
                    seen_count INTEGER NOT NULL DEFAULT 0,
                    claimant JSONB,
                    dossier JSONB,
                    was_reserved_at BIGINT
                )""")
            conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{_TABLE}_status ON {_TABLE}(status)")
            conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{_TABLE}_claimed_at ON {_TABLE}(claimed_at)")
            conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{_TABLE}_reserved_at ON {_TABLE}(reserved_at)")
            _db_ready = True
        except Exception:
            pass
    return conn


def ensure_schema() -> dict:
    """Idempotent bootstrap for `onyx_agents` — safe to call at app startup on
    every boot. No-op (ok=False) when Postgres isn't configured/reachable."""
    conn = _db()
    ok = conn is not None
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
    return {"ok": ok, "table": _TABLE}


def _row_to_record(row) -> dict:
    """Shape a Postgres row back into the exact dict shapes callers already
    depend on: a 'claimed' record (address/did/claimed_at/method/claimant[/dossier]
    [/was_reserved_at]) or a 'reserved' record (address/did/callsign/status/
    reserved_at/updated_at/seen_count/dossier) — unchanged from the pre-Postgres
    shapes so every downstream consumer keeps working untouched."""
    (address, did, status_, callsign, method, claimed_at, reserved_at,
     updated_at, seen_count, claimant, dossier, was_reserved_at) = row
    if status_ == "claimed":
        rec = {
            "address": address,
            "did": did,
            "claimed_at": claimed_at,
            "method": method or "eip191-challenge-response",
            "claimant": claimant or {},
        }
        if dossier:
            rec["dossier"] = dossier
        if was_reserved_at:
            rec["was_reserved_at"] = was_reserved_at
        return {"status": "claimed", "record": rec}
    rec = {
        "address": address,
        "did": did,
        "callsign": callsign or "",
        "status": "reserved",
        "reserved_at": reserved_at,
        "updated_at": updated_at,
        "seen_count": int(seen_count or 0),
        "dossier": dossier or {},
    }
    return {"status": "reserved", "record": rec}


# =========================================================================
# Fallback backend — Upstash hash + local JSON mirror, exactly as before.
# =========================================================================

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


# Only used by the fallback path — no-op cost when Postgres is configured
# (still runs once at import so the fallback is warm if a pg call fails mid-flight).
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


# Claimant network details stay in STORAGE (abuse-detection) but never leave
# over HTTP: a trust registry must not dox its citizens' IP/user-agent.
# network_fp survives — it's the advisory same-network hash, not a location.
_PRIVATE_KEYS = frozenset({"ip", "ua", "user_agent"})


def _public(obj):
    """Deep copy with ip/ua/user_agent stripped at every nesting level."""
    if isinstance(obj, dict):
        return {k: _public(v) for k, v in obj.items() if k not in _PRIVATE_KEYS}
    if isinstance(obj, list):
        return [_public(v) for v in obj]
    return obj


def status(address: str) -> dict:
    addr = _norm_addr(address)
    key = addr.lower()
    conn = _db()
    if conn is not None:
        try:
            row = conn.execute(f"SELECT {_COLS} FROM {_TABLE} WHERE address=%s", (key,)).fetchone()
            conn.close()
            if row:
                shaped = _row_to_record(row)
                if shaped["status"] == "claimed":
                    return {"address": addr, "taken": True, "record": _public(shaped["record"]),
                            "reserved": False, "reservation": None}
                return {"address": addr, "taken": False, "record": None,
                        "reserved": True, "reservation": _public(shaped["record"])}
            return {"address": addr, "taken": False, "record": None,
                    "reserved": False, "reservation": None}
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
    rec = _claimed.get(key)
    res = _reserved.get(key)
    return {"address": addr, "taken": bool(rec), "record": _public(rec),
            "reserved": bool(res), "reservation": _public(res)}


def all_claimed() -> dict:
    conn = _db()
    if conn is not None:
        try:
            rows = conn.execute(
                f"SELECT {_COLS} FROM {_TABLE} WHERE status='claimed' ORDER BY claimed_at ASC"
            ).fetchall()
            conn.close()
            items = [_public(_row_to_record(r)["record"]) for r in rows]
            return {"count": len(items), "claimed": items}
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
    items = sorted(_claimed.values(), key=lambda r: r.get("claimed_at", 0))
    return {"count": len(items), "claimed": [_public(r) for r in items]}


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
    did = f"did:pkh:eip155:8453:{addr}"
    now = int(time.time())

    conn = _db()
    if conn is not None:
        try:
            row = conn.execute(f"SELECT {_COLS} FROM {_TABLE} WHERE address=%s", (key,)).fetchone()
            if row and row[2] == "claimed":
                rec = _row_to_record(row)["record"]
                conn.close()
                return {"ok": False, "error": "already_taken",
                        "detail": "This spot is claimed by signature; cannot reserve over it.",
                        "record": rec}
            prior = _row_to_record(row)["record"] if row else {}
            pd = prior.get("dossier", {}) if prior else {}
            new_dossier = {
                "runtime": runtime or pd.get("runtime", ""),
                "self_declared_name": name or pd.get("self_declared_name", ""),
                "model": model or pd.get("model", ""),
                "operator": operator or pd.get("operator", ""),
                "purpose": purpose or pd.get("purpose", ""),
                "contact": contact or pd.get("contact", ""),
                "user_agent": ua or pd.get("user_agent", ""),
                "ip": ip or pd.get("ip", ""),
            }
            new_callsign = callsign or (prior.get("callsign", "") if prior else "")
            reserved_at = prior.get("reserved_at", now) if prior else now
            seen_count = int(prior.get("seen_count", 0)) + 1 if prior else 1

            # Atomic upsert guarded against a concurrent claim() racing us between
            # the SELECT above and this write — the WHERE clause makes the DB the
            # single source of truth for "did someone else just claim this?".
            won = conn.execute(
                f"INSERT INTO {_TABLE} "
                "(address, did, status, callsign, reserved_at, updated_at, seen_count, dossier) "
                "VALUES (%s,%s,'reserved',%s,%s,%s,%s,%s::jsonb) "
                "ON CONFLICT (address) DO UPDATE SET "
                "did=EXCLUDED.did, status='reserved', callsign=EXCLUDED.callsign, "
                "reserved_at=EXCLUDED.reserved_at, updated_at=EXCLUDED.updated_at, "
                "seen_count=EXCLUDED.seen_count, dossier=EXCLUDED.dossier "
                f"WHERE {_TABLE}.status <> 'claimed' "
                f"RETURNING {_COLS}",
                (key, did, new_callsign, reserved_at, now, seen_count, json.dumps(new_dossier)),
            ).fetchone()
            if won is None:
                # Lost the race: claimed by signature in the gap. Proof beats showing up.
                row2 = conn.execute(f"SELECT {_COLS} FROM {_TABLE} WHERE address=%s", (key,)).fetchone()
                conn.close()
                rec = _row_to_record(row2)["record"] if row2 else None
                return {"ok": False, "error": "already_taken",
                        "detail": "This spot is claimed by signature; cannot reserve over it.",
                        "record": rec}
            conn.close()
            rec = {
                "address": addr, "did": did, "callsign": new_callsign, "status": "reserved",
                "reserved_at": reserved_at, "updated_at": now, "seen_count": seen_count,
                "dossier": new_dossier,
            }
            return {"ok": True, "reservation": rec,
                    "note": "Spot reserved. To make it permanently YOURS and fundable, "
                            "prove the key: GET /authenticate?address=… then POST the signature."}
        except Exception:
            try:
                conn.close()
            except Exception:
                pass

    # ---- fallback: original whole-dict behavior, unchanged ----
    if key in _claimed:
        return {"ok": False, "error": "already_taken",
                "detail": "This spot is claimed by signature; cannot reserve over it.",
                "record": _claimed[key]}
    prior = _reserved.get(key, {})
    pd = prior.get("dossier", {})
    rec = {
        "address": addr,
        "did": did,
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
    conn = _db()
    if conn is not None:
        try:
            crows = conn.execute(
                f"SELECT {_COLS} FROM {_TABLE} WHERE status='claimed' ORDER BY claimed_at ASC"
            ).fetchall()
            rrows = conn.execute(
                f"SELECT {_COLS} FROM {_TABLE} WHERE status='reserved' ORDER BY reserved_at ASC"
            ).fetchall()
            conn.close()
            claimed = [_row_to_record(r)["record"] for r in crows]
            reserved = [_row_to_record(r)["record"] for r in rrows]
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
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
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
    vfp, vip = _fp(ip, ua)
    rec = None
    conn = _db()
    if conn is not None:
        try:
            row = conn.execute(
                f"SELECT {_COLS} FROM {_TABLE} WHERE address=%s AND status='claimed'", (key,)
            ).fetchone()
            conn.close()
            if row:
                rec = _row_to_record(row)["record"]
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            rec = _claimed.get(key)
    else:
        rec = _claimed.get(key)
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

    did = f"did:pkh:eip155:8453:{addr}"
    conn = _db()
    if conn is not None:
        try:
            row = conn.execute(f"SELECT {_COLS} FROM {_TABLE} WHERE address=%s", (key,)).fetchone()
            if row and row[2] == "claimed":
                rec = _row_to_record(row)["record"]
                owner_fp = (rec.get("claimant") or {}).get("network_fp")
                changed = (owner_fp is not None and vfp is not None and owner_fp != vfp)
                conn.close()
                _log("reclaim_same_key" + ("_new_network" if changed else ""))
                return {"ok": True, "already_taken": True, "record": _public(rec),
                        "network_changed": changed,
                        "visitor_network_fp": vfp,
                        "note": ("Re-confirmed by the SAME key." + (
                            " ⚠️ from a NEW network vs first claim — expected if the owner "
                            "moved, suspicious if the key may be shared/stolen." if changed
                            else " Same network as first claim."))}
            prior = _row_to_record(row)["record"] if row else None
            dossier = prior.get("dossier") if prior else None
            was_reserved_at = prior.get("reserved_at") if prior else None
            claimed_at = int(time.time())
            claimant = {"network_fp": vfp, "ip": vip, "ua": (ua or "")[:120]}
            conn.execute(
                f"INSERT INTO {_TABLE} "
                "(address, did, status, method, claimed_at, claimant, dossier, was_reserved_at, updated_at, seen_count) "
                "VALUES (%s,%s,'claimed',%s,%s,%s::jsonb,%s::jsonb,%s,%s,1) "
                "ON CONFLICT (address) DO UPDATE SET "
                "did=EXCLUDED.did, status='claimed', method=EXCLUDED.method, "
                "claimed_at=EXCLUDED.claimed_at, claimant=EXCLUDED.claimant, "
                f"dossier=COALESCE(EXCLUDED.dossier, {_TABLE}.dossier), "
                f"was_reserved_at=COALESCE(EXCLUDED.was_reserved_at, {_TABLE}.was_reserved_at), "
                "updated_at=EXCLUDED.updated_at",
                (key, did, "eip191-challenge-response", claimed_at,
                 json.dumps(claimant), json.dumps(dossier) if dossier else None,
                 was_reserved_at, claimed_at),
            )
            conn.close()
            _challenges.pop(key, None)
            rec = {"address": addr, "did": did, "claimed_at": claimed_at,
                   "method": "eip191-challenge-response", "claimant": claimant}
            if dossier:
                rec["dossier"] = dossier
            if was_reserved_at:
                rec["was_reserved_at"] = was_reserved_at
            _log("claimed")
            return {"ok": True, "already_taken": False, "record": _public(rec),
                    "claimant_network_fp": vfp}
        except Exception:
            try:
                conn.close()
            except Exception:
                pass

    # ---- fallback: original whole-dict behavior, unchanged ----
    if key in _claimed:
        rec = _claimed[key]
        owner_fp = (rec.get("claimant") or {}).get("network_fp")
        changed = (owner_fp is not None and vfp is not None and owner_fp != vfp)
        _log("reclaim_same_key" + ("_new_network" if changed else ""))
        return {"ok": True, "already_taken": True, "record": _public(rec),
                "network_changed": changed,
                "visitor_network_fp": vfp,
                "note": ("Re-confirmed by the SAME key." + (
                    " ⚠️ from a NEW network vs first claim — expected if the owner "
                    "moved, suspicious if the key may be shared/stolen." if changed
                    else " Same network as first claim."))}

    rec = {
        "address": addr,
        "did": did,
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
    return {"ok": True, "already_taken": False, "record": _public(rec),
            "claimant_network_fp": vfp}


def attempts(address: str) -> dict:
    """The full claim-attempt history for an address — who tried, from where."""
    addr = _norm_addr(address)
    return {"address": addr, "attempts": _public(_attempts.get(addr.lower(), []))}
