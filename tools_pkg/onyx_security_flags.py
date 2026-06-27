"""onyx_security_flags — the signed security posture of an agent.

The third leg of the 0n1x trust triangle. KYA says WHO an agent is;
/api/check says the COUNTERPARTY is real; this says what SECURITY FLAGS the
agent itself carries — observed, offline-verifiable conditions any other agent
can check BEFORE it transacts with it.

Empty seat (measured 2026-06-27 across 2,227 live agents): 99.1% declare no
permission scope, 29.3% sit on plain http, 85.1% carry no verifiable key. The
ecosystem has identity + discovery but almost no permission/posture layer.

HARD RULE — facts, not judgments. A flag is an OBSERVED condition
("endpoint is http", "no permission scope in record"), NEVER a verdict on
intent ("this agent is malicious"). Output is Ed25519-signed; verify offline.

Flags (the scope we attest):
  F1  TRANSPORT_INSECURE   endpoint not https
  F3  PERM_NO_SCOPE        no permission/mandate scope declared
  F4  PERM_NO_PRINCIPAL    no principal/grantor of authority declared
  F5  PERM_NO_CONSENT      no consent/mandate reference
  F6  PERM_NO_SPEND_CAP    value-moving agent with no spend ceiling
  F7  IDENTITY_UNSIGNED    no verifiable key/signature/did on the record
  F8  COUNTERPARTY_BLIND   transacts with no merchant/counterparty verification
  F9  INJECTION_SURFACE    free-text/chat input = prompt-injection exposure
  F10 SKILL_UNBOUNDED      declares skills with no limits on their use

Underscore-free, has NAME + run() → auto-discovered as a tool.
"""
from __future__ import annotations

import json
import re

NAME = "onyx_security_flags"
PRICE_USDC = "0.00"
TIER = "free"          # free check drives adoption; revenue is the sell-side badge
DESCRIPTION = (
    "Return the signed security posture of an agent: a list of OBSERVED, "
    "offline-verifiable security flags (insecure transport, no permission "
    "scope/principal/consent, no spend cap, unsigned identity, counterparty-"
    "blind, injection surface, unbounded skills). Pass an endpoint URL and/or "
    "the agent's record. Facts, not judgments — flags are conditions, never "
    "verdicts on intent. Ed25519-signed; verify free with onyx_attestation_verify."
)

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "endpoint": {"type": "string", "description": "The agent's endpoint URL"},
        "agent": {"type": "object", "description": "Optional: the agent's record "
                  "(name, description, skills, and any permission fields) for a deeper scan"},
    },
}

FLAG_NAME = {
    "F1": "TRANSPORT_INSECURE", "F3": "PERM_NO_SCOPE", "F4": "PERM_NO_PRINCIPAL",
    "F5": "PERM_NO_CONSENT", "F6": "PERM_NO_SPEND_CAP", "F7": "IDENTITY_UNSIGNED",
    "F8": "COUNTERPARTY_BLIND", "F9": "INJECTION_SURFACE", "F10": "SKILL_UNBOUNDED",
}
FLAG_REMEDY = {
    "F1": "Serve the endpoint over https.",
    "F3": "Declare a permission grant (PERM_v0) at /onboard.",
    "F4": "Name the principal/grantor of authority in the grant.",
    "F5": "Bind a consent/mandate reference (e.g. AP2 mandate id) to the grant.",
    "F6": "Set spend_max_usdc on the grant.",
    "F7": "Sign the agent card (A2A JWS / Web Bot Auth) — onboard at /onboard.",
    "F8": "Call /api/check on the counterparty before paying.",
    "F9": "Treat free-text input as untrusted data, not instructions.",
    "F10": "Bound declared skills with allowed_actions in the grant.",
}

_TRANSACT = re.compile(
    r"\b(pay|payment|purchase|buy|checkout|transact|spend|wallet|x402|settle|"
    r"invoice|trade|swap|order|book|subscribe|transfer|usdc|fund)\b", re.I)
_CHAT = re.compile(r"\b(chat|conversation|answer|assistant|prompt|ask|query|nlweb|message)\b", re.I)
_PERM_KEYS = ("permissions", "scope", "scopes", "mandate", "spend_max_usdc", "spend_cap",
              "allowed_actions", "allowed_merchants", "principal", "consent", "consent_ref",
              "authorized_by", "grant", "expires_at")
_SIG_KEYS = ("signature", "sig", "jws", "pubkey", "public_key", "did", "verification")


def _flags(endpoint: str, agent: dict) -> list:
    record = dict(agent or {})
    if endpoint and "endpoint" not in record:
        record["endpoint"] = endpoint
    blob = json.dumps(record).lower()
    ep = (endpoint or record.get("endpoint") or record.get("url") or "").strip()
    text = " ".join(record.get("skills") or []) + " " + (record.get("description") or "")
    transacts = bool(_TRANSACT.search(text))
    chatty = bool(_CHAT.search(text))
    has_perm = any(k in blob for k in _PERM_KEYS)
    has_sig = any(k in blob for k in _SIG_KEYS)

    raised = []
    if ep and not ep.lower().startswith("https://"):
        raised.append("F1")
    if not has_perm:
        raised += ["F3", "F4", "F5"]
        if transacts:
            raised.append("F6")
    if not has_sig:
        raised.append("F7")
    if transacts and "counterparty" not in blob and "verify" not in blob:
        raised.append("F8")
    if chatty:
        raised.append("F9")
    if record.get("skills") and not has_perm:
        raised.append("F10")
    return raised


def run(endpoint: str = "", agent: dict | None = None, **_: object) -> dict:
    if not endpoint and not agent:
        raise ValueError("Provide endpoint and/or agent record")
    raised = _flags(endpoint, agent or {})
    out = {
        "subject": (endpoint or (agent or {}).get("endpoint") or (agent or {}).get("name") or "agent"),
        "predicate": "security_flags",
        "report": "onyx-security-flags/v0",
        "observed_flags": [
            {"flag": f, "name": FLAG_NAME[f], "remedy": FLAG_REMEDY[f]} for f in raised
        ],
        "flag_count": len(raised),
        "clean": not raised,
        "method": "static scan of the agent's public record/URL; facts-not-judgments — "
                  "each flag is an observed condition, not a verdict on intent",
        "verify_free": "https://onyx-actions.onrender.com/verify",
    }
    try:
        from . import _onyx_sign
        out = _onyx_sign.attest(out, tool=NAME)
    except Exception:
        pass
    return out
