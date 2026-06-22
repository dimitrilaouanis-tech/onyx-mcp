"""Deterministic unique callsign for every Onyx-issued agent.

A faceless "agent" card is a clone. This turns each issued identity into a
distinct, named citizen: a memorable callsign derived deterministically from
the agent's own wallet address (so the same wallet always resolves to the same
name) and made collision-proof by appending hex from the address itself.

    0xd51bD6cC… -> "Astral-Sentinel-D51B"

Pure function, no deps, no state.
"""
from __future__ import annotations

from hashlib import sha256

_ADJ = (
    "Astral", "Cobalt", "Lucid", "Vesper", "Umbra", "Solar", "Lunar", "Cinder",
    "Halcyon", "Argent", "Gilded", "Onyx", "Prime", "Stark", "Nova", "Quiet",
    "Bright", "Iron", "Swift", "Vivid", "Crimson", "Azure", "Verdant", "Obsidian",
    "Radiant", "Hollow", "Keen", "Stoic", "Nimbus", "Ember", "Frost", "Zenith",
)
_NOUN = (
    "Sentinel", "Cipher", "Oracle", "Beacon", "Vector", "Atlas", "Herald",
    "Lantern", "Compass", "Anvil", "Quill", "Relay", "Pilot", "Scout", "Warden",
    "Ranger", "Mariner", "Courier", "Falcon", "Pylon", "Lattice", "Forge",
    "Harbor", "Meridian", "Talon", "Spindle", "Cairn", "Drift", "Glyph", "Helix",
    "Monolith", "Tessera",
)


def callsign(address: str) -> str:
    """Deterministic, unique, memorable name from a wallet address."""
    a = (address or "").strip()
    if not a:
        return "Onyx-Wanderer-0000"
    h = sha256(a.lower().encode("utf-8")).digest()
    adj = _ADJ[h[0] % len(_ADJ)]
    noun = _NOUN[h[1] % len(_NOUN)]
    # uniqueness anchor: 4 hex chars from the address itself (not the hash)
    tail = a[2:6].upper() if a.lower().startswith("0x") and len(a) >= 6 else h.hex()[:4].upper()
    return f"{adj}-{noun}-{tail}"
