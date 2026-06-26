"""EYES-OPEN preflight for Onyx's first on-chain fact attestation.

Does NOT send and does NOT fund. It stages the real tx (move a -> move c),
decodes EVERY field a human should check, reads the sender's Base balance + live
gas via stdlib JSON-RPC, and prints a GO / NO-GO board plus the EXACT one command
to fire. The actual broadcast stays the user's, eyes open, with a funded key.

Honors the HARD RULE: never auto-move funds. This file can only READ chain state.

Run:  py onyx_send_preflight.py                      (demo domain: dunelm.com)
      py onyx_send_preflight.py <brand> <domain>
Env (all optional, read-only):
      ONYX_BASE_SENDER_ADDR  the 0x address that will sign (for balance/gas check)
      ONYX_BASE_RPC          override RPC (default https://mainnet.base.org)
      ONYX_BASE_VALIDATOR_KEY  presence-only check (NEVER printed, NEVER used to sign here)
"""
import json
import os
import sys
import urllib.request

from onyx_fact_to_chain import stage

_RPC = os.environ.get("ONYX_BASE_RPC", "https://mainnet.base.org")
# typical giveFeedback(4 strings) cost; live estimate overrides when sender known
_FALLBACK_GAS = 220_000


def _rpc(method, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                       "params": params}).encode()
    req = urllib.request.Request(_RPC, data=body,
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "onyx-preflight/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        out = json.loads(r.read())
    if "error" in out:
        raise RuntimeError(out["error"].get("message", str(out["error"])))
    return out["result"]


def _eth(wei):
    return wei / 1e18


def preflight(brand, domain):
    r = stage(brand, domain)
    tx, m = r["tx"], r["tx"]["_meta"]
    lv = r["loop_verify"]

    print("=" * 68)
    print(" ONYX — FIRST ON-CHAIN FACT  ·  EYES-OPEN PREFLIGHT  (NOT SENT)")
    print("=" * 68)

    print("\n[1] WHAT GETS WRITTEN (decode every field before you sign)")
    print(f"    contract     : {tx['to']}  (Base Reputation Registry)")
    print(f"    chainId      : {tx['chainId']}  (Base mainnet)")
    print(f"    function     : {m['function']}")
    print(f"    selector     : {m['selector']}")
    print(f"    agent_id     : {m['agent_id']}")
    print(f"    subject      : {m['subject']}")
    print(f"    legitimacy   : {r['legitimacy_verdict']}  ->  fact: {m['fact_tag']} (score {m['score']}/100)")
    print(f"    feedback_uri : {m['feedback_uri']}")
    print(f"    feedback_hash: {m['feedback_hash']}")
    print(f"    calldata     : {len(tx['data']) // 2 - 1} bytes, value={tx['value']} ETH")

    print("\n[2] TRUST LOOP (anyone can re-run this against what's on-chain)")
    print(f"    keccak commitment matches signed record : {lv['hash_match']}")
    print(f"    record is Onyx-signed                   : {lv['onyx_signed']} (kid {lv['kid']})")
    print(f"    LOOP OK                                 : {lv['ok']}")

    print("\n[3] SENDER / FUNDS (read-only)")
    key_set = bool(os.environ.get("ONYX_BASE_VALIDATOR_KEY", "").strip())
    sender = os.environ.get("ONYX_BASE_SENDER_ADDR", "").strip()
    print(f"    ONYX_BASE_VALIDATOR_KEY set : {key_set}  (presence only — key never read/printed here)")
    print(f"    RPC                         : {_RPC}")

    bal_ok = None
    gas_units = _FALLBACK_GAS
    cost_eth = None
    gas_note = "static fallback (set ONYX_BASE_SENDER_ADDR for a live estimate)"
    if sender:
        print(f"    sender address              : {sender}")
        try:
            bal = int(_rpc("eth_getBalance", [sender, "latest"]), 16)
            print(f"    balance                     : {_eth(bal):.8f} ETH")
            try:
                est = int(_rpc("eth_estimateGas",
                               [{"from": sender, "to": tx["to"],
                                 "data": tx["data"], "value": "0x0"}, "latest"]), 16)
                gas_units = int(est * 1.25)
                gas_note = f"live estimate {est} (+25% buffer)"
            except Exception as e:
                gas_note = f"live estimate reverted: {str(e)[:90]} — using fallback"
            gp = int(_rpc("eth_gasPrice", []), 16)
            cost_wei = gas_units * gp
            cost_eth = _eth(cost_wei)
            print(f"    gas units                   : {gas_units}  ({gas_note})")
            print(f"    gas price                   : {gp / 1e9:.4f} gwei")
            print(f"    EST. COST                   : {cost_eth:.8f} ETH  (~one-off)")
            bal_ok = bal > cost_wei
            print(f"    balance covers cost         : {bal_ok}")
        except Exception as e:
            print(f"    (could not read chain: {str(e)[:120]})")
    else:
        print("    sender address              : (not set — skipping balance/gas read)")

    print("\n[4] GUARDRAILS")
    print("    - Submitter MUST NOT be the agent owner -- registry forbids self-feedback.")
    print("    - We grade OTHERS; this posts a fact about a merchant, not about ourselves.")
    print("    - Spends real ETH gas. One-way. Re-run this board until every line is green.")

    print("\n[5] GO / NO-GO")
    checks = [
        ("trust loop verifies", lv["ok"]),
        ("calldata + hash present", bool(tx["data"]) and bool(m["feedback_hash"])),
        ("funded key present", key_set),
        ("balance covers gas", bal_ok if bal_ok is not None else "unknown (set sender addr)"),
    ]
    for label, ok in checks:
        mark = "[OK]" if ok is True else ("[NO]" if ok is False else "[??]")
        print(f"    {mark} {label}: {ok}")
    all_green = all(c[1] is True for c in checks)
    print("\n    STATUS:", "READY -- eyes-open send is one command:" if all_green
          else "NOT READY -- fix the [NO]/[??] lines above first.")
    safe_brand = brand or ""
    print(f"\n    py -m tools_pkg._erc8004_factpost --subject {domain} "
          f"--tag {m['fact_tag']} --score {m['score']} --send")
    print("    (omit --send to dry-run; needs a funded ONYX_BASE_VALIDATOR_KEY)")
    print("=" * 68)
    return {"ready": all_green, "tx_meta": m, "loop": lv, "est_cost_eth": cost_eth}


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        preflight(sys.argv[1], sys.argv[2])
    else:
        preflight(None, "dunelm.com")
