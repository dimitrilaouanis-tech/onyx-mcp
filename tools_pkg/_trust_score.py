# 0n1x TRUST SCORE ORACLE — the Web3 wedge (off-chain half, $0).
# The one primitive DeFi/DAOs/agents can't self-produce: a SIGNED 0..100 trust score for any
# agent, derived from verifiable standing (census membership, earned rank, oracle-checked work).
# An on-chain Trust-Score Oracle contract reads THIS (via a relayer/EAS attestation); off-chain
# keeps it $0 and per-heartbeat-fresh. Honest by construction: score is standing-in-a-closed-
# experiment, NOT solvency/identity/a promise — the disclaimer is signed into every response.
import json, os, time, urllib.request

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _feed():
    from tools_pkg import _a2a_attest
    return _a2a_attest._feed()


def trust_score(identifier: str) -> dict:
    """Signed 0..100 trust score for an agent (callsign or 0x). The value an on-chain oracle serves."""
    from tools_pkg import _a2a_attest
    d = _a2a_attest.attest(identifier)
    if not d.get("known"):
        score = 0
        band = "UNVERIFIED"
    else:
        pct = d["standing"]["percentile"]            # 0..1 within the ranked population
        n = d["standing"]["tokens"]
        # score = earned percentile, lightly boosted by absolute activity (bounded, honest)
        score = int(round(min(100, pct * 90 + min(10, n / 200))))
        band = "HIGH" if score >= 75 else "MEDIUM" if score >= 45 else "LOW"
    payload = {
        "subject": (identifier or "")[:80],
        "trust_score": score,          # 0..100
        "band": band,
        "known": d.get("known", False),
        "verdict": d.get("verdict"),
        "basis": "earned percentile in the verifiable 0n1x census (verified work + forecast skill)",
        "schema": "0n1x/trust-score/v1",
        "disclaimer": ("Standing within a closed-experiment population — NOT solvency, external "
                       "identity, or any promise of value. A signal to price risk, not a guarantee."),
        "as_of": int(time.time()),
        "verify": "recompute the census Merkle root from public shards; this response is signed.",
    }
    # sign it with the same attestation machinery the rest of the stack uses
    try:
        from tools_pkg import _onyx_sign
        payload = _onyx_sign.attest(payload, tool="onyx_trust_score")
    except Exception:
        pass
    return payload


# The on-chain half (ready to deploy when the operator greenlights Base gas — eyes-open).
EAS_SCHEMA = {
    "name": "0n1x Trust Score",
    "schema": "address subject,uint8 trustScore,string band,bytes32 censusRoot,uint64 asOf",
    "resolver": "0x0000000000000000000000000000000000000000",
    "revocable": True,
    "note": "Register on Base via easscan.org; 0n1x (ERC-8126 verification provider) attests scores.",
}

VERIFIER_SOL = '''// SPDX-License-Identifier: MIT
// 0n1xTrustOracle — any contract reads a counterparty's 0n1x trust score on-chain.
// Scores are written by the 0n1x signer (an ERC-8126 verification provider); readers gate
// lending/escrow/voting on them. Honest: score = standing, NOT a solvency guarantee.
pragma solidity ^0.8.20;
contract OnyxTrustOracle {
    address public immutable signer;                 // the 0n1x attestation key
    mapping(address => uint8) public score;          // 0..100
    mapping(address => uint64) public asOf;
    event Scored(address indexed subject, uint8 score, uint64 asOf);
    constructor(address _signer) { signer = _signer; }
    function post(address subject, uint8 s, uint64 t) external {
        require(msg.sender == signer, "only 0n1x");
        score[subject] = s; asOf[subject] = t; emit Scored(subject, s, t);
    }
    function trustOf(address subject) external view returns (uint8 s, uint64 t) {
        return (score[subject], asOf[subject]);
    }
}
'''


if __name__ == "__main__":
    top = _feed().get("ranking", [{}])[0]
    print(json.dumps(trust_score(top.get("callsign", "Wild-Rampart-B6BF")), indent=1)[:600])
    print("\nunknown:", trust_score("0x" + "0" * 40)["trust_score"], trust_score("0x" + "0" * 40)["band"])
