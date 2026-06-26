"""Onyx -> ERC-8004 Reputation Registry: post signed FACT attestations ON-CHAIN.

The Validation Registry (the natural home for fact/outcome validation) is NOT yet
deployed on Base — "still under active update with the TEE community". But the
Reputation Registry IS live (0x8004BAa1...), and its giveFeedback() is general
enough to carry Onyx's real-world fact attestations TODAY:

  giveFeedback(uint256 agentId, int128 value, uint8 valueDecimals,
               string tag1, string tag2, string endpoint,
               string feedbackURI, bytes32 feedbackHash)

We map an Onyx signed verdict -> on-chain feedback:
  tag1   = fact class      (merchant_verified | price_true | wash_flag | scam_risk)
  value  = 0-100 fact score, valueDecimals = 0
  endpoint = the subject (merchant domain / market / agent endpoint)
  feedbackURI  = public Onyx signed-record URL
  feedbackHash = keccak256 of the JCS-canonical signed verdict (on-chain commitment)

This module BUILDS the calldata + an unsigned tx. It does NOT auto-send or
auto-fund (HARD RULE: never auto-move funds). Pass --send only with eyes open and
a funded key in ONYX_BASE_VALIDATOR_KEY; default is dry-run.

Stdlib-only (incl. a pure-python keccak256). Underscore-prefixed -> not a tool.
"""
from __future__ import annotations

import json
import os
import sys

REPUTATION_REGISTRY = "0x8004BAa17C55a88189AE136b182e5fdA19dE9b63"
CHAIN_ID = 8453  # Base mainnet
FACT_TAGS = ("merchant_verified", "price_true", "wash_flag", "scam_risk", "liveness")
_SIG = "giveFeedback(uint256,int128,uint8,string,string,string,string,bytes32)"


# ---- pure-python keccak-256 (Ethereum), no deps -----------------------------
def _keccak256(data: bytes) -> bytes:
    RC = [0x0000000000000001, 0x0000000000008082, 0x800000000000808A,
          0x8000000080008000, 0x000000000000808B, 0x0000000080000001,
          0x8000000080008081, 0x8000000000008009, 0x000000000000008A,
          0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
          0x000000008000808B, 0x800000000000008B, 0x8000000000008089,
          0x8000000000008003, 0x8000000000008002, 0x8000000000000080,
          0x000000000000800A, 0x800000008000000A, 0x8000000080008081,
          0x8000000000008080, 0x0000000080000001, 0x8000000080008008]
    ROT = [[0, 36, 3, 41, 18], [1, 44, 10, 45, 2], [62, 6, 43, 15, 61],
           [28, 55, 25, 21, 56], [27, 20, 39, 8, 14]]
    M = (1 << 64) - 1

    def rol(x, n):
        return ((x << n) | (x >> (64 - n))) & M

    rate = 136  # 1088 bits for keccak-256
    # pad (keccak pad: 0x01 ... 0x80)
    msg = bytearray(data)
    msg.append(0x01)
    while len(msg) % rate != 0:
        msg.append(0x00)
    msg[-1] ^= 0x80

    S = [[0] * 5 for _ in range(5)]
    for off in range(0, len(msg), rate):
        block = msg[off:off + rate]
        for i in range(rate // 8):
            lane = int.from_bytes(block[i * 8:i * 8 + 8], "little")
            S[i % 5][i // 5] ^= lane
        for rnd in range(24):
            C = [S[x][0] ^ S[x][1] ^ S[x][2] ^ S[x][3] ^ S[x][4] for x in range(5)]
            D = [C[(x - 1) % 5] ^ rol(C[(x + 1) % 5], 1) for x in range(5)]
            for x in range(5):
                for y in range(5):
                    S[x][y] ^= D[x]
            B = [[0] * 5 for _ in range(5)]
            for x in range(5):
                for y in range(5):
                    B[y][(2 * x + 3 * y) % 5] = rol(S[x][y], ROT[x][y])
            for x in range(5):
                for y in range(5):
                    S[x][y] = B[x][y] ^ ((~B[(x + 1) % 5][y]) & B[(x + 2) % 5][y])
            S[0][0] ^= RC[rnd]
    out = bytearray()
    for i in range(4):  # 32 bytes
        out += S[i % 5][i // 5].to_bytes(8, "little")
    return bytes(out)


def _selector() -> bytes:
    return _keccak256(_SIG.encode())[:4]


# ---- minimal ABI encoding for the giveFeedback layout -----------------------
def _u256(n: int) -> bytes:
    return (n & ((1 << 256) - 1)).to_bytes(32, "big")


def _i256(n: int) -> bytes:
    return (n & ((1 << 256) - 1)).to_bytes(32, "big")  # two's complement


def _bytes32(hexstr: str) -> bytes:
    h = hexstr.lower().removeprefix("sha256:").removeprefix("0x")
    b = bytes.fromhex(h[:64].rjust(64, "0"))
    return b[:32].rjust(32, b"\x00")


def _enc_string(s: str) -> bytes:
    raw = s.encode()
    out = _u256(len(raw)) + raw
    if len(raw) % 32:
        out += b"\x00" * (32 - len(raw) % 32)
    return out


def build_calldata(agent_id: int, value: int, value_decimals: int,
                   tag1: str, tag2: str, endpoint: str,
                   feedback_uri: str, feedback_hash: str) -> str:
    """ABI-encode giveFeedback(...). 4 dynamic strings (tag1,tag2,endpoint,uri),
    rest static. Returns 0x-hex calldata."""
    head = b""
    tail = b""
    dyn = [tag1, tag2, endpoint, feedback_uri]
    # head order: agentId, value, valueDecimals, off(tag1), off(tag2),
    #             off(endpoint), off(uri), feedbackHash
    base_off = 8 * 32
    encoded_dyn = [_enc_string(s) for s in dyn]
    offs, run = [], base_off
    for e in encoded_dyn:
        offs.append(run)
        run += len(e)
    head += _u256(agent_id)
    head += _i256(value)
    head += _u256(value_decimals)
    head += _u256(offs[0]) + _u256(offs[1]) + _u256(offs[2]) + _u256(offs[3])
    head += _bytes32(feedback_hash)
    for e in encoded_dyn:
        tail += e
    return "0x" + (_selector() + head + tail).hex()


def keccak_of_canonical(signed_record: dict) -> str:
    """keccak256 over the JCS-canonical signed verdict = the on-chain commitment."""
    from . import _onyx_sign
    canonical = _onyx_sign._jcs(signed_record).encode()
    return "0x" + _keccak256(canonical).hex()


def build_feedback_tx(agent_id: int, fact_tag: str, score: int,
                      subject_endpoint: str, feedback_uri: str,
                      signed_record: dict, tag2: str = "onyx_fact") -> dict:
    """Map an Onyx signed fact -> a ready-to-broadcast Reputation Registry tx.
    Builds calldata only; does NOT send. score 0-100, valueDecimals 0."""
    if fact_tag not in FACT_TAGS:
        raise ValueError(f"fact_tag must be one of {FACT_TAGS}")
    score = max(0, min(100, int(score)))
    fhash = keccak_of_canonical(signed_record)
    data = build_calldata(agent_id, score, 0, fact_tag, tag2,
                          subject_endpoint, feedback_uri, fhash)
    return {
        "to": REPUTATION_REGISTRY,
        "data": data,
        "value": 0,
        "chainId": CHAIN_ID,
        "_meta": {
            "function": _SIG,
            "selector": "0x" + _selector().hex(),
            "agent_id": agent_id, "fact_tag": fact_tag, "score": score,
            "subject": subject_endpoint, "feedback_uri": feedback_uri,
            "feedback_hash": fhash,
            "note": "Reputation Registry is LIVE on Base. Requires ETH gas (~$0.01-0.05). "
                    "NOT auto-sent. Submitter must NOT be the agent owner (we grade others).",
        },
    }


_KEY_ENV = "ONYX_BASE_VALIDATOR_KEY"
_RPC_ENV = "ONYX_BASE_RPC"
_DEFAULT_RPC = "https://mainnet.base.org"


def send_feedback_tx(tx: dict) -> dict:
    """EYES-OPEN ONLY. Sign + broadcast a built fact tx to Base. Requires a funded
    key in ONYX_BASE_VALIDATOR_KEY. Spends real ETH gas — never call without the
    user's explicit go. Returns {sent, tx_hash, ...} or {sent:False, reason}."""
    pk = os.environ.get(_KEY_ENV, "").strip()
    if not pk:
        return {"sent": False, "reason": f"no key in {_KEY_ENV} — refusing to send "
                "(no auto-fund). Set a funded Base key and retry."}
    try:
        from web3 import Web3
    except ImportError:
        return {"sent": False, "reason": "web3 not installed"}
    rpc = os.environ.get(_RPC_ENV, _DEFAULT_RPC)
    w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 30,
              "headers": {"User-Agent": "onyx/1.0"}}))
    acct = w3.eth.account.from_key(pk if pk.startswith("0x") else "0x" + pk)
    body = {
        "from": acct.address,
        "to": Web3.to_checksum_address(tx["to"]),
        "data": tx["data"],
        "value": 0,
        "chainId": CHAIN_ID,
        "nonce": w3.eth.get_transaction_count(acct.address),
    }
    try:
        body["gas"] = int(w3.eth.estimate_gas(body) * 1.25)
    except Exception as e:
        return {"sent": False, "reason": f"gas estimate reverted: {str(e)[:160]} "
                "(submitter may be the agent owner — registry forbids self-feedback)"}
    fee = w3.eth.fee_history(1, "latest")["baseFeePerGas"][-1]
    tip = w3.to_wei(0.001, "gwei")
    body["maxPriorityFeePerGas"] = tip
    body["maxFeePerGas"] = fee * 2 + tip
    signed = acct.sign_transaction(body)
    h = w3.eth.send_raw_transaction(signed.raw_transaction)
    return {"sent": True, "tx_hash": h.hex(), "from": acct.address,
            "explorer": f"https://basescan.org/tx/0x{h.hex().lstrip('0x')}",
            "gas": body["gas"], "rpc": rpc}


def verify_feedback_record(signed_record: dict, claimed_feedback_hash: str) -> dict:
    """Close the loop: given a fetched signed record + the on-chain feedbackHash,
    confirm (a) the keccak commitment matches and (b) Onyx actually signed it.
    Anyone can run this against what's on-chain — that's the whole trust model."""
    from . import _onyx_sign
    recomputed = keccak_of_canonical(signed_record)
    want = "0x" + claimed_feedback_hash.lower().removeprefix("0x")
    hash_ok = recomputed == want
    onyx = _onyx_sign.is_onyx_signed(signed_record)
    return {
        "ok": bool(hash_ok and onyx.get("ok")),
        "hash_match": hash_ok,
        "recomputed_hash": recomputed,
        "claimed_hash": want,
        "onyx_signed": onyx.get("onyx_signed", False),
        "kid": onyx.get("kid"),
        "reason": None if (hash_ok and onyx.get("ok"))
                  else ("hash_mismatch" if not hash_ok else onyx.get("reason")),
    }


def _cli():
    """Build a ready-to-fire fact tx from a REAL Onyx check, or verify a record.
      --subject DOMAIN --tag merchant_verified --score 0-100 [--agent-id N] [--out FILE]
      --verify RECORD.json --hash 0x...
    Writes the signed record + tx JSON; never sends (no auto-fund)."""
    a = sys.argv
    if "--verify" in a:
        path = a[a.index("--verify") + 1]
        rec = json.load(open(path, encoding="utf-8"))
        if "--hash" in a:
            h = a[a.index("--hash") + 1]
        else:  # read the companion tx file: _record.json -> _tx.json
            txp = path.replace("_record.json", "_tx.json")
            h = json.load(open(txp, encoding="utf-8"))["_meta"]["feedback_hash"]
        print(json.dumps(verify_feedback_record(rec, h), indent=2))
        return
    def opt(k, d=None):
        return a[a.index(k) + 1] if k in a else d
    subject = opt("--subject")
    if not subject:
        return _demo()
    tag = opt("--tag", "merchant_verified")
    score = int(opt("--score", "0"))
    agent_id = int(opt("--agent-id", "0"))
    from . import _onyx_sign
    record = _onyx_sign.attest(
        {"subject": subject, "fact_class": tag, "score": score,
         "tool": "onyx_fact_attestation"}, tool="onyx_fact_attestation")
    uri = opt("--uri", f"{_BASE_URL}/check?url={subject}")
    tx = build_feedback_tx(agent_id, tag, score, subject, uri, record)
    out = opt("--out", "_first_fact")
    json.dump(record, open(out + "_record.json", "w", encoding="utf-8"), indent=2)
    json.dump(tx, open(out + "_tx.json", "w", encoding="utf-8"), indent=2)
    chk = verify_feedback_record(record, tx["_meta"]["feedback_hash"])
    print(f"WROTE {out}_record.json + {out}_tx.json")
    print(f"  subject={subject} tag={tag} score={score} -> {tx['to']} (Base {tx['chainId']})")
    print(f"  loop-verify: ok={chk['ok']} onyx_signed={chk['onyx_signed']} kid={chk['kid']}")
    if "--send" in a:
        print("  --send given: broadcasting (EYES-OPEN, spends gas)...")
        print("  " + json.dumps(send_feedback_tx(tx)))
    else:
        print("  NOT sent. Add --send with a funded ONYX_BASE_VALIDATOR_KEY to go live.")


_BASE_URL = "https://onyx-actions.onrender.com"


def _demo():
    """Build a sample tx with a fake signed record (no send, no key needed)."""
    sample = {"subject": "shady-store.example", "verdict": "high_risk",
              "trust_score": 12, "tool": "onyx_merchant_fact_check"}
    tx = build_feedback_tx(
        agent_id=42, fact_tag="scam_risk", score=12,
        subject_endpoint="shady-store.example",
        feedback_uri="https://onyx-actions.onrender.com/check?url=shady-store.example",
        signed_record=sample)
    print(json.dumps(tx, indent=2))
    print("\nselftest selector(giveFeedback...) =", "0x" + _selector().hex())
    # keccak self-check: keccak256("") known vector
    empty = "0x" + _keccak256(b"").hex()
    expect = "0xc5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"
    print("keccak256('') ok:", empty == expect)


if __name__ == "__main__":
    _cli()
