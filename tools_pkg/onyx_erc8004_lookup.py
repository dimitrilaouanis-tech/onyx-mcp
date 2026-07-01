"""ERC-8004 on-chain agent-identity lookup — signed read of the live registries.

ERC-8004 ("Trustless Agents") deploys three singleton registries at fixed
addresses across 30+ EVM chains: an Identity Registry (ERC-721 model — one NFT
per registered agent), a Reputation Registry, and a Validation Registry. As of
2026 the Identity + Reputation singletons are LIVE on Base mainnet; the
Validation Registry write-seat (who posts outcome/fact attestations) is still
an open standards socket — which is exactly the 0n1x wedge.

This tool does a READ-ONLY `eth_call` against the registries and returns a
SIGNED snapshot:

  - the registry contract metadata (name/symbol) + that it is real code on-chain
  - totalSupply  = how many agents are registered (ERC-721Enumerable, if exposed)
  - balanceOf(address) = whether a queried agent address holds an identity NFT

No funds, no signing of transactions, no gating. Just a verifiable on-chain fact
an agent can pull before trusting a counterparty, Ed25519-signed by 0n1x so the
reading is provably unaltered.

Bright line: reads public chain state. Signs facts, not judgments.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from . import _onyx_sign

NAME = "onyx_erc8004_lookup"
PRICE_USDC = "0.05"
TIER = "metered"
DESCRIPTION = (
    "Signed on-chain read of the ERC-8004 'Trustless Agents' registries (Identity "
    "+ Reputation singletons, live on Base mainnet). Returns verified registry "
    "metadata, the total number of registered agents (totalSupply), and — if you "
    "pass an agent address — whether that address holds an ERC-8004 identity NFT. "
    "Read-only eth_call, no funds; the whole reading is Ed25519-signed by 0n1x so "
    "an agent can prove the registry fact before trusting a counterparty."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "address": {
            "type": "string",
            "description": "Optional agent EVM address (0x...) to check for an ERC-8004 identity (balanceOf > 0).",
        },
        "registry": {
            "type": "string",
            "enum": ["identity", "reputation"],
            "description": "Which singleton to read (default 'identity').",
        },
        "chain": {
            "type": "string",
            "enum": ["base"],
            "description": "Chain to read (default 'base' = Base mainnet, eip155:8453).",
        },
    },
    "required": [],
}

# ERC-8004 singleton addresses (fixed across chains; verified live on Base mainnet).
_REGISTRIES = {
    "identity": "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432",
    "reputation": "0x8004BAa17C55a88189AE136b182e5fdA19dE9b63",
}
_RPCS = {
    "base": ("https://base-rpc.publicnode.com", "https://base.publicnode.com"),
}
_TIMEOUT = 20.0

# Standard ERC-721 selectors.
_SEL_NAME = "0x06fdde03"          # name()
_SEL_SYMBOL = "0x95d89b41"        # symbol()
_SEL_TOTALSUPPLY = "0x18160ddd"   # totalSupply()
_SEL_BALANCEOF = "0x70a08231"     # balanceOf(address)


_UA = "Mozilla/5.0 (compatible; onyx-observer/1.0; +https://0n1x)"


def _rpc(url: str, method: str, params: list) -> dict:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "User-Agent": _UA},
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _eth_call(url: str, to: str, data: str) -> str | None:
    try:
        out = _rpc(url, "eth_call", [{"to": to, "data": data}, "latest"])
        return out.get("result")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError):
        return None


def _decode_uint(hexstr: str | None) -> int | None:
    if not hexstr or hexstr == "0x":
        return None
    try:
        return int(hexstr, 16)
    except ValueError:
        return None


def _decode_string(hexstr: str | None) -> str | None:
    """Decode an ABI-encoded dynamic string (offset, length, data)."""
    if not hexstr or len(hexstr) < 130:
        return None
    raw = hexstr[2:]
    try:
        length = int(raw[64:128], 16)
        data = raw[128:128 + length * 2]
        return bytes.fromhex(data).decode("utf-8", "replace") or None
    except (ValueError, IndexError):
        return None


def _code_exists(url: str, addr: str) -> bool:
    try:
        out = _rpc(url, "eth_getCode", [addr, "latest"])
        code = out.get("result") or "0x"
        return len(code) > 2
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError):
        return False


def run(address: str = "", registry: str = "identity", chain: str = "base",
        **_: object) -> dict:
    registry = (registry or "identity").strip().lower()
    if registry not in _REGISTRIES:
        raise ValueError("registry must be 'identity' or 'reputation'")
    chain = (chain or "base").strip().lower()
    if chain not in _RPCS:
        raise ValueError("chain must be 'base'")

    to = _REGISTRIES[registry]
    addr = (address or "").strip()

    # Pick the first RPC that answers eth_getCode.
    url = None
    code_present = False
    for candidate in _RPCS[chain]:
        if _code_exists(candidate, to):
            url, code_present = candidate, True
            break
        url = url or candidate
    if not url:
        url = _RPCS[chain][0]

    name = _decode_string(_eth_call(url, to, _SEL_NAME))
    symbol = _decode_string(_eth_call(url, to, _SEL_SYMBOL))
    total_supply = _decode_uint(_eth_call(url, to, _SEL_TOTALSUPPLY))

    holds_identity = None
    balance = None
    if addr and len(addr) == 42 and addr.startswith("0x"):
        padded = "0" * 24 + addr[2:].lower()
        balance = _decode_uint(_eth_call(url, to, _SEL_BALANCEOF + padded))
        if balance is not None:
            holds_identity = balance > 0

    result = {
        "ok": code_present,
        "standard": "ERC-8004",
        "registry": registry,
        "contract": to,
        "chain": chain,
        "chain_id": "eip155:8453",
        "rpc": url,
        "code_present": code_present,
        "registry_name": name,
        "registry_symbol": symbol,
        "total_agents_registered": total_supply,
        "queried_address": addr or None,
        "holds_identity": holds_identity,
        "identity_balance": balance,
        "note": (
            "Identity + Reputation singletons are live; the ERC-8004 Validation "
            "Registry (who posts outcome/fact attestations) is the open seat 0n1x "
            "targets with signed-fact attestations."
        ),
        "summary": (
            f"ERC-8004 {registry} registry {to[:10]}.. on {chain}: "
            + ("contract present" if code_present else "NO code (unexpected)")
            + (f", name={name}" if name else "")
            + (f", {total_supply} agents registered" if total_supply is not None else "")
            + (
                f", queried {addr[:10]}.. {'HOLDS' if holds_identity else 'does NOT hold'} an identity"
                if holds_identity is not None else ""
            )
        ),
    }
    return _onyx_sign.attest(result, tool=NAME)


run.__when_to_use__ = (
    "Before trusting an agent counterparty, check whether it is registered in the "
    "ERC-8004 Identity Registry on-chain — and read the live registry size — as a "
    "signed fact, not a self-claim. Useful for agent due-diligence, registry "
    "census, and proving an agent's on-chain identity exists."
)
run.__vs_alternatives__ = (
    "A raw RPC call gives you an undecoded hex blob and no provenance. This returns "
    "decoded registry metadata + agent count + a per-address identity check, all "
    "Ed25519-signed by 0n1x so the on-chain reading is tamper-evident and "
    "verifiable with onyx_attestation_verify."
)
run.__example_request__ = {"address": "0xbD2900000000000000000000000000000000004Da7", "registry": "identity"}
run.__example_response__ = {
    "ok": True, "standard": "ERC-8004", "registry": "identity",
    "contract": "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432",
    "code_present": True, "total_agents_registered": 1234, "holds_identity": False,
}
