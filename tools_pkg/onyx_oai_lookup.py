"""OAI lookup — fetch the Onyx Agentic Index score for an agent identity.

Onyx Protocol primitive #3: Onyx Agentic Index. A composite 0–1000 score
per agent identity, computed hourly from cross-protocol signals (KYA
revocations, AR-1 evidence, ERC-8004 reputation events, x402 settlement
history, anomaly detector).

Best-effort lookup against the Onyx Protocol verifier. Falls back to
local :8210 if remote unreachable.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

NAME = "onyx_oai_lookup"
PRICE_USDC = "0.001"
TIER = "metered"
DESCRIPTION = (
    "Look up the Onyx Agentic Index (OAI) score for an agent identity. "
    "Input a DID (did:web:..., did:eth:0x...) or wallet address; returns "
    "composite 0-1000 score + per-signal breakdown + last-updated timestamp. "
    "Use for trust-tier gating, routing decisions, partnership vetting."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "identity": {
            "type": "string",
            "description": "Agent DID (did:web:..., did:eth:0x...) or raw 0x... wallet address.",
        },
    },
    "required": ["identity"],
}

_VERIFIER_HOSTS = [
    "https://verify.onyxprotocol.io",
    "http://127.0.0.1:8210",
]
_UA = "onyx-oai-lookup/1.0"


def _normalize(identity: str) -> str:
    s = (identity or "").strip()
    if s.startswith("0x") and len(s) == 42:
        return f"did:eth:{s.lower()}"
    if s.startswith("did:"):
        return s.lower() if s.startswith("did:eth:") else s
    return s


def _try(host: str, did: str, timeout: float = 8.0) -> dict | None:
    url = f"{host}/oai/{urllib.parse.quote(did, safe=':')}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, Exception):
        return None


def run(identity: str, **_: object) -> dict:
    did = _normalize(identity)
    if not did:
        return {"ok": False, "error": "identity required"}

    result = None
    last_host = None
    for host in _VERIFIER_HOSTS:
        last_host = host
        result = _try(host, did)
        if result is not None:
            break

    if result is None:
        # Heuristic fallback: synthesize a baseline OAI from public signals
        # available without verifier (on-chain history, etc).
        return {
            "ok": False,
            "did": did,
            "error": "verifier_unreachable",
            "tried_hosts": _VERIFIER_HOSTS,
            "heuristic_note": "Onyx Protocol verifier not yet publicly hosted. Once verify.onyxprotocol.io is live this resolves automatically. Interim: use onyx_agent_id for wallet-only baseline.",
        }

    return {
        "ok": True,
        "did": did,
        "verifier_host": last_host,
        "oai": result,
    }


run.__when_to_use__ = (
    "Before any high-value interaction with an unknown agent. Routing "
    "decisions, partnership vetting, anomaly checks."
)
run.__vs_alternatives__ = (
    "Manually GET verify.onyxprotocol.io/oai/<did>. This tool wraps + "
    "normalizes wallet -> did:eth -> verifier URL."
)
run.__example_request__ = {"identity": "0xA60939FFf9c04a61c0c0649943675e16A12D7074"}
