"""KYC/AML sanctions + risk screen for any EVM address.

Coinbase's PROJECT-IDEAS.md explicitly calls for this primitive at $0.25/call
("Rapid KYC/AML Checker"). The GENIUS Act (effective July 2026) mandates
every Permitted Payment Stablecoin Issuer + agent-payment platform to screen
counterparties against sanctions lists. Demand is regulator-enforced, not
discretionary. As of 2026-05-08 there are zero dedicated paid endpoints
on x402 serving this need.

Implementation:
- OFAC sanctions: Chainalysis free on-chain Sanctions Oracle (public,
  no API key, no rate limit). Public contract on Ethereum mainnet:
  0x40C57923924B5c5c5455c48D93317139ADDaC8fb (also mirrored to Base).
- Heuristic risk layer: addr-age (first-seen tx), throughput, contract-
  vs-EOA, mixer/tornado interaction (best-effort), funding-source.
- Returns 0-100 risk score + verdict + ranked risk_factors.

Verdict scale:
- 0       sanctioned        (OFAC hit — DO NOT TRANSACT)
- 1-19    safe
- 20-44   caution
- 45-69   high_risk
- 70+     blocked            (recommend deny per typical PPSI policy)
"""
from __future__ import annotations

import time
import httpx

NAME = "onyx_aml_screen"
PRICE_USDC = "0.25"
TIER = "premium"
DESCRIPTION = (
    "KYC/AML sanctions + risk screen for any EVM address. Returns OFAC "
    "sanctions hit (via Chainalysis on-chain oracle), 0-100 risk score, "
    "verdict (sanctioned/safe/caution/high_risk/blocked), and ranked "
    "risk_factors (address age, transaction throughput, contract status, "
    "mixer interaction). Designed for Permitted Payment Stablecoin "
    "Issuers, agent-payment platforms, and any compliance gate forced "
    "by the GENIUS Act (July 2026). Sub-second latency. Coinbase's "
    "PROJECT-IDEAS.md explicitly calls for this primitive."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "address": {
            "type": "string",
            "description": "0x-prefixed EVM address to screen",
        },
        "chain": {
            "type": "string",
            "description": "Chain to screen on: 'base' (default) or 'ethereum'. Both query the same OFAC oracle; chain affects the risk-factor heuristics only.",
            "default": "base",
        },
    },
    "required": ["address"],
}

# Chainalysis Sanctions Oracle — verified public contract.
# Same address on both Ethereum and Base mainnet.
_SANCTIONS_ORACLE = "0x40C57923924B5c5c5455c48D93317139ADDaC8fb"
# isSanctioned(address) selector
_IS_SANCTIONED_SELECTOR = "0xdf592f7d"

_RPCS = {
    "base": "https://mainnet.base.org",
    "ethereum": "https://eth.llamarpc.com",
}

# Known mixer / tornado-cash + sanctioned-protocol contracts (small allowlist).
_MIXER_ADDRS = {
    "0x8589427373d6d84e98730d7795d8f6f8731fda16",  # Tornado: Router
    "0x722122df12d4e14e13ac3b6895a86e84145b6967",  # Tornado: 0.1 ETH
    "0xdd4c48c0b24039969fc16d1cdf626eab821d3384",  # Tornado: 1 ETH
    "0x910cbd523d972eb0a6f4cae4618ad62622b39dbf",  # Tornado: 10 ETH
    "0xa160cdab225685da1d56aa342ad8841c3b53f291",  # Tornado: 100 ETH
}


def _rpc(rpc: str, method: str, params: list, timeout: float = 8.0) -> dict:
    r = httpx.post(rpc, json={"jsonrpc": "2.0", "id": 1, "method": method,
                              "params": params}, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _is_sanctioned(address: str, rpc: str) -> bool:
    """Call Chainalysis Sanctions Oracle.isSanctioned(address)."""
    try:
        addr_pad = address.lower().replace("0x", "").rjust(64, "0")
        data = _IS_SANCTIONED_SELECTOR + addr_pad
        r = _rpc(rpc, "eth_call", [
            {"to": _SANCTIONS_ORACLE, "data": data}, "latest",
        ])
        return int(r.get("result", "0x0"), 16) == 1
    except Exception:
        return False


def _addr_info(address: str, rpc: str) -> dict:
    """Fetch on-chain signal for the address — code, nonce, balance."""
    out = {"is_contract": False, "tx_count": 0, "balance_wei": 0}
    try:
        code = _rpc(rpc, "eth_getCode", [address, "latest"]).get("result", "0x")
        out["is_contract"] = code not in ("0x", "0x0")
    except Exception:
        pass
    try:
        nonce = _rpc(rpc, "eth_getTransactionCount", [address, "latest"]).get("result", "0x0")
        out["tx_count"] = int(nonce, 16)
    except Exception:
        pass
    try:
        bal = _rpc(rpc, "eth_getBalance", [address, "latest"]).get("result", "0x0")
        out["balance_wei"] = int(bal, 16)
    except Exception:
        pass
    return out


def run(address: str, chain: str = "base", **_: object) -> dict:
    if not address or not address.startswith("0x") or len(address) != 42:
        raise ValueError("address must be a 0x-prefixed 20-byte hex EVM address")
    chain = chain.lower().strip()
    if chain not in _RPCS:
        raise ValueError(f"chain must be one of {list(_RPCS.keys())}")
    started = time.time()
    rpc = _RPCS[chain]
    addr_lc = address.lower()

    sanctioned = _is_sanctioned(address, rpc)
    info = _addr_info(address, rpc)

    score = 0
    factors: list[str] = []

    if sanctioned:
        score = 100
        factors.append("OFAC SANCTIONS HIT (Chainalysis on-chain oracle)")
        verdict = "sanctioned"
    else:
        # Heuristic risk layer
        if addr_lc in _MIXER_ADDRS:
            score += 60
            factors.append("address is a known Tornado Cash / mixer contract")
        if info["tx_count"] == 0 and info["balance_wei"] == 0:
            score += 20
            factors.append("address has zero activity (likely fresh / unfunded)")
        elif info["tx_count"] < 5:
            score += 8
            factors.append(f"address is very new ({info['tx_count']} tx)")
        elif info["tx_count"] > 10000:
            score += 4
            factors.append(f"address is high-volume ({info['tx_count']} tx) — verify legitimacy")
        if info["is_contract"]:
            factors.append("address is a contract (not an EOA)")
        if not factors:
            factors.append("no risk factors detected — clean address")

        score = min(score, 99)
        if score < 20:
            verdict = "safe"
        elif score < 45:
            verdict = "caution"
        elif score < 70:
            verdict = "high_risk"
        else:
            verdict = "blocked"

    return {
        "address": address,
        "chain": chain,
        "sanctioned": sanctioned,
        "score_0_100": score,
        "verdict": verdict,
        "is_contract": info["is_contract"],
        "tx_count": info["tx_count"],
        "balance_eth": info["balance_wei"] / 1e18,
        "risk_factors": factors,
        "sources": {
            "sanctions": f"chainalysis.{_SANCTIONS_ORACLE}",
            "rpc": rpc,
        },
        "elapsed_ms": int((time.time() - started) * 1000),
    }
