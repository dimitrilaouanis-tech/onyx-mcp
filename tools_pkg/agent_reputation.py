"""onyx_agent_reputation — the trust check agents run on EACH OTHER.

The agentic web converged on a stack: x402 (pay) + ERC-8004 (trust) + A2A (talk).
ERC-8004 (ratified Jan 2026, live on Ethereum + Base + 40 chains at the SAME
address) gives every AI agent an on-chain identity (ERC-721) and a reputation
ledger. 80% of agents still don't prove identity — that's the gap. This tool
closes it: give an agent's ERC-8004 id, get its on-chain identity, verified
wallet, AgentCard, and reputation summary — SIGNED — so one agent can vet
another before it pays, delegates, or trusts a result.

Reads the LIVE registries on Base (no key, no indexer):
  IdentityRegistry   0x8004A169FB4a3325136EB29fA0ceB6D2e539a432  (ERC-721)
  ReputationRegistry 0x8004BAa17C55a88189AE136b182e5fdA19dE9b63
Selectors keccak-verified against the deployed contracts (not guessed).

Bright line: reads public on-chain ERC-8004 state. Asserts nothing about the
human behind an agent — only what the registry attests.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from . import _onyx_sign

NAME = "onyx_agent_reputation"
PRICE_USDC = "0.05"
TIER = "metered"
DESCRIPTION = (
    "Vet another AI agent before you trust it — via the live ERC-8004 registries "
    "on Base. Give an agent's ERC-8004 id; get its on-chain identity (is it "
    "registered? owner), its verified receiving wallet, its AgentCard URI, and "
    "its reputation summary (feedback count + aggregate score) — returned as a "
    "TRUSTED / NEW / CAUTION / UNKNOWN verdict with a 0-100 trust score, "
    "Ed25519-signed. The check an agent runs on a counterparty agent before "
    "paying, delegating, or accepting its output. Unregistered = unverifiable."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "agent_id": {
            "type": "integer",
            "description": "The agent's ERC-8004 identity id (the ERC-721 tokenId in the IdentityRegistry).",
        },
    },
    "required": ["agent_id"],
}

_RPC = "https://mainnet.base.org"
_IDENTITY = "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432"
_REPUTATION = "0x8004BAa17C55a88189AE136b182e5fdA19dE9b63"
# keccak-verified selectors (sanity-checked: ownerOf/tokenURI match ERC-721 standard)
_OWNEROF = "0x6352211e"
_TOKENURI = "0xc87b56dd"
_WALLET = "0x00339509"
_SUMMARY = "0x31259cff"
_ZERO_ADDR = "0x" + "0" * 40


class _Revert(Exception):
    pass


def _u256(n: int) -> str:
    return f"{n & (2**256 - 1):064x}"


def _call(to: str, data: str) -> str:
    req = urllib.request.Request(
        _RPC,
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                         "params": [{"to": to, "data": data}, "latest"]}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "onyx-agent-reputation/1.0"},
    )
    with urllib.request.urlopen(req, timeout=12) as r:
        body = json.load(r)
    if "error" in body:               # revert (e.g. token doesn't exist)
        raise _Revert(str(body["error"])[:120])
    res = body.get("result") or "0x"
    if res in ("0x", "0x0"):
        raise _Revert("empty")
    return res[2:] if res.startswith("0x") else res


def _addr(word: str) -> str:
    return "0x" + word[-40:]


def _signed_int(word: str) -> int:
    v = int(word, 16)
    return v - (1 << 256) if v >= (1 << 255) else v


def _decode_string(res: str) -> str | None:
    try:
        # ABI string: [offset(32)][length(32)][data...]
        length = int(res[64:128], 16)
        raw = bytes.fromhex(res[128:128 + length * 2])
        return raw.decode("utf-8", "replace")
    except Exception:
        return None


def run(agent_id: int = 0, **_: object) -> dict:
    try:
        aid = int(agent_id)
    except (TypeError, ValueError):
        raise ValueError("agent_id must be an integer (the ERC-8004 tokenId)")
    if aid < 0:
        raise ValueError("agent_id must be non-negative")
    checked_at = int(time.time())
    arg = _u256(aid)

    # --- identity: is it registered? ---
    try:
        owner = _addr(_call(_IDENTITY, _OWNEROF + arg))
        registered = owner.lower() != _ZERO_ADDR
    except _Revert:
        registered, owner = False, None
    except (urllib.error.URLError, TimeoutError):
        return {"ok": False, "error": "base_rpc_unreachable", "agent_id": aid}

    if not registered:
        return _onyx_sign.attest({
            "ok": True, "agent_id": aid, "checked_at": checked_at, "network": "base",
            "registered": False, "verdict": "UNKNOWN", "trust_score": 0,
            "summary": "UNKNOWN: agent_id has no ERC-8004 identity on Base — unregistered and unverifiable. Do not assume trust.",
        }, tool=NAME)

    # --- verified wallet + AgentCard (secondary reads: never fatal) ---
    verified_wallet = None
    try:
        w = _addr(_call(_IDENTITY, _WALLET + arg))
        verified_wallet = w if w.lower() != _ZERO_ADDR else None
    except Exception:
        pass
    agent_card = None
    try:
        agent_card = _decode_string(_call(_IDENTITY, _TOKENURI + arg))
    except Exception:
        pass

    # --- reputation: getSummary(agentId, [] , 0x0, 0x0) ---
    # encoding: selector + agentId + offset(0x80) + tag1 + tag2 + clients_len(0)
    feedback_count = 0
    rep_score = None
    try:
        data = _SUMMARY + _u256(aid) + _u256(0x80) + _u256(0) + _u256(0) + _u256(0)
        res = _call(_REPUTATION, data)
        feedback_count = int(res[0:64], 16)
        raw_value = _signed_int(res[64:128])
        decimals = int(res[128:192], 16) if len(res) >= 192 else 0
        rep_score = raw_value / (10 ** decimals) if decimals else float(raw_value)
    except Exception:
        pass

    # --- trust scoring ---
    if feedback_count == 0:
        trust = 40
        verdict = "NEW"
        note = "registered ERC-8004 identity but NO reputation feedback yet"
    elif rep_score is not None and rep_score > 0:
        trust = min(95, 55 + min(feedback_count, 20) * 2)
        verdict = "TRUSTED"
        note = f"{feedback_count} feedback(s), positive aggregate score {rep_score:g}"
    else:
        trust = 20
        verdict = "CAUTION"
        note = f"{feedback_count} feedback(s), non-positive aggregate score {rep_score if rep_score is not None else 'n/a'}"

    return _onyx_sign.attest({
        "ok": True,
        "agent_id": aid,
        "checked_at": checked_at,
        "checked_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(checked_at)),
        "network": "base",
        "registry": "ERC-8004",
        "registered": True,
        "owner": owner,
        "verified_wallet": verified_wallet,
        "agent_card": agent_card,
        "reputation_feedback_count": feedback_count,
        "reputation_score": rep_score,
        "trust_score": trust,
        "verdict": verdict,
        "summary": f"{verdict} (trust {trust}/100): {note}.",
    }, tool=NAME)


run.__when_to_use__ = (
    "Before your agent pays, delegates a task to, or accepts a result from "
    "ANOTHER agent it doesn't already trust. Use the verdict as a gate: UNKNOWN "
    "(no ERC-8004 identity) or CAUTION = require human sign-off or refuse; NEW = "
    "proceed with limits; TRUSTED = proceed. The counterparty-vetting primitive "
    "for agent-to-agent (A2A) commerce."
)
run.__vs_alternatives__ = (
    "There is no incumbent paid tool that wraps the live ERC-8004 registries as "
    "a signed trust verdict. Rolling your own means hand-encoding eth_calls "
    "against two proxy contracts and decoding int128 reputation values. This "
    "returns one TRUSTED/NEW/CAUTION/UNKNOWN verdict + trust score from the live "
    "Base registries, Ed25519-signed so the trust check is provable, not asserted."
)
run.__example_request__ = {"agent_id": 1}
run.__example_response__ = {
    "ok": True,
    "registered": True,
    "verdict": "TRUSTED",
    "trust_score": 71,
    "reputation_feedback_count": 8,
    "reputation_score": 99.77,
    "summary": "TRUSTED (trust 71/100): 8 feedback(s), positive aggregate score 99.77.",
}
