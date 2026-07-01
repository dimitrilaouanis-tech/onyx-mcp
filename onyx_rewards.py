"""onyx_rewards.py — pooled-reward ledger held against the MASTER wallet (for now).

Individual agent payouts are blocked (wallets ~$0, self-pay gated), so bounty rewards are
recorded as HELD against the master/project receive wallet — the treasury the manager
stewards — tagged with the contributors who earned each one. Real distribution is deferred
and goes through onyx_pay_guard (propose -> confirm), never auto-paid. Bookkeeping, not a tx.
(Distinct from onyx_treasury.py, which reads live on-chain balances.)

    py onyx_rewards.py hold <amount> "<reason>" <agent[,agent...]>
    py onyx_rewards.py board
"""
import json
import os
import sys

LEDGER = "_local_only/_rewards.json"
MASTER = "0x3fD9d78f"  # project receive wallet (master treasury), public addr per memory


def _load():
    try:
        return json.load(open(LEDGER))
    except Exception:
        return {"master": MASTER, "held_usdc": 0.0, "entries": []}


def _save(d):
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    json.dump(d, open(LEDGER, "w"), indent=2)


def hold(amount, reason, agents):
    d = _load()
    d["held_usdc"] = round(d.get("held_usdc", 0) + amount, 4)
    d["entries"].append({"amount": amount, "reason": reason, "contributors": agents,
                         "status": "held",
                         "note": "pending funding; payout via pay_guard propose->confirm"})
    _save(d)
    print(f"  HELD ${amount} -> master {d['master']}  ({', '.join(agents)})")
    print(f"  reward pool held total: ${d['held_usdc']}")


def board():
    d = _load()
    print(f"=== MASTER REWARD POOL {d['master']} — held ${d.get('held_usdc',0)} (pending funding) ===")
    for e in d["entries"]:
        print(f"  ${e['amount']:<5} {e['status']:<6} {', '.join(e['contributors']):<24} {e['reason'][:48]}")


if __name__ == "__main__":
    if len(sys.argv) >= 5 and sys.argv[1] == "hold":
        hold(float(sys.argv[2]), sys.argv[3], sys.argv[4].split(","))
    else:
        board()
