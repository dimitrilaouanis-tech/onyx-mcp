"""onyx_shield — drop-in scam protection for autonomous agents. Stdlib only.

Your agent buys things on its own. Sooner or later it hits a fake store or a
hallucinated price. Onyx Shield is the neutral, signed risk layer you put in
FRONT of your payment rail: check before you pay, record what happened after.

Three lines:

    from onyx_shield import shield
    if shield.check(merchant_url).blocked:
        return                      # don't pay a scam

Full loop (check -> act -> report so the network's track record compounds):

    v = shield.check(merchant_url)
    if v.blocked: return
    pay(merchant_url)
    shield.report(v.verdict_id, "proceeded_ok", who="my-agent")

No API key needed for the free first calls. Every verdict is Ed25519-signed by
0n1x and independently verifiable at /verify — trust the math, not us.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass

BASE = "https://onyx-actions.onrender.com"
_TIMEOUT = 20


@dataclass
class Verdict:
    verdict: str          # PROCEED | REVIEW | HOLD
    score: float
    verdict_id: str
    raw: dict

    @property
    def blocked(self) -> bool:
        """True if you should NOT pay (HOLD, or REVIEW if you're strict)."""
        return self.verdict.upper() in ("HOLD",)

    @property
    def caution(self) -> bool:
        return self.verdict.upper() in ("HOLD", "REVIEW")


def _get(path: str) -> dict:
    req = urllib.request.Request(BASE + path, headers={"user-agent": "onyx-shield/1.0"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
        return json.loads(r.read() or "{}")


def check(url: str) -> Verdict:
    """Verify a merchant/counterparty BEFORE you pay. Returns a signed Verdict."""
    d = _get("/api/check?url=" + urllib.parse.quote(url, safe=""))
    return Verdict(
        verdict=str(d.get("verdict", "REVIEW")),
        score=float(d.get("score", 0) or 0),
        verdict_id=str(d.get("verdict_id") or d.get("domain") or url),
        raw=d,
    )


def report(verdict_id: str, outcome: str, who: str = "agent",
           evidence: str = "") -> dict:
    """Record what HAPPENED after the verdict, into the signed outcome ledger.
    outcome in: avoided_scam, confirmed_legit, proceeded_ok, false_positive,
                false_negative, loss_incurred, unknown."""
    q = urllib.parse.urlencode({"verdict_id": verdict_id, "outcome": outcome,
                                "from": who, "evidence": evidence})
    return _get("/report?" + q)


# module-level convenience so `from onyx_shield import shield; shield.check(...)`
class _Shield:
    check = staticmethod(check)
    report = staticmethod(report)
    Verdict = Verdict
    BASE = BASE


shield = _Shield()
