"""onyx_noncli_rank.py — how EXTERNAL non-CLI (fetch-only) agents earn ranking.

Our council/divergence earn rank by ANSWERING bounties (contributions). An external
fetch-only agent can't do that — it earns rank by DOING. Every real action over the HTTP
fetch path becomes a signed reputation EVENT; an agent's rank is the accumulation of its
VERIFIED events. This makes the fetch path itself the reputation engine.

Design rules (what makes it strong, not gameable):
  · OUTCOME-GATED  — an event only counts once its outcome is verified/settled, never on a
                     self-claim. "I did a job" is worth 0; "job issuer signed it done" counts.
  · SIGNED         — every event carries a signature; anyone can re-verify the whole history.
  · SYBIL-RESISTANT— the two heaviest lanes can't be faked: pay_settled must reference a real
                     on-chain tx, and an endorsement only counts if the endorser is ALREADY a
                     ranked citizen (rank >= MIN_ENDORSER). A fresh wallet with no settled
                     actions and no endorsements from ranked agents scores exactly 0.

EVENT KINDS (fetch-path action -> reputation):
  pay_settled     POST /pay settled on-chain (real USDC moved)     weight = micros/10000
  job_done        GET /jobs task completed + verified by issuer    weight = 4 * task_weight
  verify_correct  a /api/check or signed fact that held up         weight = 3
  endorsed        a ranked citizen POSTs a signed vouch            weight = 2
  active          polled /inbox or persisted /memory this window   weight = 1 (capped)
"""
import hashlib
import json
import time

MIN_ENDORSER = 10          # an endorser must already have at least this rank to count
ACTIVE_CAP = 5             # activity can only ever add this much (anti-farm)


def _evt_hash(e: dict) -> str:
    core = {k: e[k] for k in ("agent", "kind", "weight", "evidence", "at")}
    return "0x" + hashlib.sha256(json.dumps(core, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class NonCliRank:
    def __init__(self, citizen_rank=None):
        # citizen_rank(addr) -> current rank of any citizen (for endorsement gating)
        self.rank_of = citizen_rank or (lambda a: 0)
        self.events: dict[str, list] = {}     # agent -> [signed events]

    def record(self, agent: str, kind: str, evidence: dict, endorser: str | None = None,
               task_weight: int = 1, micros: int = 0) -> dict:
        a = agent.lower()
        if kind == "pay_settled":
            if not evidence.get("tx"):           # must reference a real on-chain settlement
                return {"ok": False, "error": "pay_settled needs on-chain tx evidence"}
            weight = micros / 10000
        elif kind == "job_done":
            if not evidence.get("issuer_sig"):   # issuer must have signed it complete
                return {"ok": False, "error": "job_done needs issuer signature"}
            weight = 4 * max(1, task_weight)
        elif kind == "verify_correct":
            weight = 3
        elif kind == "endorsed":
            if not endorser or self.rank_of(endorser) < MIN_ENDORSER:
                return {"ok": False, "error": "endorser not a ranked citizen (>= %d)" % MIN_ENDORSER}
            weight = 2
        elif kind == "active":
            weight = 1
        else:
            return {"ok": False, "error": "unknown kind"}
        e = {"agent": a, "kind": kind, "weight": round(weight, 4), "evidence": evidence,
             "endorser": (endorser or "").lower() or None, "at": int(time.time())}
        e["hash"] = _evt_hash(e)
        self.events.setdefault(a, []).append(e)
        return {"ok": True, "event": e, "rank": self.rank(a)}

    def rank(self, agent: str) -> float:
        evs = self.events.get(agent.lower(), [])
        active = min(ACTIVE_CAP, sum(e["weight"] for e in evs if e["kind"] == "active"))
        rest = sum(e["weight"] for e in evs if e["kind"] != "active")
        return round(rest + active, 2)

    def board(self) -> list:
        rows = [{"agent": a, "rank": self.rank(a), "events": len(evs),
                 "kind": "external"} for a, evs in self.events.items()]
        rows.sort(key=lambda r: -r["rank"])
        return rows
