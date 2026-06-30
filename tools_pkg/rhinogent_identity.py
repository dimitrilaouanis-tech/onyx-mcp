"""Rhinogent — turn a self-custody address into a signed, verifiable agent identity.

Rhinogent ("MetaMask for agents", powered by 0n1x) is the branded identity-wallet
surface over the 0n1x trust layer. The agent generates and holds its OWN key
(self-custody — 0n1x never custodies it); this tool issues the PUBLIC, signed
identity that anyone can verify: a deterministic callsign, a did:pkh, and the
earned 0n1x-Verified credential.

Reuses existing 0n1x primitives — no new key handling, no custody.
"""
from __future__ import annotations

from . import _callsign, _credential, _onyx_sign

NAME = "rhinogent_identity"
PRICE_USDC = "0.00"
TIER = "free"
DESCRIPTION = (
    "Rhinogent identity card: give a self-custody Base (EVM) address, get back a "
    "signed, verifiable identity — deterministic callsign, did:pkh, and the agent's "
    "earned 0n1x-Verified credential. Keys never leave the agent; this issues only "
    "the public signed identity. The front door of the agent identity wallet."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "address": {
            "type": "string",
            "description": "The agent's self-custody Base/EVM address, 0x-prefixed (42 chars).",
        },
    },
    "required": ["address"],
}

_HEX = set("0123456789abcdefABCDEF")


def _valid_evm(addr: str) -> bool:
    a = (addr or "").strip()
    return a.startswith("0x") and len(a) == 42 and all(c in _HEX for c in a[2:])


def run(address: str | None = None, **_: object) -> dict:
    if not isinstance(address, str) or not _valid_evm(address):
        raise ValueError("address must be a 0x-prefixed 42-character EVM address")
    addr = address.strip()
    out = {
        "product": "rhinogent",
        "subject": addr,
        "callsign": _callsign.callsign(addr),
        "did": f"did:pkh:eip155:8453:{addr}",
        "network": "base-mainnet (eip155:8453)",
        "self_custody": True,
        "custody_note": (
            "The agent holds its own key. 0n1x never custodies it — there is "
            "nothing for us to seize, freeze, or fake. This is the public, "
            "signed identity only."
        ),
        "credential": _credential.credential(addr),
        "get_a_wallet": "https://rhinogent.0n1x.xyz/dashboard",
        "verify_with": "rhinogent_verify_counterparty (verify who you're paying)",
    }
    return _onyx_sign.attest(out, tool=NAME)
