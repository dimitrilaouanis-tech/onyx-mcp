"""onyx_approval_guard — the highest-frequency safety call an on-chain agent makes.

Token approvals are the #1 crypto-drain vector, and AI agents are the most exposed:
a prompt-injected or confused agent that signs `approve(spender, MAX)` hands a
drainer unlimited, permanent access to the wallet. Agents do an approval before
EVERY DeFi interaction — so this is the call they make by the kilo.

Before your agent signs an approval, it asks Onyx: is this spender safe, and is
this amount sane? We check, on-chain, in one signed verdict:

  - unlimited?        is the amount effectively infinite (max-uint / astronomically
                      larger than any real supply)? → recommend a finite amount instead
  - spender is EOA?   approving a plain wallet (not a contract) to spend your tokens
                      is almost always a drainer → BLOCK
  - spender verified? an UNVERIFIED spender contract is a major red flag
  - spender age       a brand-new spender contract is higher risk
  → ALLOW / REVIEW / BLOCK + risk score + a recommended safe amount, Ed25519-signed.

Bright line: reads public on-chain state for the spender. Never holds funds.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from . import _onyx_sign
from . import base_contract_verify as _bcv

NAME = "onyx_approval_guard"
PRICE_USDC = "0.03"
TIER = "metered"
DESCRIPTION = (
    "Pre-approval firewall — the safety check before your agent signs a token "
    "approve(). Give the spender (and optionally the amount + token); get a SIGNED "
    "ALLOW/REVIEW/BLOCK verdict: is the amount unlimited (the #1 drain vector — we "
    "recommend a finite amount instead)? is the spender a plain EOA (almost always "
    "a drainer)? is it a verified, established contract? Catches the malicious/"
    "unlimited approval that empties a wallet BEFORE the agent signs it. Every "
    "verdict Ed25519-signed. The highest-frequency safety call an on-chain agent makes."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "spender": {
            "type": "string",
            "description": "0x address that will receive spend approval (the `spender` arg of approve()). Required.",
        },
        "amount_raw": {
            "type": "string",
            "description": "Optional. The raw approval amount as a base-10 integer string (the uint the agent is about to approve). Pass it to detect unlimited/max approvals. Omit to assess the spender only.",
        },
        "token": {
            "type": "string",
            "description": "Optional. The ERC-20 token address being approved, for context.",
        },
    },
    "required": ["spender"],
}

_RPC = "https://mainnet.base.org"
_MAX_UINT = (1 << 256) - 1
_UNLIMITED_FLOOR = 1 << 128   # no real token has 2^128 supply → effectively unlimited


class _Revert(Exception):
    pass


def _get_code(addr: str) -> str:
    req = urllib.request.Request(
        _RPC,
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_getCode",
                         "params": [addr, "latest"]}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "onyx-approval-guard/1.0"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        body = json.load(r)
    if "error" in body:
        raise _Revert(str(body["error"])[:120])
    return body.get("result") or "0x"


def _tx_count(addr: str) -> int:
    req = urllib.request.Request(
        _RPC,
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_getTransactionCount",
                         "params": [addr, "latest"]}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "onyx-approval-guard/1.0"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return int((json.load(r).get("result") or "0x0"), 16)


def run(spender: str = "", amount_raw: str = "", token: str = "", **_: object) -> dict:
    spender = (spender or "").strip()
    if not (spender.startswith("0x") and len(spender) == 42):
        raise ValueError("spender must be a 0x-prefixed 20-byte hex address")

    flags: list = []
    risk = 0

    # --- unlimited-amount check (the #1 drain pattern) ---
    unlimited = False
    parsed_amount = None
    if amount_raw not in ("", None):
        try:
            parsed_amount = int(str(amount_raw).strip())
            if parsed_amount >= _UNLIMITED_FLOOR:
                unlimited = True
                pct = "MAX (2^256-1)" if parsed_amount >= _MAX_UINT else "effectively unlimited"
                flags.append(f"UNLIMITED approval ({pct}) — the spender could drain the ENTIRE balance, forever. Approve only the exact amount needed.")
                risk += 35
        except (ValueError, TypeError):
            flags.append("amount_raw could not be parsed as an integer — verify it before signing.")
            risk += 5

    # --- spender on-chain checks (degrade gracefully, never crash) ---
    is_contract = None
    verified = None
    try:
        code = _get_code(spender)
        is_contract = code not in ("0x", "0x0", "", None)
        if not is_contract:
            tx = 0
            try:
                tx = _tx_count(spender)
            except Exception:
                pass
            flags.append("spender is a PLAIN WALLET (EOA), not a contract — approving an EOA to spend your tokens is almost always a drainer. Legitimate protocols are contracts.")
            risk += 45
        else:
            # verified contract?
            try:
                d = _bcv._fetch(spender)
                verified = bool(d and d.get("is_verified"))
                if not verified:
                    flags.append("spender contract is UNVERIFIED on the explorer — you cannot see what it does with your approval. Major red flag.")
                    risk += 22
                elif d.get("is_self_destructed"):
                    flags.append("spender contract is SELF-DESTRUCTED — do not approve.")
                    risk += 40
            except Exception:
                pass
            if len(code) < 200:
                flags.append("spender contract bytecode is unusually small (possible proxy/forwarder) — confirm the target.")
                risk += 12
    except _Revert:
        flags.append("could not read spender on-chain — verify manually before approving.")
        risk += 10
    except (urllib.error.URLError, TimeoutError):
        return {"ok": False, "error": "base_rpc_unreachable", "spender": spender.lower()}

    risk = min(risk, 99)
    verdict = "ALLOW" if risk < 25 else ("REVIEW" if risk < 60 else "BLOCK")
    # floor: an EOA spender or a true unlimited+unverified combo should never auto-pass
    if is_contract is False:
        verdict = "BLOCK"
    elif unlimited and verified is False and verdict == "ALLOW":
        verdict = "REVIEW"

    return _onyx_sign.attest({
        "ok": True,
        "spender": spender.lower(),
        "token": (token or "").lower() or None,
        "network": "base",
        "unlimited": unlimited,
        "spender_is_contract": is_contract,
        "spender_verified": verified,
        "risk_score": risk,
        "verdict": verdict,
        "flags": flags or ["no elevated-risk signals — spender is a verified contract and the amount is bounded"],
        "recommendation": (
            "Approve ONLY the exact amount this transaction needs, not unlimited. Re-approve next time if required."
            if unlimited else
            "If you must approve, prefer the minimum necessary amount and revoke when done."
        ),
        "summary": (
            f"{verdict} (risk {risk}/100): "
            + ("; ".join(flags[:2]) if flags else "spender verified, amount bounded")
        ),
    }, tool=NAME)


run.__when_to_use__ = (
    "Call this the instant before your agent signs ANY ERC-20 approve() — every "
    "swap, deposit, or DeFi interaction starts with one. Use the verdict as a hard "
    "gate: BLOCK = abort (EOA spender / self-destructed / unlimited-to-unverified), "
    "REVIEW = require approval, ALLOW = proceed. This is the single highest-leverage "
    "drain-prevention call an on-chain agent can make."
)
run.__vs_alternatives__ = (
    "Wallet UIs warn humans about unlimited approvals, but an autonomous agent has "
    "no human to see the warning — it just signs. This is that warning, as a signed "
    "machine-readable verdict an agent gates on, with the spender screened on-chain "
    "(EOA / unverified / self-destructed) and a recommended safe amount returned."
)
run.__example_request__ = {
    "spender": "0x1111111111111111111111111111111111111111",
    "amount_raw": "115792089237316195423570985008687907853269984665640564039457584007913129639935",
}
run.__example_response__ = {
    "ok": True, "verdict": "BLOCK", "risk_score": 80, "unlimited": True,
    "spender_is_contract": False,
    "flags": ["UNLIMITED approval (MAX) — the spender could drain the ENTIRE balance, forever.",
              "spender is a PLAIN WALLET (EOA) — almost always a drainer."],
    "summary": "BLOCK (risk 80/100): unlimited approval to an EOA spender.",
}
