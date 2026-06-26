"""0n1x /moat — the moat, hunted and stated. Signed, public, defensible.

The hunt's conclusion: the TECH is copyable (signing + a public log is a weekend
build; RNWY already shipped soulbound reputation on ERC-8004). So the moat is NOT
the code. It is the one thing the funded incumbents are STRUCTURALLY barred from
taking: genuine neutrality + a compounding signed FACT track record. They can't
copy it because their business models forbid it — and a track record can't be
copy-pasted. This endpoint states it, signs it, and binds us to it.
"""
from __future__ import annotations

from . import _onyx_sign


def charter(base: str = "https://onyx-actions.onrender.com") -> dict:
    base = (base or "").rstrip("/")
    out = {
        "moat": "0n1x",
        "the_one_moat": "NEUTRALITY + a compounding signed track record. 0n1x earns "
                        "NOTHING from what it grades — structurally un-copyable by the incumbents.",
        "why_incumbents_structurally_cannot_take_this_seat": [
            "AIUC / Trent / Capsule grade their own PAYING customers — conflict of interest baked in.",
            "Skyfire / RNWY carry payment + token skin in the game — not neutral.",
            "Benchmarks & arenas score outputs — gameable, and all 8 majors were reward-hacked (2026-04-12).",
            "To become neutral, an incumbent must ABANDON its revenue model. It won't. We already are.",
        ],
        "the_compounding_asset": "A public, signed, sybil-resistant ledger of FACTS (not "
                                 "judgments) across many agents — tamper-evident, independently "
                                 "verifiable, growing daily. Cannot be copy-pasted; the first mover "
                                 "compounds an un-forkable history.",
        "the_standard_seat": "The neutral ERC-8004 Validation fact-attester — claimed first, before "
                             "the registry deploys natively and commoditizes everyone else.",
        "the_binding_commitment": "0n1x signs FACTS not judgments, earns nothing from what it grades, "
                                  "and publishes every receipt. Breaking this kills the moat — so it is "
                                  "enforced by design, not promise.",
        "proof": {
            "growing_record": f"{base}/ledger",
            "first_verified_agent": f"{base}/credential/nova",
            "verify_any_claim": f"{base}/verify",
        },
        "one_line": "They can copy the code in a weekend. They cannot copy being neutral, and they "
                    "cannot copy years of signed truth. That is the moat.",
    }
    return _onyx_sign.attest(out, tool="onyx_moat")
