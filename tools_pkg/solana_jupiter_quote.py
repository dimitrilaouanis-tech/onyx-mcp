"""Jupiter best-route swap quote for any SPL token pair.

Every Solana trading agent needs a live quote before signing a swap.
Jupiter's lite-api is free + no auth — the x402 wrapper IS the value:
agents pay USDC per quote instead of registering API keys.

Returns the best route Jupiter can compose for inputMint -> outputMint
at the requested amount, including price impact, slippage, route hops,
and the ready-to-sign serialized tx (when requested).
"""
from __future__ import annotations

import time
import httpx

NAME = "onyx_solana_jupiter_quote"
PRICE_USDC = "0.001"
TIER = "metered"
DESCRIPTION = (
    "Best-route swap quote on Solana via Jupiter aggregator. Pass "
    "inputMint + outputMint + amount (in input mint's smallest units) "
    "and get the best route across all Solana DEXes (Orca, Raydium, "
    "Meteora, Phoenix, Lifinity, etc.) with price impact, expected "
    "output, intermediate hops, and slippage. Use BEFORE every Solana "
    "swap to lock execution price. Cheaper than every alternative — "
    "Jupiter's API is free but requires no API key tracking; we charge "
    "$0.001 USDC per quote with no signup."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "input_mint": {"type": "string", "description": "Input token SPL mint (base58)"},
        "output_mint": {"type": "string", "description": "Output token SPL mint (base58)"},
        "amount": {"type": "string",
                   "description": "Amount in smallest units of input_mint (string to avoid float precision)"},
        "slippage_bps": {"type": "integer",
                         "description": "Max slippage in basis points (50 = 0.5%, default 50)",
                         "default": 50},
    },
    "required": ["input_mint", "output_mint", "amount"],
}

_JUP = "https://lite-api.jup.ag/swap/v1/quote"


def run(input_mint: str, output_mint: str, amount: str,
        slippage_bps: int = 50, **_: object) -> dict:
    if not input_mint or not output_mint:
        raise ValueError("input_mint and output_mint are required")
    try:
        amt_int = int(amount)
    except (TypeError, ValueError):
        raise ValueError("amount must be a string-encoded integer")
    if amt_int <= 0:
        raise ValueError("amount must be > 0")
    if not (0 < slippage_bps <= 5000):
        raise ValueError("slippage_bps must be in (0, 5000]")

    started = time.time()
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(amt_int),
        "slippageBps": str(slippage_bps),
        "swapMode": "ExactIn",
        "onlyDirectRoutes": "false",
        "asLegacyTransaction": "false",
    }
    try:
        r = httpx.get(_JUP, params=params, timeout=10.0)
    except Exception as e:
        return {"error": f"upstream: {type(e).__name__}",
                "elapsed_ms": int((time.time() - started) * 1000)}
    if r.status_code != 200:
        return {"error": f"jupiter HTTP {r.status_code}",
                "detail": r.text[:200],
                "elapsed_ms": int((time.time() - started) * 1000)}

    q = r.json()
    in_amt = int(q.get("inAmount", "0") or 0)
    out_amt = int(q.get("outAmount", "0") or 0)
    other_amt = int(q.get("otherAmountThreshold", "0") or 0)
    plan = q.get("routePlan") or []
    hops = []
    for step in plan:
        info = (step.get("swapInfo") or {})
        hops.append({
            "amm": info.get("label") or info.get("ammKey", "")[:8],
            "input_mint": info.get("inputMint"),
            "output_mint": info.get("outputMint"),
            "in_amount": info.get("inAmount"),
            "out_amount": info.get("outAmount"),
            "fee_bps": info.get("feeBps"),
        })
    impact_pct = float(q.get("priceImpactPct") or 0) * 100

    return {
        "input_mint": input_mint,
        "output_mint": output_mint,
        "in_amount": str(in_amt),
        "out_amount": str(out_amt),
        "min_out_amount": str(other_amt),
        "price_impact_pct": impact_pct,
        "slippage_bps": slippage_bps,
        "route_hops": hops,
        "hop_count": len(hops),
        "amms_used": list({h["amm"] for h in hops if h.get("amm")}),
        "swap_mode": q.get("swapMode"),
        "context_slot": q.get("contextSlot"),
        "source": "onyx.jupiter_v1",
        "elapsed_ms": int((time.time() - started) * 1000),
    }
