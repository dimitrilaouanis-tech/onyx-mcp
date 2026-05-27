"""KYA verify — check a KYA credential against the Onyx Protocol verifier.

Onyx Protocol primitive #1: Know Your Agent. A KYA credential
cryptographically binds an agent to its principal, scope, and spend caps.
This tool verifies a credential id without making a paid call against
the agent — useful for compliance, gating, and routing decisions.

Best-effort: tries multiple verifier hosts (onyxprotocol.io public,
local :8210). Returns ok/reason/credential summary.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

NAME = "onyx_kya_verify"
PRICE_USDC = "0.001"
TIER = "metered"
DESCRIPTION = (
    "Verify an Onyx Protocol KYA (Know Your Agent) credential. Pass a "
    "credential id (e.g. 'kya_01KSHZ...'); returns ok + scope + spend cap "
    "+ issuer + revocation status. Use to gate paid tool access, audit "
    "agent operations, or compose with x402 settlement for trust-tier "
    "routing. Calls Onyx Protocol verifier."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "credential_id": {
            "type": "string",
            "description": "KYA credential id (kya_*).",
        },
    },
    "required": ["credential_id"],
}

_VERIFIER_HOSTS = [
    "https://verify.onyxprotocol.io",
    "http://127.0.0.1:8210",  # local fallback
]
_UA = "onyx-kya-verify/1.0"


def _try(host: str, cred_id: str, timeout: float = 8.0) -> dict | None:
    url = f"{host}/kya/{cred_id}.json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, Exception):
        return None


def run(credential_id: str, **_: object) -> dict:
    cred = (credential_id or "").strip()
    if not cred or not cred.startswith("kya_"):
        return {"ok": False, "error": "credential_id must start with 'kya_'"}

    result = None
    last_host = None
    for host in _VERIFIER_HOSTS:
        last_host = host
        result = _try(host, cred)
        if result is not None:
            break

    if result is None:
        return {
            "ok": False,
            "credential_id": cred,
            "error": "verifier_unreachable",
            "tried_hosts": _VERIFIER_HOSTS,
            "fallback_note": "Onyx Protocol verifier not yet publicly hosted. Once verify.onyxprotocol.io is live this resolves automatically.",
        }

    return {
        "ok": True,
        "credential_id": cred,
        "verifier_host": last_host,
        "credential": result,
    }


run.__when_to_use__ = (
    "Before issuing a high-cost tool call to an unknown agent. Or when "
    "auditing an action receipt that references a kya credential id."
)
run.__vs_alternatives__ = (
    "Manually GET verify.onyxprotocol.io/kya/<id>.json. This tool wraps "
    "with structured output + automatic fallback to local :8210 verifier."
)
run.__example_request__ = {"credential_id": "kya_01KSHZHQ8JQSFEJFM72EEHW826"}
