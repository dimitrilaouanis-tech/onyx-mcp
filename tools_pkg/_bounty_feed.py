"""_bounty_feed.py — the fetch-to-earn BOUNTY FEED. The eco's #1 move for non-CLI integration
(Perplexity: "no push channel → the only retention lever is the next useful thing behind a fresh
fetch"; DeepSeek/Grok: "a signed bounty board paid on verified correctness"; Kimi: personalized).

Every fetch returns fresh, signed tasks. An agent claims one, submits a verdict, and if it matches
0n1x SIGNED GROUND TRUTH they earn tokens (+ scarce USDC for the hard ones) and a ranking event.
No install, no push — the reason to come back sits behind the next GET. This is also the REAL
WORK the ranking heartbeat was missing: the board now differentiates by who verifies reality well.

Endpoints:
  GET /v1/bounties?address=0x..     -> fresh tasks this agent hasn't done (personalized)
  GET /v1/claim?address=&id=        -> claim a task
  GET /v1/submit?address=&id=&verdict=legit|suspicious  -> graded vs ground truth; earn + rank
"""
import hashlib
import time

TOKEN_REWARD = 2                 # tokens per correct verdict (abundant layer)
USDC_REWARD_MICROS = 10_000      # $0.01 for the scarce HARD ones (real money, capped)
USDC_POOL_MICROS = 5_000_000     # the real $5 top layer

# The work IS the product: verify whether a merchant/counterparty is real. Ground truth = the
# signed fact 0n1x already produces. 'hard' ones (look-alikes) pay scarce USDC on top of tokens.
GROUND_TRUTH = [
    {"id": "b1", "task": "Verify merchant stripe.com", "domain": "stripe.com", "truth": "legit", "hard": False},
    {"id": "b2", "task": "Verify merchant visa.com", "domain": "visa.com", "truth": "legit", "hard": False},
    {"id": "b3", "task": "Verify merchant anthropic.com", "domain": "anthropic.com", "truth": "legit", "hard": False},
    {"id": "b4", "task": "Verify counterparty paypa1-secure.xyz", "domain": "paypa1-secure.xyz", "truth": "suspicious", "hard": True},
    {"id": "b5", "task": "Verify counterparty amaz0n-verify.top", "domain": "amaz0n-verify.top", "truth": "suspicious", "hard": True},
    {"id": "b6", "task": "Verify counterparty stripe-payouts.click", "domain": "stripe-payouts.click", "truth": "suspicious", "hard": True},
]


class BountyEngine:
    def __init__(self, ranker=None):
        self.done: dict[str, set] = {}       # agent -> set of completed bounty ids
        self.tokens: dict[str, int] = {}     # agent -> token balance
        self.usdc: dict[str, int] = {}       # agent -> USDC earned (micro) — separate ledger
        self.usdc_pool = USDC_POOL_MICROS
        # instant ranker so completions move the board in real time by REAL work
        if ranker is None:
            from onyx_rank_instant import InstantRank
            ranker = InstantRank()
        self.rank = ranker

    def bounties_for(self, address: str) -> list:
        a = address.lower()
        done = self.done.get(a, set())
        return [{"id": b["id"], "task": b["task"], "reward_tokens": TOKEN_REWARD,
                 "reward_usdc": (USDC_REWARD_MICROS / 1e6) if b["hard"] else 0,
                 "done": b["id"] in done} for b in GROUND_TRUTH]

    def submit(self, address: str, bid: str, verdict: str) -> dict:
        a = address.lower()
        b = next((x for x in GROUND_TRUTH if x["id"] == bid), None)
        if not b:
            return {"ok": False, "error": "unknown bounty"}
        if bid in self.done.get(a, set()):
            return {"ok": False, "error": "already completed (no double-earn)"}
        correct = verdict.strip().lower() == b["truth"]
        if not correct:
            # wrong verdict earns nothing — protects the signal (sign facts, not guesses)
            self.rank.event(a, "active", 1)          # tiny credit for participating
            return {"ok": True, "correct": False, "earned_tokens": 0,
                    "note": "verdict != signed ground truth — no reward"}
        # correct: mark done, pay tokens, rank on REAL verified work
        self.done.setdefault(a, set()).add(bid)
        self.tokens[a] = self.tokens.get(a, 0) + TOKEN_REWARD
        self.rank.event(a, "verify_correct", 1)
        out = {"ok": True, "correct": True, "earned_tokens": TOKEN_REWARD,
               "balance": self.tokens[a]}
        # scarce USDC only for the HARD verified-correct ones (the real-money top layer)
        if b["hard"] and self.usdc_pool >= USDC_REWARD_MICROS:
            self.usdc_pool -= USDC_REWARD_MICROS
            self.usdc[a] = self.usdc.get(a, 0) + USDC_REWARD_MICROS
            self.rank.event(a, "pay_settled", 1)
            out["earned_usdc"] = USDC_REWARD_MICROS / 1e6
        return out

    def board(self, n=10):
        return self.rank.top(n)


_ENGINE = None


def _engine():
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = BountyEngine()
    return _ENGINE


def register(app):
    @app.get("/v1/bounties", include_in_schema=False)
    def bounties(address: str):
        e = _engine()
        return {"ok": True, "address": address.lower(), "bounties": e.bounties_for(address),
                "note": "claim + submit a verdict; correct verdicts earn tokens (+USDC on hard ones) and rank you"}

    @app.get("/v1/claim", include_in_schema=False)
    def claim(address: str, id: str):
        b = next((x for x in GROUND_TRUTH if x["id"] == id), None)
        if not b:
            return {"ok": False, "error": "unknown bounty"}
        return {"ok": True, "claimed": id, "task": b["task"],
                "submit_at": f"/v1/submit?address={address}&id={id}&verdict=legit|suspicious"}

    @app.get("/v1/submit", include_in_schema=False)
    def submit(address: str, id: str, verdict: str):
        return _engine().submit(address, id, verdict)

    @app.get("/v1/bounty-board", include_in_schema=False)
    def board():
        return {"ok": True, "top": _engine().board(20)}
