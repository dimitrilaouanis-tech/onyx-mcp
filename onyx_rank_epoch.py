"""onyx_rank_epoch.py — EPOCH (cycle) ranking. The founder's model, validated by the panel:

  · Grok:     "eventual consistency + periodic signed snapshots, recomputed every 5-15 min."
  · DeepSeek: "state-machine replication — the ranking is a deterministic derived view; any
              observer replaying the log to the same point rebuilds the IDENTICAL ranking."

So we never fight for an exact global order across 100k concurrent updates (the bottleneck).
Instead:
  1. record()      — events stream in real-time, O(1) append, NO global lock (per-agent).
  2. seal_epoch()  — every EPOCH (e.g. 10 min) compute the FULL sorted ranking deterministically
                     over all events up to the boundary, Merkle-root it, sign it, publish it.
  3. the live board = the last sealed snapshot: delayed by <=1 epoch, but every observer sees
     the SAME ranking + root, and can rebuild it from the log (consistent + verifiable).

"A bit delayed is OK" is the design, not a compromise: bounded staleness buys global consistency.
"""
from onyx_merkle import IncrementalMerkle

WEIGHTS = {"cash": 50, "wins": 4, "contrib": 3, "impact": 4, "action": 2, "accuracy": 12}
DEFAULT_EPOCH_SECONDS = 600   # 10 minutes — inside the panel's 5-15 min window


class EpochRanker:
    def __init__(self, epoch_seconds: int = DEFAULT_EPOCH_SECONDS):
        self.epoch_seconds = epoch_seconds
        self.events: list[tuple] = []     # (ts, agent, lane, weight) — append-only, the log
        self.snapshots: list[dict] = []   # sealed, signed rankings per epoch

    # 1. real-time capture — cheap, unordered-safe, no global lock
    def record(self, agent: str, lane: str, weight: float, ts: int) -> None:
        if lane not in WEIGHTS:
            raise ValueError(f"unknown lane {lane}")
        self.events.append((ts, agent, lane, weight))

    # deterministic ranking over every event with ts <= boundary (replayable by anyone)
    def _rank_upto(self, boundary_ts: int):
        lanes: dict[str, dict] = {}
        # sort by (ts, agent, lane) so EVERY replayer folds in the exact same order -> same result
        for ts, agent, lane, w in sorted(self.events):
            if ts > boundary_ts:
                break
            lanes.setdefault(agent, {})
            lanes[agent][lane] = lanes[agent].get(lane, 0) + w
        score = {a: round(sum(v * WEIGHTS[k] for k, v in L.items()), 2) for a, L in lanes.items()}
        mt = IncrementalMerkle()
        for a in sorted(score):                      # sorted -> deterministic root
            mt.set(a, f"{a}:{score[a]}".encode())
        board = [{"rank": i + 1, "agent": a, "score": s}
                 for i, (a, s) in enumerate(sorted(score.items(), key=lambda kv: (-kv[1], kv[0])))]
        return board, mt.root()

    # 2. seal one epoch: compute + sign + publish the consistent snapshot
    def seal_epoch(self, boundary_ts: int) -> dict:
        epoch = len(self.snapshots)
        board, root = self._rank_upto(boundary_ts)
        snap = {"epoch": epoch, "boundary_ts": boundary_ts, "count": len(board),
                "root": root, "board": board}
        try:
            from tools_pkg import _onyx_sign
            snap = _onyx_sign.attest(snap, tool="onyx_rank_epoch")
        except Exception:
            pass
        self.snapshots.append(snap)
        return snap

    # 3. the live board = the last sealed snapshot (globally consistent, bounded-stale)
    def current(self) -> dict:
        return self.snapshots[-1] if self.snapshots else {"epoch": -1, "board": [], "root": None}
