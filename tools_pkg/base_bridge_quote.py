"""Base bridge quote — cross-chain bridge route via LI.FI.

Returns: best route + USD value, fees, gas, ETA, bridge tool used.
LI.FI aggregates ~30 bridges (Across, Hop, Stargate, cBridge, Connext,
Hyphen, Mayan, etc.) — no auth, no rate limit on quote endpoint.

Composes with onyx_base_swap_quote: agent first swaps token A → bridgeable
token B on Base, then bridges B → target chain in one paid call.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

NAME = "onyx_base_bridge_quote"
PRICE_USDC = "0.003"
TIER = "metered"
DESCRIPTION = (
    "Cross-chain bridge quote starting from Base. Best-route across ~30 "
    "bridges (Across, Hop, Stargate, cBridge, Connext, Hyphen, Mayan, ...) "
    "via LI.FI aggregator. Returns toAmount, fee breakdown, gas cost, "
    "estimated bridge tool, approval address, ETA. Use when an agent on "
    "Base needs USDC/ETH/etc. on another chain."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "to_chain_id": {
            "type": "integer",
            "description": "Destination chain ID. 1=Ethereum, 10=Optimism, 42161=Arbitrum, 137=Polygon, 56=BSC, 43114=Avalanche, 250=Fantom, 8453=Base (same chain - use swap_quote instead).",
        },
        "from_token": {
            "type": "string",
            "description": "Source token address on Base (0x...). Use 0x0000000000000000000000000000000000000000 for native ETH.",
        },
        "to_token": {
            "type": "string",
            "description": "Destination token address on destination chain (0x...).",
        },
        "from_amount": {
            "type": "string",
            "description": "Atomic amount on source side (decimal string). E.g. 100 USDC = '100000000'.",
        },
        "from_address": {
            "type": "string",
            "description": "Optional: sender address for routes that need it. Default = 0x...0001 (LI.FI accepts any for quote).",
        },
    },
    "required": ["to_chain_id", "from_token", "to_token", "from_amount"],
}

_LIFI = "https://li.quest/v1/quote"
_UA = "onyx-base-bridge-quote/1.0"


def _hex_addr(s: str) -> bool:
    s = (s or "").strip()
    return s.startswith("0x") and len(s) == 42


def run(
    to_chain_id: int,
    from_token: str,
    to_token: str,
    from_amount: str,
    from_address: str | None = None,
    **_: object,
) -> dict:
    try:
        to_chain_id = int(to_chain_id)
    except (TypeError, ValueError):
        return {"ok": False, "error": "to_chain_id must be int"}
    if to_chain_id == 8453:
        return {"ok": False, "error": "to_chain is also Base — use onyx_base_swap_quote for same-chain swaps"}
    if not _hex_addr(from_token):
        return {"ok": False, "error": "from_token must be 0x... 20-byte hex"}
    if not _hex_addr(to_token):
        return {"ok": False, "error": "to_token must be 0x... 20-byte hex"}
    try:
        if int(from_amount) <= 0:
            return {"ok": False, "error": "from_amount must be positive"}
    except (TypeError, ValueError):
        return {"ok": False, "error": "from_amount must be a decimal string"}

    params = urllib.parse.urlencode({
        "fromChain": "8453",
        "toChain": str(to_chain_id),
        "fromToken": from_token.lower(),
        "toToken": to_token.lower(),
        "fromAmount": str(from_amount),
        "fromAddress": (from_address or "0x0000000000000000000000000000000000000001").lower(),
    })
    url = f"{_LIFI}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            d = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8"))
            return {"ok": False, "error": f"lifi_http_{e.code}", "detail": body.get("message", "")[:200]}
        except Exception:
            return {"ok": False, "error": f"lifi_http_{e.code}"}
    except urllib.error.URLError as e:
        return {"ok": False, "error": "lifi_unreachable", "detail": str(e)[:200]}

    est = d.get("estimate") or {}
    action = d.get("action") or {}
    fee_costs = est.get("feeCosts") or []
    gas_costs = est.get("gasCosts") or []
    fee_total_usd = sum(float(f.get("amountUSD") or 0) for f in fee_costs)
    gas_total_usd = sum(float(g.get("amountUSD") or 0) for g in gas_costs)

    return {
        "ok": True,
        "from_chain": "Base (8453)",
        "to_chain": to_chain_id,
        "from_token": (action.get("fromToken") or {}).get("symbol"),
        "to_token": (action.get("toToken") or {}).get("symbol"),
        "from_amount": est.get("fromAmount"),
        "to_amount": est.get("toAmount"),
        "to_amount_min": est.get("toAmountMin"),
        "from_amount_usd": est.get("fromAmountUSD"),
        "to_amount_usd": est.get("toAmountUSD"),
        "bridge_tool": d.get("tool"),
        "approval_address": est.get("approvalAddress"),
        "execution_duration_sec": est.get("executionDuration"),
        "fee_usd_total": round(fee_total_usd, 4),
        "gas_usd_total": round(gas_total_usd, 4),
        "fee_breakdown": [
            {"name": f.get("name"), "amountUSD": f.get("amountUSD"), "included": f.get("included")}
            for f in fee_costs
        ],
    }


run.__when_to_use__ = (
    "An agent on Base needs liquidity on another chain. Get a quote across "
    "all major bridges in one call before signing the bridge transaction."
)
run.__vs_alternatives__ = (
    "Bridge UI shopping (manual). Direct bridge SDK calls (10+ separate "
    "integrations). LI.FI is the standard aggregator — same data as their "
    "frontend, no auth."
)
run.__example_request__ = {
    "to_chain_id": 42161,
    "from_token": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    "to_token": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
    "from_amount": "10000000",
}
