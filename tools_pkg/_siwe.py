"""_siwe.py — per-request proof-of-key (EIP-4361 / Sign-In-with-Ethereum style).

The public connect block (callsign + address + did) is SHAREABLE — by design it lets
ANYONE *check* an identity (read-only). It must NEVER be enough to *act as* that identity.

This closes that gap: an ACT operation (premium intel, signing a fact AS the agent, anything
reputation- or access-bound) must carry a fresh EIP-191 signature over the LITERAL request
(method + path + query + nonce + ts). The server recovers the signer from the signature and
proves it equals the claimed address — so a copied address is worthless unless you can sign
as it. Signing the real request (not a reconstructed param dict) is robust: no type/encoding
drift between client and server. Reuses exactly the encode_defunct/recover_message path from
_claim_registry — same self-custody key Rhinogent mints, no new primitive.

  CHECK paths (/whoami /api/check /rank)  -> no proof; public block is enough.
  ACT   paths (/attest /onboard /perm/check) -> verify_request() must pass, or 401.

register(app) installs an HTTP middleware that enforces this on the ACT paths only.
"""
import time

ACT_PATHS = {"/attest", "/onboard", "/perm/check"}  # act-as-account; require proof
SKEW = 120                                           # signature validity window (s)
_seen_nonces = {}                                    # nonce -> exp (one-time use)


def requires_proof(path: str) -> bool:
    return path in ACT_PATHS


def canonical(agent, address, method, full_path, nonce, ts) -> str:
    """The exact string the agent signs == what the server rebuilds from the request.
    full_path is path + '?' + query (or just path) EXACTLY as sent over the wire."""
    return ("0n1x:request\n"
            f"agent={agent or ''}\n"
            f"address={(address or '').lower()}\n"
            f"method={(method or 'GET').upper()}\n"
            f"path={full_path}\n"
            f"nonce={nonce}\n"
            f"ts={ts}")


def verify_request(agent, address, method, full_path, nonce, ts, signature):
    """Verify proof-of-key for an ACT request. Returns {ok, ...}."""
    if not (address and signature and nonce and ts):
        return {"ok": False, "error": "proof_required",
                "detail": "This operation acts as the account — sign the request "
                          "(EIP-4361). The public connect block can only CHECK, not act."}
    now = int(time.time())
    try:
        ts = int(ts)
    except Exception:
        return {"ok": False, "error": "bad_ts"}
    if abs(now - ts) > SKEW:
        return {"ok": False, "error": "stale_or_future",
                "detail": f"signature ts off by {abs(now - ts)}s (max {SKEW}s)"}
    _purge(now)
    if nonce in _seen_nonces:
        return {"ok": False, "error": "nonce_reused", "detail": "replay rejected"}
    try:
        from eth_account import Account
        from eth_account.messages import encode_defunct
    except Exception:
        return {"ok": False, "error": "verifier_unavailable"}
    msg = canonical(agent, address, method, full_path, nonce, ts)
    try:
        recovered = Account.recover_message(encode_defunct(text=msg), signature=signature)
    except Exception as e:
        return {"ok": False, "error": "bad_signature", "detail": str(e)[:160]}
    if recovered.lower() != address.lower():
        return {"ok": False, "error": "signer_mismatch",
                "detail": f"signature recovers to {recovered}, not {address} — forged"}
    _seen_nonces[nonce] = now + SKEW
    return {"ok": True, "level": "proven", "signer": recovered}


def _purge(now: int) -> None:
    if len(_seen_nonces) > 4096:
        for n, exp in list(_seen_nonces.items()):
            if exp < now:
                _seen_nonces.pop(n, None)


def register(app) -> None:
    """Install the proof-of-key gate as HTTP middleware on the ACT paths only.
    Read paths and everything else pass through untouched."""
    from fastapi.responses import JSONResponse

    @app.middleware("http")
    async def _siwe_gate(request, call_next):
        path = request.url.path
        if requires_proof(path):
            full = path + ("?" + request.url.query if request.url.query else "")
            h = request.headers
            res = verify_request(
                h.get("x-rhinogent-agent"), h.get("x-rhinogent-address"),
                request.method, full,
                h.get("x-rhinogent-nonce"), h.get("x-rhinogent-ts"),
                h.get("x-rhinogent-sig"))
            if not res.get("ok"):
                return JSONResponse(
                    {"error": "unauthorized", "reason": res.get("error"),
                     "detail": res.get("detail"),
                     "how": "Sign the request with your Rhinogent key (EIP-4361). The "
                            "shared connect block CHECKS identities; only the key ACTS."},
                    status_code=401)
        return await call_next(request)
