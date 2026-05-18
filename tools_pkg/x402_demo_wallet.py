"""Testnet faucet + dev-sandbox helper for x402.

Helps devs building x402 clients spin up sandbox infrastructure: generates
ephemeral test wallet (or checks an existing one), reports Base Sepolia
ETH + USDC balances, points at the Circle USDC Sepolia faucet, and emits
a copy-paste config block ready for any x402 client SDK.

Stdlib-only. No key storage. Read-only RPC + deterministic ephemeral key
generation (for sandbox use only; warned never to use on mainnet).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import urllib.error
import urllib.request

NAME = "onyx_x402_demo_wallet"
PRICE_USDC = "0"
TIER = "free"
DESCRIPTION = (
    "Dev-sandbox wallet helper for x402 testing. Generates a deterministic "
    "ephemeral Sepolia wallet (or accepts your address), reports ETH + USDC "
    "Sepolia balances, points to the Circle USDC Sepolia faucet, and emits "
    "a copy-paste env config for x402 client SDKs. SANDBOX ONLY — generated "
    "keys are deterministic and MUST NOT receive real value."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "existing_address": {
            "type": "string",
            "description": "Existing 0x-prefixed address to check. If omitted, generates an ephemeral sandbox address from `seed`.",
        },
        "seed": {
            "type": "string",
            "description": "String seed for deterministic sandbox address generation. Same seed always yields same address. NOT cryptographically secure; sandbox only.",
        },
    },
}

_ADDR_RX = re.compile(r"^0x[a-fA-F0-9]{40}$")

_BASE_SEPOLIA_RPC = "https://base-sepolia.gateway.tenderly.co"
_USDC_SEPOLIA = "0x036cbd53842c5426634e7929541ec2318f3dcf7e"
_USDC_MAINNET = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"


def _rpc(url: str, method: str, params: list, timeout: float = 10.0) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; OnyxDemoWallet/1.0)",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _balance_eth(rpc_url: str, addr: str) -> int:
    r = _rpc(rpc_url, "eth_getBalance", [addr, "latest"])
    res = r.get("result", "0x0")
    return int(res, 16) if isinstance(res, str) and res.startswith("0x") else 0


def _balance_erc20(rpc_url: str, contract: str, owner: str) -> int:
    owner_padded = owner.lower().replace("0x", "").rjust(64, "0")
    data = "0x70a08231" + owner_padded
    r = _rpc(rpc_url, "eth_call", [{"to": contract, "data": data}, "latest"])
    res = r.get("result", "0x0")
    return int(res, 16) if isinstance(res, str) and res.startswith("0x") else 0


def _deterministic_addr(seed: str) -> str:
    """Generate a deterministic 0x address from a seed. Sandbox only —
    derives address from a hash, not a real keypair. The returned 'wallet'
    can RECEIVE testnet USDC (for inspection demos) but CANNOT SIGN — no
    private key exists. Used purely as a sandbox identity placeholder."""
    h = hashlib.sha256(seed.encode("utf-8")).digest()
    return "0x" + h[-20:].hex()


def run(
    existing_address: str | None = None,
    seed: str | None = None,
    **_: object,
) -> dict:
    if existing_address:
        if not _ADDR_RX.match(existing_address.strip()):
            raise ValueError("existing_address must be 0x-prefixed 20-byte hex")
        addr = existing_address.strip()
        addr_source = "user-provided"
        sandbox_warning = None
    else:
        seed = seed or "onyx-default-sandbox"
        addr = _deterministic_addr(seed)
        addr_source = "deterministic-from-seed"
        sandbox_warning = (
            "This address was derived from a seed hash — NO private key exists. "
            "It can RECEIVE testnet tokens (useful for inspecting payments TO it) "
            "but cannot sign transactions. For a real signing wallet, generate one "
            "with eth_account or viem in your client."
        )

    sepolia_state = {"ok": False}
    try:
        eth_wei = _balance_eth(_BASE_SEPOLIA_RPC, addr)
        usdc_atomic = _balance_erc20(_BASE_SEPOLIA_RPC, _USDC_SEPOLIA, addr)
        sepolia_state = {
            "ok": True,
            "rpc": _BASE_SEPOLIA_RPC,
            "eth_wei": eth_wei,
            "eth_balance": eth_wei / 1e18,
            "usdc_atomic": usdc_atomic,
            "usdc_balance": usdc_atomic / 1_000_000,
        }
    except Exception as e:
        sepolia_state = {"ok": False, "error": str(e)[:160]}

    faucet_links = {
        "circle_usdc_sepolia": "https://faucet.circle.com (Base Sepolia, 10 USDC free per request)",
        "base_eth_sepolia":    "https://www.coinbase.com/faucets/base-ethereum-sepolia-faucet (0.1 ETH free)",
        "alternate_eth_sepolia": "https://www.alchemy.com/faucets/base-sepolia",
    }

    client_env_block = (
        f"# x402 sandbox env — Base Sepolia only\n"
        f"X402_NETWORK=base-sepolia\n"
        f"X402_NETWORK_CAIP2=eip155:84532\n"
        f"X402_RPC_URL={_BASE_SEPOLIA_RPC}\n"
        f"X402_USDC_ADDRESS={_USDC_SEPOLIA}\n"
        f"X402_USDC_DECIMALS=6\n"
        f"X402_USDC_DOMAIN_VERSION=2\n"
        f"X402_FACILITATOR_URL=https://x402.org/facilitator\n"
        f"X402_TEST_ADDRESS={addr}\n"
    )

    next_steps = [
        f"1. Fund {addr} with USDC from {faucet_links['circle_usdc_sepolia']}.",
        f"2. Fund the same address with Sepolia ETH from {faucet_links['base_eth_sepolia']} (needed for gas if you sign locally).",
        "3. Use the client_env_block below as your sandbox config.",
        "4. Point your x402 client at any Onyx tool's GET introspection URL (free preview) before retrying with payment.",
        "5. Use onyx_x402_simulate to inspect the payment payload an x402 client would build.",
        "6. Use onyx_verify_explain if your /verify call returns a bare 402.",
    ]
    if sandbox_warning:
        next_steps.insert(0, f"WARNING: {sandbox_warning}")

    return {
        "ok": True,
        "address": addr,
        "address_source": addr_source,
        "sandbox_warning": sandbox_warning,
        "sepolia": sepolia_state,
        "mainnet_usdc_address": _USDC_MAINNET,
        "sepolia_usdc_address": _USDC_SEPOLIA,
        "faucets": faucet_links,
        "client_env_block": client_env_block,
        "next_steps": next_steps,
    }


run.__when_to_use__ = (
    "A developer building or testing an x402 client needs sandbox infrastructure: "
    "a testnet address with funded balances, faucet links, and a ready-to-paste "
    "config block — without spinning up their own wallet management code."
)
run.__vs_alternatives__ = (
    "Existing options: build it yourself (eth_account/viem + faucet hunting + "
    "config writing = 30 min). This tool returns it all in one call. Sandbox-only "
    "warning is explicit; not a key-management product."
)
run.__example_request__ = {"seed": "my-test-agent-01"}
run.__example_response__ = {
    "ok": True,
    "address": "0xABCDEF...",
    "address_source": "deterministic-from-seed",
    "sepolia": {"ok": True, "eth_balance": 0.0, "usdc_balance": 0.0},
    "client_env_block": "X402_NETWORK=base-sepolia\n...",
    "next_steps": ["1. Fund address...", "..."],
}
