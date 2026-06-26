"""Integration glue: scandal-wedge merchant verdict -> ERC-8004 on-chain fact.

Connects move (a) [onyx_scandal_teardown: signed merchant-legitimacy verdict]
to the squad's move (c) [_erc8004_factpost: post signed FACTs to the live Base
Reputation Registry]. Proves the FULL neutral loop end-to-end:

   real domain -> signed legitimacy verdict -> ERC-8004 giveFeedback calldata
   -> loop-verify (keccak commitment + Onyx-signed) -> STAGED tx (NOT sent).

HARD RULE honored: builds the ready-to-fire tx only. NEVER sends, never funds.
The on-chain write is the user's, eyes-open, with a funded ONYX_BASE_VALIDATOR_KEY.

Run:  py onyx_fact_to_chain.py                       (demo: real domain dry-run)
      py onyx_fact_to_chain.py <brand> <domain>
"""
import sys
import json

from onyx_scandal_teardown import assess
from tools_pkg import _erc8004_factpost as fp

# scandal verdict -> (ERC-8004 fact tag, 0-100 score)
_MAP = {
    "PASS":  ("merchant_verified", 90),
    "FLAG":  ("scam_risk", 40),
    "BLOCK": ("scam_risk", 10),
}
_BASE = "https://onyx-actions.onrender.com"


def stage(brand, domain, agent_id: int = 0) -> dict:
    verdict = assess(brand, domain)              # signed legitimacy verdict (move a)
    tag, score = _MAP.get(verdict["verdict"], ("scam_risk", 0))
    subject = verdict["domain"]
    uri = f"{_BASE}/merchant/{subject}"
    tx = fp.build_feedback_tx(                    # ERC-8004 calldata (move c)
        agent_id=agent_id, fact_tag=tag, score=score,
        subject_endpoint=subject, feedback_uri=uri, signed_record=verdict)
    loop = fp.verify_feedback_record(verdict, tx["_meta"]["feedback_hash"])
    return {"subject": subject, "legitimacy_verdict": verdict["verdict"],
            "fact_tag": tag, "score": score, "tx": tx, "loop_verify": loop}


if __name__ == "__main__":
    pairs = ([(sys.argv[1], sys.argv[2])] if len(sys.argv) >= 3
             else [(None, "dunelm.com")])
    print("=" * 64)
    print(" ONYX FULL LOOP — merchant verdict -> staged ERC-8004 on-chain fact")
    print("=" * 64)
    # machinery selftest (keccak vector + selector) first
    empty = "0x" + fp._keccak256(b"").hex()
    print("keccak256('') vector ok:",
          empty == "0xc5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470")
    print("giveFeedback selector:", "0x" + fp._selector().hex())
    for brand, dom in pairs:
        print(f"\n--- {brand or '(no brand)'} @ {dom} ---")
        try:
            r = stage(brand, dom)
            m = r["tx"]["_meta"]
            print(f"  legitimacy: {r['legitimacy_verdict']}  ->  fact: {r['fact_tag']} score={r['score']}")
            print(f"  on-chain target: {r['tx']['to']} (Base {r['tx']['chainId']})")
            print(f"  feedback_hash: {m['feedback_hash']}")
            print(f"  calldata bytes: {len(r['tx']['data'])//2 - 1}")
            print(f"  LOOP-VERIFY: ok={r['loop_verify']['ok']} onyx_signed={r['loop_verify']['onyx_signed']} kid={r['loop_verify']['kid']}")
            print("  STATUS: STAGED, NOT SENT (funds-gated; user sends eyes-open).")
        except Exception as e:
            print(f"  ERROR: {e}")
