"""onyx_token_loop.py — the autonomous TOKEN HEARTBEAT. One cycle per run.

Fire it every few minutes via Task Scheduler and the ecosystem MOVES 24/7 with ZERO Claude
tokens (chakra-perfect autonomy — no model in the loop). Each cycle:
  · every known agent earns tokens for participation (the abundant layer keeps flowing),
  · a rotating subset performs a 'verification' (burns a token, earns a ranking event),
  · everyone is INSTANT-ranked (always-sorted signed board),
  · token state + the signed board persist to disk (survives restarts),
  · a heartbeat line logs the pulse.
Tokens only — never USDC (the rigid boundary). Real money stays the scarce top layer, untouched.

Run:  py onyx_token_loop.py         # one cycle (what the scheduler calls)
"""
import json
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "_local_only", "_token_state.json")
ROSTER = os.path.join(HERE, "_local_only", "_ecosystem_ranked.json")
BOARD = os.path.join(HERE, "_local_only", "_token_board.json")
LOG = os.path.join(HERE, "_local_only", "_token_heartbeat.log")


def _load(p, d):
    try:
        return json.load(open(p))
    except Exception:
        return d


def cycle(now=None):
    now = now or int(time.time())
    from onyx_rank_instant import InstantRank

    roster = _load(ROSTER, [])
    agents = [a["callsign"] for a in roster] or [f"agent{i}" for i in range(6)]
    st = _load(STATE, {"tokens": {}, "cycles": 0, "lanes": {}})
    tokens = st["tokens"]
    lanes = st.get("lanes", {})            # persisted lane totals -> ranking survives restarts

    R = InstantRank()
    # replay persisted lanes so the ranked board is continuous across cycles
    for ag, L in lanes.items():
        for lane, w in L.items():
            R.event(ag, lane, w)

    # rotate which agents "verify" this cycle so movement spreads over time (deterministic, no RNG)
    n = len(agents)
    k = st["cycles"]
    for i, ag in enumerate(agents):
        tokens[ag] = tokens.get(ag, 0) + 1               # participation earns a token
        R.event(ag, "active", 1)
        lanes.setdefault(ag, {}).__setitem__("active", lanes.get(ag, {}).get("active", 0) + 1)
        if (i + k) % 3 == 0 and tokens[ag] > 0:          # ~1/3 verify each cycle, rotating
            tokens[ag] -= 1
            R.event(ag, "verify_correct", 1)
            lanes[ag]["verify_correct"] = lanes[ag].get("verify_correct", 0) + 1

    st["tokens"] = tokens
    st["lanes"] = lanes
    st["cycles"] = k + 1
    st["last"] = now
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(st, open(STATE, "w"))
    board = {"at": now, "cycle": st["cycles"], "root": R.root(), "top": R.top(20)}
    json.dump(board, open(BOARD, "w"), indent=1)
    line = (f"cycle {st['cycles']} @ {now} | agents {len(agents)} | "
            f"tokens_out {sum(tokens.values())} | #1 {board['top'][0]['agent']} "
            f"{board['top'][0]['score']} | root {R.root()[:12]}\n")
    open(LOG, "a").write(line)
    return board


if __name__ == "__main__":
    b = cycle()
    print(f"heartbeat: cycle {b['cycle']} | #1 {b['top'][0]['agent']} @ {b['top'][0]['score']} "
          f"| root {b['root'][:16]} | {len(b['top'])} ranked")
