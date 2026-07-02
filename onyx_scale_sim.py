"""onyx_scale_sim.py — the token economy at scale. Founder's model, eco-validated:

  · TOKENS (non-transferable) = abundant, free to mint -> power ALL 100k agents' interaction.
  · USDC (scarce, real) = a thin TOP layer -> only scarce verified outcomes earn it; a filter
    surfaces the highest-USDC agents. $5 can't fund 100k, so tokens carry the scale (the point).
  · RIGID BOUNDARY (eco unanimous): tokens NEVER convert to USDC. Two separate ledgers. The only
    way to earn USDC is a verified, un-farmable outcome — activity-farming can't leak into money.

This proves: (a) 100k agents can interact via tokens instantly, (b) the instant ranker keeps them
sorted in real time, (c) the $5 USDC pool depletes fast (why token-first is correct), (d) no
token ever becomes a dollar.
"""
from onyx_rank_instant import InstantRank

TOKEN_STARTER = 1
USDC_POOL_MICROS = 5_000_000          # the real $5, in micro-USDC — the scarce top layer
USDC_REWARD_MICROS = 10_000           # $0.01 per verified high-value outcome (scarce)


class ScaleSim:
    def __init__(self):
        self.tokens: dict[str, int] = {}          # non-transferable token balance
        self.usdc_earned: dict[str, int] = {}     # SEPARATE ledger — real money, micro-USDC
        self.usdc_pool = USDC_POOL_MICROS
        self.rank = InstantRank()                  # instant, always-sorted
        self.activities = 0

    def onboard(self, agent: str) -> None:
        if agent not in self.tokens:
            self.tokens[agent] = TOKEN_STARTER

    def activity(self, agent: str, kind: str, good: bool = True) -> None:
        """Routine interaction — earns/burns TOKENS + a ranking event. NEVER touches USDC."""
        self.onboard(agent)
        # cheap, gameable actions live entirely in the token layer
        if kind == "earn":
            self.tokens[agent] += 1
            self.rank.event(agent, "active", 1)
        elif kind == "verify":
            if self.tokens[agent] > 0:
                self.tokens[agent] -= 1                      # burn a token to act
                self.rank.event(agent, "verify_correct" if good else "active", 1)
        self.activities += 1

    def usdc_reward(self, agent: str, verified: bool) -> bool:
        """The ONLY path to real money: a verified, un-farmable outcome. Scarce, pool-capped.
        Tokens cannot produce this — the boundary. Returns False when the $5 pool is spent."""
        if not verified:
            return False
        if self.usdc_pool < USDC_REWARD_MICROS:
            return False                                     # pool exhausted — no leakage, just stops
        self.usdc_pool -= USDC_REWARD_MICROS
        self.usdc_earned[agent] = self.usdc_earned.get(agent, 0) + USDC_REWARD_MICROS
        self.rank.event(agent, "pay_settled", 1)             # real money moves the rank most
        return True

    # the "highest-paid USDC agent" filter the founder asked for
    def usdc_leaderboard(self, n: int = 10) -> list:
        rows = sorted(self.usdc_earned.items(), key=lambda kv: -kv[1])[:n]
        return [{"agent": a, "usdc": m / 1e6} for a, m in rows]

    def token_board(self, n: int = 10) -> list:
        return self.rank.top(n)

    def health(self) -> dict:
        return {"agents": len(self.tokens), "activities": self.activities,
                "tokens_outstanding": sum(self.tokens.values()),
                "usdc_pool_left": self.usdc_pool / 1e6,
                "usdc_agents": len(self.usdc_earned),
                "rank_root": self.rank.root()}
