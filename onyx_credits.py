"""onyx_credits.py — the 0n1x metering-credit engine (the 'tokenised' system, done to survive).

The founder's call: ship a tokenised system NOW to activate agents. The full Eco (6/6 divergence
+ onyx-mind, unanimous) + the standards discipline converge on ONE safe shape:

  · NON-TRANSFERABLE — there is deliberately NO transfer() method. Credits can't move between
    agents, so there's no market, no listing, no speculation, no securities exposure, and no
    incentive to game ratings to pump a price. It's still fully "tokenised": free to mint, burned
    for access, refilled with USDC.
  · OFF-CHAIN SIGNED MERKLE LEDGER (DeepSeek) — zero gas, scales to millions; the root is
    re-verifiable by anyone.
  · FREE STAGED STARTER (Kimi) — a little now, more after the first legitimate use (anti-Sybil).
  · REFUNDABLE $0.50 ACTIVATION DEPOSIT to unlock premium (DeepSeek) — a Sybil filter that costs
    the agent nothing (it's refundable), but makes farming 100k free identities pointless.
  · REPUTATION = EARNED DISCOUNT (Perplexity/Kimi) — higher Census rank => more credits per USDC
    on top-up, i.e. a cheaper effective price. Never free credits for rank; a discount on refill.
"""
import hashlib
import time

from onyx_merkle import IncrementalMerkle

# Numbers set by the divergence (Perplexity + DeepSeek + onyx-mind): keep the FREE upfront a
# TASTE (1 call — enough to see a result, not enough to farm), and release the small bonus only
# after an ECONOMIC action (locking the $0.50 deposit). Worst case: 100k x 3 x $0.001 = $300,
# leaving ~$700 of the $1k for spikes. (20+80 would have burned the whole budget in month one.)
STARTER = 1                  # free credits at onboard — a single "taste" ping
STARTER_BONUS = 2            # released only after the $0.50 deposit is locked (economic action)
MIN_ACTIVATION_MICROS = 500_000   # $0.50 refundable deposit unlocks premium
CREDIT_PRICE_MICROS = 10_000      # base: 1 credit = $0.01  (100 credits per $1)


def rank_discount(rank: int) -> float:
    """Higher earned rank => cheaper effective price (more credits per USDC). Never free."""
    if rank >= 50:
        return 0.25       # 4x credits per dollar
    if rank >= 30:
        return 0.50
    if rank >= 10:
        return 0.75
    return 1.00


class Credits:
    def __init__(self):
        self.bal: dict[str, int] = {}        # agent -> credits (non-transferable)
        self.activated: dict[str, int] = {}  # agent -> refundable deposit micros
        self.bonus_released: set[str] = set()
        self.mtree = IncrementalMerkle()     # O(log n) balance root — no per-write full rebuild

    def _touch(self, a: str) -> None:
        self.mtree.set(a, f"{a}:{self.bal.get(a, 0)}".encode())

    def grant_starter(self, agent: str) -> dict:
        a = agent.lower()
        if a in self.bal:
            return {"ok": False, "error": "already onboarded", "credits": self.bal[a]}
        self.bal[a] = STARTER
        self._touch(a)
        return {"ok": True, "credits": STARTER,
                "note": f"staged — {STARTER_BONUS} more after your first legitimate query"}

    def release_bonus(self, agent: str) -> dict:
        a = agent.lower()
        if a in self.bonus_released:
            return {"ok": False, "error": "bonus already released"}
        self.bonus_released.add(a)
        self.bal[a] = self.bal.get(a, 0) + STARTER_BONUS
        self._touch(a)
        return {"ok": True, "credits": self.bal[a]}

    def activate(self, agent: str, usdc_micros: int) -> dict:
        if usdc_micros < MIN_ACTIVATION_MICROS:
            return {"ok": False, "error": f"minimum activation deposit is ${MIN_ACTIVATION_MICROS/1e6:.2f} (refundable)"}
        self.activated[agent.lower()] = usdc_micros
        return {"ok": True, "activated": True, "deposit_micros": usdc_micros, "refundable": True,
                "why": "Sybil filter — costs you nothing (refundable), makes mass free-farming pointless"}

    def topup(self, agent: str, usdc_micros: int, rank: int = 0) -> dict:
        # rank gives a DISCOUNT: more credits per USDC. (reputation = earned discount)
        credits = int(usdc_micros / (CREDIT_PRICE_MICROS * rank_discount(rank)))
        a = agent.lower()
        self.bal[a] = self.bal.get(a, 0) + credits
        self._touch(a)
        return {"ok": True, "added": credits, "balance": self.bal[a],
                "rank_discount": rank_discount(rank)}

    def burn(self, agent: str, cost: int = 1) -> dict:
        a = agent.lower()
        if a not in self.activated:
            return {"ok": False, "error": "premium requires activation deposit ($0.50, refundable)"}
        if self.bal.get(a, 0) < cost:
            return {"ok": False, "error": "insufficient_credits", "have": self.bal.get(a, 0),
                    "need": cost, "topup": "send USDC to refill"}
        self.bal[a] -= cost
        self._touch(a)
        return {"ok": True, "burned": cost, "remaining": self.bal[a]}

    def merkle_root(self) -> str:
        # O(1): incremental Merkle keeps the balance root current on every credit change —
        # no per-request rebuild (the 100k bottleneck). Re-verifiable via mtree.proof(agent).
        return self.mtree.root()

    # NOTE: there is intentionally NO transfer() method. Credits never move between agents.
    # That single omission is what keeps this a neutral trust product instead of a security.
