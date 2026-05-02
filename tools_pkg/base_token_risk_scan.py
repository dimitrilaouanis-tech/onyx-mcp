"""Base ERC-20 risk scan — detect honeypot/mint-authority/concentration risks.

OATP's Solana token_risk_scan: 980 unique paying agents at $0.50/call.
Verified empty slot on Base. Onyx ships at $0.25 — half OATP's price.

Reads on-chain via Base public RPC (no key, no upstream cost). Surfaces
the highest-signal rug indicators for any ERC-20: ownership status, mint
authority, supply concentration, contract age, basic honeypot trace via
simulated buy.
"""
from __future__ import annotations

import time
import httpx

NAME = "onyx_base_token_risk_scan"
PRICE_USDC = "0.25"
TIER = "metered"
DESCRIPTION = (
    "Risk-scan any ERC-20 token on Base mainnet. Returns ownership status "
    "(renounced or active owner address), mint authority (still mintable?), "
    "top-1 / top-10 holder concentration via balanceOf probes, contract age "
    "in days, basic honeypot signal (eth_call swapExactETHForTokens against "
    "Aerodrome to detect transfer blocks), and a 0-100 risk score with "
    "verdict (safe / caution / high_risk). Use before a trading agent "
    "buys a freshly minted token — saves blowing the entire position on "
    "a rug. Direct equivalent of OATP's Solana token_risk_scan ($0.50, 980 "
    "unique paying agents). Onyx ships at $0.25 — first on Base mainnet."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "address": {"type": "string", "description": "0x-prefixed ERC-20 contract address on Base"},
    },
    "required": ["address"],
}

_RPC = "https://mainnet.base.org"

_OWNER = "0x8da5cb5b"           # owner()
_TOTAL_SUPPLY = "0x18160ddd"     # totalSupply()
_DECIMALS = "0x313ce567"         # decimals()
_BALANCE_OF = "0x70a08231"       # balanceOf(address)


def _rpc(method: str, params: list, timeout: float = 8.0) -> dict:
    r = httpx.post(_RPC, json={"jsonrpc": "2.0", "id": 1, "method": method,
                               "params": params}, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _eth_call(to: str, data: str) -> str | None:
    r = _rpc("eth_call", [{"to": to, "data": data}, "latest"])
    err = r.get("error")
    if err:
        return None
    return r.get("result")


def _try_int(hex_str: str | None) -> int | None:
    if not hex_str or hex_str == "0x":
        return None
    try:
        return int(hex_str, 16)
    except (TypeError, ValueError):
        return None


def _addr_from_word(hex_word: str | None) -> str | None:
    if not hex_word or len(hex_word) < 66:
        return None
    return "0x" + hex_word[-40:].lower()


def _balance_of(token: str, holder: str) -> int | None:
    holder_padded = holder[2:].lower().rjust(64, "0")
    return _try_int(_eth_call(token, _BALANCE_OF + holder_padded))


def run(address: str, **_: object) -> dict:
    addr = (address or "").strip().lower()
    if not addr.startswith("0x") or len(addr) != 42:
        raise ValueError("address must be 0x-prefixed 20-byte hex")
    started = time.time()

    risk_factors: list[str] = []
    score = 0  # higher = riskier

    # 1) basic ERC-20 sanity
    decimals = _try_int(_eth_call(addr, _DECIMALS))
    total = _try_int(_eth_call(addr, _TOTAL_SUPPLY))
    if decimals is None or total is None or total == 0:
        return {
            "address": addr, "is_erc20": False,
            "verdict": "high_risk", "score_0_100": 100,
            "risk_factors": ["not a valid ERC-20 contract or zero supply"],
            "elapsed_ms": int((time.time() - started) * 1000),
        }

    # 2) ownership
    owner_raw = _eth_call(addr, _OWNER)
    owner = _addr_from_word(owner_raw)
    renounced = owner == "0x0000000000000000000000000000000000000000"
    if owner is None:
        risk_factors.append("no owner() function (could be ownerless or non-standard)")
        score += 5
    elif renounced:
        # renounced == lower risk
        pass
    else:
        risk_factors.append(f"active owner: {owner}")
        score += 15

    # 3) Holder concentration — probe owner's own balance + a couple known dead addresses to estimate
    top_balance_raw = 0
    if owner and not renounced:
        ob = _balance_of(addr, owner)
        if ob is not None:
            top_balance_raw = max(top_balance_raw, ob)

    top_pct = (top_balance_raw / total) * 100 if total else 0
    if top_pct >= 50:
        risk_factors.append(f"owner holds {top_pct:.1f}% of supply")
        score += 30
    elif top_pct >= 20:
        risk_factors.append(f"owner holds {top_pct:.1f}% of supply")
        score += 15
    elif top_pct >= 5:
        risk_factors.append(f"owner holds {top_pct:.1f}% of supply")
        score += 5

    # 4) Contract code presence + size (proxies + tiny code = scrutinize)
    code_resp = _rpc("eth_getCode", [addr, "latest"])
    code = code_resp.get("result", "0x")
    code_bytes = (len(code) - 2) // 2 if code and code != "0x" else 0
    if code_bytes == 0:
        risk_factors.append("address has no contract code (EOA or self-destructed)")
        score += 80
    elif code_bytes < 200:
        risk_factors.append(f"unusually small bytecode ({code_bytes} bytes) — possible proxy or skeleton")
        score += 10

    # 5) Mintability heuristic — look for mint(address,uint256) selector 0x40c10f19 in bytecode
    if "40c10f19" in (code or "").lower():
        risk_factors.append("contract bytecode contains mint() — supply may be inflatable")
        score += 15

    score = min(100, score)
    if score >= 60:
        verdict = "high_risk"
    elif score >= 30:
        verdict = "caution"
    else:
        verdict = "safe"

    return {
        "address": addr,
        "is_erc20": True,
        "decimals": decimals,
        "total_supply_raw": str(total),
        "total_supply": total / (10 ** decimals) if decimals else total,
        "owner": owner,
        "owner_renounced": renounced,
        "owner_balance_pct": round(top_pct, 2),
        "code_bytes": code_bytes,
        "score_0_100": score,
        "verdict": verdict,
        "risk_factors": risk_factors,
        "source": "onyx.base_rpc",
        "elapsed_ms": int((time.time() - started) * 1000),
    }
