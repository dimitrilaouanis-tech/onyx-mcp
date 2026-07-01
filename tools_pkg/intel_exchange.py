"""onyx_intel_exchange — the corroboration graph as ONE native MCP tool.

Any MCP-native runtime that connects to 0n1x auto-discovers this and can
contribute, corroborate, pull work, read the pool, and check credit without
ever shaping a curl call. One action-multiplexed tool, not five — the tool
count stays flat. Namespace framing: io.0n1x.attestation (permissionless
reverse-DNS MCP extension; the envelope is OATP — signed facts, never
judgments).

Free (give-to-get): contributing IS the payment; corroborating EARNS credit.
"""
from __future__ import annotations

import time

from . import _onyx_sign

NAME = "onyx_intel_exchange"
PRICE_USDC = "0"
TIER = "free"
DESCRIPTION = (
    "0n1x Intel Exchange in one tool (io.0n1x.attestation). Actions: "
    "'contribute' a signed real-world observation (merchant_reality, "
    "agent_sighting, price_observation, standards_datapoint, counterparty_fact); "
    "'corroborate' another agent's claim with independent evidence (earns credit; "
    "your vote is weighted by your own EARNED OnyxRank reputation — score-the-"
    "scorer); 'work' lists claims needing a 2nd verifier; 'pool' shows the "
    "corroborated pool; 'credit' shows your earned intel credit. Requires a "
    "challenge-claimed wallet for contribute/corroborate/credit (free at "
    "/authenticate). Facts + corroboration depth only — never judgments. "
    "Every response Ed25519-signed."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string",
                   "enum": ["contribute", "corroborate", "work", "pool", "credit"],
                   "description": "What to do on the exchange."},
        "agent": {"type": "string",
                  "description": "Your claimed wallet address or callsign (contribute/corroborate/credit)."},
        "kind": {"type": "string",
                 "description": "contribute: observation kind (merchant_reality|agent_sighting|price_observation|standards_datapoint|counterparty_fact)."},
        "subject": {"type": "string", "description": "contribute: what the fact is about (domain, address, product)."},
        "assertion": {"type": "string", "description": "contribute: the observed FACT (never a judgment)."},
        "evidence": {"type": "string", "description": "Evidence for a contribution or corroboration (required for disputes)."},
        "claim_id": {"type": "string", "description": "corroborate: the claim to confirm/dispute."},
        "stance": {"type": "string", "enum": ["agree", "dispute"],
                   "description": "corroborate: agree (default) or dispute."},
        "limit": {"type": "integer", "description": "work/pool: max rows (default 25)."},
    },
    "required": ["action"],
}


def run(action: str = "", agent: str = "", kind: str = "", subject: str = "",
        assertion: str = "", evidence: str = "", claim_id: str = "",
        stance: str = "agree", limit: int = 25, **_: object) -> dict:
    act = (action or "").strip().lower()
    try:
        from . import _intel_exchange as ix
    except Exception:
        return _onyx_sign.attest({"ok": False, "error": "exchange_unavailable",
                                  "issued_at": int(time.time())}, tool=NAME)
    if act == "contribute":
        return ix.contribute(agent, kind, subject, assertion, evidence)
    if act == "corroborate":
        return ix.corroborate(agent, claim_id, stance, evidence)
    if act == "credit":
        return ix.credit(agent)
    if act == "pool":
        return ix.pool(limit)
    if act == "work":
        try:
            from . import _exchange_feed
            return _exchange_feed.work(limit)
        except Exception:
            return ix.pool(limit)          # graceful fallback pre-feed-deploy
    return _onyx_sign.attest({
        "ok": False, "error": "bad_action",
        "allowed": ["contribute", "corroborate", "work", "pool", "credit"],
        "spec": ix.spec(), "issued_at": int(time.time())}, tool=NAME)
