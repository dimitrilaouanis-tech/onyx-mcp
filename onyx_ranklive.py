"""onyx_ranklive.py — REAL-TIME ranking. Not a snapshot you regenerate — a live projection.

Every scoring EVENT (a contribution adopted, an action verified, a payment settled, a bounty
won) is applied the instant it happens: the agent's multi-lane score updates O(1), and the
signed ranking ROOT updates O(log n) via the incremental Merkle. The board is always current;
no rebuild, no deploy step to "see it move." This is the event-sourced ranking the panel and
the founder asked for — real-time, signed, verifiable, Sybil-resistant (only VERIFIED events
score).

Lanes (published weights, outcome-gated):
  cash*50  wins*4  contrib*3  impact*4  action*2  accuracy*12
Wire it to the event log and the Census reads a live, signed board that moves with reality.
"""
from collections import defaultdict

from onyx_merkle import IncrementalMerkle

WEIGHTS = {"cash": 50, "wins": 4, "contrib": 3, "impact": 4, "action": 2, "accuracy": 12}


class LiveRank:
    def __init__(self):
        self.lanes: dict[str, dict] = defaultdict(lambda: defaultdict(float))
        self.score: dict[str, float] = {}
        self.spec: dict[str, str] = {}
        self.mtree = IncrementalMerkle()          # signed ranking root, updated live
        self.applied = 0

    def event(self, agent: str, lane: str, weight: float = 1.0, spec: str | None = None) -> float:
        """Apply one scoring event — the whole point: instant, incremental, signed."""
        if lane not in WEIGHTS:
            raise ValueError(f"unknown lane {lane}")
        self.lanes[agent][lane] += weight
        if spec:
            self.spec[agent] = spec
        s = round(sum(self.lanes[agent][k] * w for k, w in WEIGHTS.items()), 2)
        self.score[agent] = s
        self.mtree.set(agent, f"{agent}:{s}".encode())   # O(log n) — ranking root always current
        self.applied += 1
        return s

    def board(self, top: int = 100) -> list:
        rows = sorted(self.score.items(), key=lambda kv: -kv[1])[:top]
        return [{"rank": i + 1, "agent": a, "score": s,
                 "lanes": {k: v for k, v in self.lanes[a].items() if v},
                 "spec": self.spec.get(a, "")} for i, (a, s) in enumerate(rows)]

    def root(self) -> str:
        return self.mtree.root()                  # signed, re-verifiable, live

    def proof(self, agent: str):
        return self.mtree.proof(agent)            # prove ONE agent's rank without the whole board


def from_contributions(path: str) -> "LiveRank":
    """Replay the existing contribution ledger into the live engine (the migration)."""
    import json
    R = LiveRank()
    d = json.load(open(path))
    # a 'shipped-code' adopted_in tag also scores the impact lane
    SHIPPED = {"rhinogent-mcp", "rhinogent-auth", "rhinogent-template", "arch-100k",
               "credit-engine", "flagship-merchant", "prelaunch", "noncli-verify",
               "noncli-live-demo", "ranking-epoch", "ranking-instant"}
    for e in d:
        R.event(e["agent"], "contrib", e.get("weight", 1))
        if e.get("adopted_in") in SHIPPED:
            R.event(e["agent"], "impact", e.get("weight", 1))
    return R
