"""ENS resolution — name to address (Base ENS via free public resolver)."""
from __future__ import annotations

import time
import httpx

NAME = "onyx_ens_resolve"
PRICE_USDC = "0.0008"
TIER = "metered"
DESCRIPTION = (
    "Resolve an ENS name to its current Ethereum mainnet address (or vice "
    "versa). Returns the canonical address, avatar URL if set, and the "
    "resolver contract that returned it. Use when an agent encounters a "
    "human-readable name like 'vitalik.eth' and needs to send funds or "
    "validate identity. Reads via the public ensideas API (no key, no "
    "rate-limit pain for typical agent traffic). ~200-500ms."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "ENS name (foo.eth) or 0x-address for reverse"},
    },
    "required": ["name"],
}


def run(name: str, **_: object) -> dict:
    n = (name or "").strip()
    if not n:
        raise ValueError("name required")
    started = time.time()
    is_address = n.lower().startswith("0x") and len(n) == 42
    url = f"https://api.ensideas.com/ens/resolve/{n}"
    r = httpx.get(url, timeout=10.0,
                  headers={"User-Agent": "onyx-actions/0.2"})
    r.raise_for_status()
    d = r.json()
    return {
        "input": n,
        "input_kind": "address" if is_address else "name",
        "name": d.get("name"),
        "address": d.get("address"),
        "avatar": d.get("avatar"),
        "display_name": d.get("displayName"),
        "source": "onyx.ensideas",
        "elapsed_ms": int((time.time() - started) * 1000),
    }
