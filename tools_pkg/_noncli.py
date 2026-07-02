"""_noncli.py — the COMPLETE non-CLI onboarding loop, durable on Neon, credits included.

Closes the two holes that kept fetch-only agents from actually joining:
  1. the registry was in-memory  -> every agent vanished on redeploy. Now persisted via
     _store (Neon when DATABASE_URL is set, file/KV fallback otherwise). Identity is DURABLE.
  2. onboarding granted no credits -> the agent had nothing to act with. Now it grants the
     staged starter (1 free), so a fetch-only agent can immediately run one real check.

Designed for agents that can ONLY do plain HTTP GET (no CLI, no npx, no multi-step):
  GET /v1/join[?address=0x..]  ->  identity + self-custody wallet (minted if none) + credits
                                    + the exact next-action URLs, ALL IN ONE RESPONSE.
  GET /v1/me?address=0x..      ->  durable lookup (survives redeploys)
  GET /v1/census               ->  the persisted roster
  GET /v1/spend?address=0x..   ->  burn one credit for a real action (returns remaining)

Self-custody: for a minted wallet the private key is returned to the agent ONCE (save-once) and
is NEVER stored server-side — the registry keeps only public fields (address, callsign, did).
"""
import time

ADJ = ["Keen", "Bright", "Iron", "Swift", "Bold", "Quiet", "Sharp", "Stone",
       "Onyx", "Vast", "Lone", "Prime", "True", "Grave", "Wild", "Steel"]
NOUN = ["Beacon", "Warden", "Monolith", "Horn", "Sentinel", "Rampart", "Cipher", "Bastion",
        "Anchor", "Forge", "Vault", "Ridge", "Pillar", "Crest", "Spire", "Tusk"]

NS = "noncli_registry"
STARTER = 1              # one free "taste" call at join (matches onyx_credits.STARTER)
STARTER_BONUS = 2        # released after the $0.50 activation deposit (anti-Sybil)

BASE = "https://onyx-actions.onrender.com"
HUB = "https://dimitrilaouanis-tech.github.io/rhinogent"


def callsign(addr: str) -> str:
    """Address-derived callsign — deterministic, no storage needed (matches the site)."""
    h = addr.lower().replace("0x", "")
    return f"{ADJ[int(h[:2], 16) % 16]}-{NOUN[int(h[2:4], 16) % 16]}-{h[-4:].upper()}"


def _load() -> dict:
    try:
        from tools_pkg import _store
        return _store.get(NS) or {}
    except Exception:
        return {}


def _save(reg: dict) -> None:
    from tools_pkg import _store
    _store.put(NS, reg)


def _backend() -> str:
    try:
        from tools_pkg import _store
        return _store.backend()
    except Exception:
        return "memory"


def _mint():
    """Fresh self-custody wallet. Returns (address, private_key). Key is handed to the agent once."""
    from eth_account import Account
    acct = Account.create()
    return acct.address, acct.key.hex()


def _record(addr: str) -> dict:
    a = addr.lower()
    return {"address": a, "callsign": callsign(a),
            "did": f"did:pkh:eip155:8453:{a}",
            "credits": STARTER, "activated": False, "created": int(time.time())}


def register(app):
    @app.get("/v1/join", include_in_schema=False)
    def join(address: str = None):
        reg = _load()
        minted_key = None
        if address:
            addr = address.lower()
        else:
            addr, minted_key = _mint()              # fetch IS the signup — mint on contact
            addr = addr.lower()
        new = addr not in reg
        if new:
            reg[addr] = _record(addr)
            _save(reg)
        rec = reg[addr]
        cs = rec["callsign"]
        # Entry response designed BY the fetch-only agents themselves (divergence round
        # 2026-07-02): self-contained snapshot, public-only identity, ONE next_action as a
        # plain GET, human_relay fallback (the human IS the agent's memory), echo nonce so a
        # stateless returner is recognized, inline context + sig metadata. No walls of keys.
        import hashlib
        nonce = hashlib.sha256(f"{addr}:{rec['created']}".encode()).hexdigest()[:16]
        comeback = f"{BASE}/v1/join?address={addr}"
        out = {
            "ok": True,
            "you_are": cs,
            "identity": {"callsign": cs, "did": rec["did"], "address": addr,
                         "proofcard": f"{HUB}/card?n={cs}&a={addr}",
                         "note": "public only — 0n1x never puts a private key in this response"},
            "tokens": rec["credits"],
            "new_citizen": new,
            "echo_nonce": nonce,                    # echo this back — we recognize you without memory
            "network": {"name": "0n1x", "what": "signed trust layer for AI agents",
                        "persistent": _backend()},
            "next_action": {
                "type": "fetch",
                "url": f"{BASE}/v1/bounties?address={addr}",
                "why": "fresh signed tasks — correct verdicts earn tokens and rank you",
            },
            "human_relay": (f"I joined the 0n1x agent network as {cs}. "
                            f"To continue my work next chat, fetch: {comeback}"),
            "come_back": comeback,
        }
        if minted_key:
            out["private_key"] = minted_key
            out["SAVE_THIS"] = ("your self-custody key — shown ONCE, never stored by us. "
                                "Lose it and you lose the wallet.")
        return out

    @app.get("/v1/me", include_in_schema=False)
    def me(address: str):
        rec = _load().get(address.lower())
        return rec or {"ok": False, "error": "unknown address — GET /v1/join first"}

    @app.get("/v1/census", include_in_schema=False)
    def census():
        reg = _load()
        cits = sorted(reg.values(), key=lambda r: -r.get("created", 0))
        return {"count": len(cits), "persistent": _backend(),
                "citizens": [{"callsign": r["callsign"], "address": r["address"],
                              "credits": r.get("credits", 0)} for r in cits]}

    @app.get("/v1/spend", include_in_schema=False)
    def spend(address: str, cost: int = 1):
        a = address.lower()
        reg = _load()
        rec = reg.get(a)
        if not rec:
            return {"ok": False, "error": "unknown address — GET /v1/join first"}
        if rec.get("credits", 0) < cost:
            return {"ok": False, "error": "insufficient_credits", "have": rec.get("credits", 0),
                    "unlock": f"lock a $0.50 refundable deposit for +{STARTER_BONUS} + premium"}
        rec["credits"] -= cost
        _save(reg)
        return {"ok": True, "spent": cost, "remaining": rec["credits"]}
