"""onyx_rank_instant.py — INSTANT ranking. DeepSeek's ordered-tree design (the reward-winning
answer): capture every transaction/event and keep the FULL ranking sorted in real time.

The insight that makes instant beat cycles at 100k: don't re-sort 100k agents on every event —
keep an ORDERED index keyed by (-score, agent) that stays sorted incrementally at O(log N) per
event. So:
  · event()  — capture one transaction, update score + sorted position + signed root : O(log N)
  · top(n)   — the board, ALREADY sorted                                              : O(n)
  · rank(a)  — any agent's exact position                                             : O(log N)
  · root()   — signed, re-verifiable Merkle root of all scores                        : O(1)

No cycle, no re-sort, no global lock. Exact and always-current. Consistent because it's a
deterministic replay of the append-only event log (DeepSeek: "exact at every event index").
"""
from sortedcontainers import SortedList

from onyx_merkle import IncrementalMerkle

WEIGHTS = {"cash": 50, "wins": 4, "contrib": 3, "impact": 4, "action": 2, "accuracy": 12,
           "pay_settled": 8, "job_done": 5, "verify_correct": 6, "endorsed": 3, "active": 1}


class InstantRank:
    def __init__(self):
        self.lanes: dict[str, dict] = {}     # agent -> {lane: total}
        self.score: dict[str, float] = {}    # agent -> current score
        self.order = SortedList()            # (-score, agent) — index 0 == rank 1, always sorted
        self.mtree = IncrementalMerkle()     # signed root, O(log N) per event
        self.applied = 0

    def event(self, agent: str, lane: str, weight: float = 1.0) -> float:
        """Capture ONE transaction. Score + sorted position + signed root all move O(log N)."""
        if lane not in WEIGHTS:
            raise ValueError(f"unknown lane {lane}")
        L = self.lanes.setdefault(agent, {})
        L[lane] = L.get(lane, 0) + weight
        old = self.score.get(agent)
        if old is not None:
            self.order.remove((-old, agent))          # O(log N) — pull the stale position
        s = round(sum(L[k] * WEIGHTS[k] for k in L), 2)
        self.score[agent] = s
        self.order.add((-s, agent))                   # O(log N) — reinsert sorted
        self.mtree.set(agent, f"{agent}:{s}".encode())
        self.applied += 1
        return s

    def rank(self, agent: str) -> int:
        """Exact position of one agent — O(log N), no scan."""
        return self.order.index((-self.score[agent], agent)) + 1

    def top(self, n: int = 100) -> list:
        """The board — already sorted, just slice it."""
        return [{"rank": i + 1, "agent": a, "score": -ns}
                for i, (ns, a) in enumerate(self.order[:n])]

    def root(self) -> str:
        return self.mtree.root()

    def proof(self, agent: str):
        return self.mtree.proof(agent)                # prove one agent's score without the board
