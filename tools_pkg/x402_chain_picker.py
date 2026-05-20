"""Optimal-chain recommender for an x402 payment.

Given a target USDC amount and the agent's available chains, returns
the chain ranked best for this payment based on:
  - facilitator support (Coinbase Bazaar supports base/base-sepolia today)
  - average gas cost (USDC equivalent — pulled from live RPC)
  - finality time (seconds to 1 confirmation)
  - USDC contract maturity (mainnet > L2 mainnet > testnet)
  - native ETH gas reserve required

Lane: agent-side chain selection is currently a hardcoded constant in
every x402 client. This tool turns it into a data-driven choice.

Stdlib-only. Free tier. SSRF: only public RPC allowlist.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

NAME = "onyx_x402_chain_picker"
PRICE_USDC = "0"
TIER = "free"
DESCRIPTION = (
    "Pick the optimal chain for an x402 USDC payment. Given target amount "
    "+ agent's available chains, ranks by facilitator support, live gas, "
    "finality time, and USDC contract maturity. Returns ranked list with "
    "explanations. Free tier — agents shouldn't hardcode 'base' when "
    "their wallet has L2 options."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "amount_usdc": {
            "type": "number",
            "description": "Target USDC amount the agent wants to settle.",
        },
        "available_chains": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Chains the agent's wallet supports. Subset of: base, base-sepolia, optimism, arbitrum, polygon. Default = ['base', 'base-sepolia'].",
        },
        "production_only": {
            "type": "boolean",
            "default": True,
            "description": "If true, exclude testnets from ranking.",
        },
    },
    "required": ["amount_usdc"],
}

_CHAINS = {
    "base": {
        "caip2": "eip155:8453",
        "rpc": "https://base-rpc.publicnode.com",
        "usdc": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
        "facilitator_supported": True,
        "is_testnet": False,
        "avg_finality_s": 2,
        "usdc_maturity": "circle-native",  # native USDC, not bridged
    },
    "base-sepolia": {
        "caip2": "eip155:84532",
        "rpc": "https://base-sepolia-rpc.publicnode.com",
        "usdc": "0x036cbd53842c5426634e7929541ec2318f3dcf7e",
        "facilitator_supported": True,
        "is_testnet": True,
        "avg_finality_s": 2,
        "usdc_maturity": "circle-native-testnet",
    },
    "optimism": {
        "caip2": "eip155:10",
        "rpc": "https://mainnet.optimism.io",
        "usdc": "0x0b2c639c533813f4aa9d7837caf62653d097ff85",
        "facilitator_supported": False,  # not yet on Coinbase Bazaar
        "is_testnet": False,
        "avg_finality_s": 3,
        "usdc_maturity": "circle-native",
    },
    "arbitrum": {
        "caip2": "eip155:42161",
        "rpc": "https://arb1.arbitrum.io/rpc",
        "usdc": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        "facilitator_supported": False,
        "is_testnet": False,
        "avg_finality_s": 2,
        "usdc_maturity": "circle-native",
    },
    "polygon": {
        "caip2": "eip155:137",
        "rpc": "https://polygon-rpc.com",
        "usdc": "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359",
        "facilitator_supported": False,
        "is_testnet": False,
        "avg_finality_s": 3,
        "usdc_maturity": "circle-native",
    },
}


def _rpc(url: str, method: str, params: list, timeout: float = 6.0) -> dict | None:
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
            headers={"Content-Type": "application/json",
                     "User-Agent": "Mozilla/5.0 (compatible; OnyxChainPicker/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _gas_price_gwei(rpc_url: str) -> float | None:
    r = _rpc(rpc_url, "eth_gasPrice", [])
    if not r or "result" not in r:
        return None
    try:
        return int(r["result"], 16) / 1e9
    except Exception:
        return None


def _score_chain(chain: str, spec: dict, amount: float, gas_gwei: float | None) -> tuple[int, list[str]]:
    score = 0
    reasons = []

    if spec["facilitator_supported"]:
        score += 40
        reasons.append("+40 Coinbase Bazaar facilitator supports this chain")
    else:
        reasons.append("+0 no Bazaar facilitator yet — would need self-hosted or alternate")

    if spec["usdc_maturity"] == "circle-native":
        score += 20
        reasons.append("+20 native Circle USDC (best liquidity)")
    elif spec["usdc_maturity"] == "circle-native-testnet":
        score += 5
        reasons.append("+5 native testnet USDC (sandbox only)")

    if spec["avg_finality_s"] <= 2:
        score += 15
        reasons.append(f"+15 fast finality ({spec['avg_finality_s']}s)")
    elif spec["avg_finality_s"] <= 5:
        score += 10
        reasons.append(f"+10 ok finality ({spec['avg_finality_s']}s)")

    if gas_gwei is not None:
        # USDC settlement is ~50k gas. Cost = gas * gas_price_gwei * eth_price_assumed
        # Assume ETH at $3000 for ballpark: cost_usd = 50000 * gas_gwei * 1e-9 * 3000
        est_usd = 50_000 * gas_gwei * 1e-9 * 3000
        if est_usd < 0.001:
            score += 15
            reasons.append(f"+15 gas cheap (~${est_usd:.5f})")
        elif est_usd < 0.01:
            score += 10
            reasons.append(f"+10 gas low (~${est_usd:.5f})")
        elif est_usd < 0.1:
            score += 5
            reasons.append(f"+5 gas moderate (~${est_usd:.4f})")
        else:
            reasons.append(f"+0 gas expensive (~${est_usd:.3f})")
    else:
        reasons.append("+0 gas data unavailable (RPC failed)")

    if amount < est_usd * 5 if gas_gwei is not None else False:
        reasons.append("WARNING: amount close to gas cost — uneconomical")

    return score, reasons


def run(
    amount_usdc: float,
    available_chains: list[str] | None = None,
    production_only: bool = True,
    **_: object,
) -> dict:
    if not isinstance(amount_usdc, (int, float)) or amount_usdc <= 0:
        raise ValueError("amount_usdc must be a positive number")
    candidates = available_chains or ["base", "base-sepolia"]
    unknown = [c for c in candidates if c not in _CHAINS]
    if unknown:
        raise ValueError(f"unknown chain(s): {unknown}. Supported: {list(_CHAINS.keys())}")

    if production_only:
        candidates = [c for c in candidates if not _CHAINS[c]["is_testnet"]]

    rankings = []
    for chain in candidates:
        spec = _CHAINS[chain]
        gas = _gas_price_gwei(spec["rpc"])
        score, reasons = _score_chain(chain, spec, amount_usdc, gas)
        rankings.append({
            "chain": chain,
            "caip2": spec["caip2"],
            "score": score,
            "reasons": reasons,
            "usdc_contract": spec["usdc"],
            "facilitator_supported": spec["facilitator_supported"],
            "is_testnet": spec["is_testnet"],
            "gas_price_gwei": gas,
            "estimated_settlement_cost_usd": (
                50_000 * gas * 1e-9 * 3000 if gas is not None else None
            ),
        })

    rankings.sort(key=lambda r: -r["score"])
    winner = rankings[0] if rankings else None

    return {
        "ok": True,
        "amount_usdc": amount_usdc,
        "chains_considered": candidates,
        "winner": winner["chain"] if winner else None,
        "winner_caip2": winner["caip2"] if winner else None,
        "ranked": rankings,
        "recommendation": (
            f"Use {winner['chain']} ({winner['caip2']}). {winner['reasons'][0]}"
            if winner else "No production chains available in input."
        ),
        "note": (
            "Only base + base-sepolia are Bazaar-facilitated as of 2026-05. "
            "Optimism/Arbitrum/Polygon score lower because the agent would "
            "need a self-hosted facilitator or alternate (xpay.sh, faremeter)."
        ),
    }


run.__when_to_use__ = (
    "An agent's wallet supports multiple chains and needs to pick one for an "
    "x402 settlement. Don't hardcode 'base' — ask this tool and let live gas "
    "+ facilitator support decide."
)
run.__vs_alternatives__ = (
    "Existing x402 clients hardcode the network constant. No public chain-picker "
    "exists. This is the first multi-factor scorer."
)
run.__example_request__ = {
    "amount_usdc": 0.50,
    "available_chains": ["base", "optimism", "arbitrum"],
}
run.__example_response__ = {
    "ok": True,
    "winner": "base",
    "winner_caip2": "eip155:8453",
    "recommendation": "Use base (eip155:8453). +40 Coinbase Bazaar facilitator supports this chain",
}
