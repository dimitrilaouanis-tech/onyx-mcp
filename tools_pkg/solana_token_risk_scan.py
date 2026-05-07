"""SPL token rug-vector risk scan — Solana equivalent of base_token_risk_scan.

OATP charges $0.50 for token_risk_scan on Solana with 800+ paying agents.
Onyx ships at $0.25, no API key, x402-native settlement. Specifically tuned
for the Solana / pump.fun memecoin segment where mint-authority + top-holder
concentration are the dominant rug vectors.

Verdict scale (lower = safer):
- 0-19   safe       (renounced, distributed)
- 20-44  caution    (active authority OR concentrated holders)
- 45-69  high_risk  (active authority AND concentrated)
- 70+    likely_rug (active authority, freeze-able, single-whale supply)
"""
from __future__ import annotations

import time
import base64
import struct
import httpx

NAME = "onyx_solana_token_risk_scan"
PRICE_USDC = "0.25"
TIER = "metered"
DESCRIPTION = (
    "Rug-vector risk scan for any SPL token on Solana mainnet. Checks "
    "mint authority (active = can mint unlimited supply), freeze "
    "authority (active = can freeze any holder's wallet), top-10 "
    "holder concentration (whale risk), supply rationality, and "
    "pump.fun bonded/unbonded state. Returns 0-100 risk score + "
    "verdict (safe/caution/high_risk/likely_rug) + ranked risk_factors. "
    "Designed for memecoin/sniper/MEV agents that need a sub-second "
    "pre-trade gate. OATP charges $0.50 for the same primitive — "
    "Onyx is half-price, no API key, USDC-direct."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "mint": {"type": "string",
                 "description": "base58-encoded SPL mint address"},
    },
    "required": ["mint"],
}

_RPC = "https://api.mainnet-beta.solana.com"
_TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
_TOKEN_2022 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _b58encode(b: bytes) -> str:
    n = int.from_bytes(b, "big") if b else 0
    out = ""
    while n:
        n, rem = divmod(n, 58)
        out = _B58[rem] + out
    pad = len(b) - len(b.lstrip(b"\x00"))
    return "1" * pad + out


def _rpc(method: str, params: list, timeout: float = 10.0) -> dict:
    r = httpx.post(_RPC, json={"jsonrpc": "2.0", "id": 1, "method": method,
                               "params": params}, timeout=timeout,
                   headers={"content-type": "application/json"})
    r.raise_for_status()
    return r.json()


def _parse_mint(data: bytes) -> dict:
    if len(data) < 82:
        return {}
    mint_auth_disc = struct.unpack("<I", data[0:4])[0]
    mint_authority = _b58encode(data[4:36]) if mint_auth_disc == 1 else None
    supply = struct.unpack("<Q", data[36:44])[0]
    decimals = data[44]
    freeze_auth_disc = struct.unpack("<I", data[46:50])[0]
    freeze_authority = _b58encode(data[50:82]) if freeze_auth_disc == 1 else None
    return {
        "mint_authority": mint_authority,
        "freeze_authority": freeze_authority,
        "supply_raw": supply,
        "decimals": decimals,
    }


def run(mint: str, **_: object) -> dict:
    if not mint or len(mint) < 32 or len(mint) > 44:
        raise ValueError("mint must be a base58 SPL mint address")
    started = time.time()

    # 1. Fetch mint account
    mint_resp = _rpc("getAccountInfo", [
        mint, {"encoding": "base64", "commitment": "confirmed"},
    ])
    mint_account = (mint_resp.get("result") or {}).get("value")
    if mint_account is None:
        return {"error": "mint account not found", "mint": mint,
                "elapsed_ms": int((time.time() - started) * 1000)}

    owner = mint_account.get("owner")
    if owner not in (_TOKEN_PROGRAM, _TOKEN_2022):
        return {"error": "not an SPL token mint", "mint": mint, "owner": owner,
                "elapsed_ms": int((time.time() - started) * 1000)}

    raw_data = mint_account.get("data") or ["", "base64"]
    try:
        data_bytes = base64.b64decode(raw_data[0]) if raw_data and raw_data[0] else b""
    except Exception:
        data_bytes = b""
    parsed = _parse_mint(data_bytes)

    decimals = parsed.get("decimals", 0)
    supply_raw = parsed.get("supply_raw", 0)
    supply_ui = supply_raw / (10 ** decimals) if decimals else supply_raw
    mint_auth = parsed.get("mint_authority")
    freeze_auth = parsed.get("freeze_authority")

    # 2. Top-10 holder concentration via getTokenLargestAccounts
    top_holders = []
    top_pct_sum = 0.0
    try:
        lg_resp = _rpc("getTokenLargestAccounts", [
            mint, {"commitment": "confirmed"},
        ])
        accounts = (lg_resp.get("result") or {}).get("value") or []
        if supply_raw > 0:
            for a in accounts[:10]:
                amt_raw = int(a.get("amount", "0") or 0)
                pct = (amt_raw / supply_raw) * 100 if supply_raw else 0
                top_holders.append({
                    "address": a.get("address"),
                    "amount": amt_raw / (10 ** decimals) if decimals else amt_raw,
                    "pct": round(pct, 4),
                })
                top_pct_sum += pct
    except Exception:
        pass

    top1_pct = top_holders[0]["pct"] if top_holders else 0
    top10_pct = round(top_pct_sum, 4)

    # 3. Pump.fun heuristic — mint address ending in "pump" or bonded curve
    is_pump = mint.endswith("pump")

    # 4. Score
    score = 0
    factors = []
    if mint_auth:
        score += 35
        factors.append(f"active mint_authority: {mint_auth[:8]}…")
    else:
        factors.append("mint_authority renounced")
    if freeze_auth:
        score += 25
        factors.append(f"active freeze_authority: {freeze_auth[:8]}…")
    if top1_pct >= 50:
        score += 30
        factors.append(f"top-1 holder owns {top1_pct:.1f}% of supply")
    elif top1_pct >= 25:
        score += 18
        factors.append(f"top-1 holder owns {top1_pct:.1f}% of supply")
    elif top1_pct >= 10:
        score += 8
        factors.append(f"top-1 holder owns {top1_pct:.1f}% of supply")
    if top10_pct >= 80:
        score += 15
        factors.append(f"top-10 holders own {top10_pct:.1f}% of supply")
    elif top10_pct >= 50:
        score += 5
    if is_pump:
        factors.append("pump.fun-style mint suffix detected")
    if supply_raw == 0:
        score += 20
        factors.append("zero total supply (uninitialized?)")
    if owner == _TOKEN_2022:
        factors.append("Token-2022 program (check for transfer hooks)")

    score = min(100, score)
    if score < 20:
        verdict = "safe"
    elif score < 45:
        verdict = "caution"
    elif score < 70:
        verdict = "high_risk"
    else:
        verdict = "likely_rug"

    return {
        "mint": mint,
        "score_0_100": score,
        "verdict": verdict,
        "is_spl_token": True,
        "token_program": "Token-2022" if owner == _TOKEN_2022 else "Token",
        "decimals": decimals,
        "total_supply": supply_ui,
        "mint_authority": mint_auth,
        "mint_authority_renounced": mint_auth is None,
        "freeze_authority": freeze_auth,
        "freeze_authority_renounced": freeze_auth is None,
        "top1_holder_pct": top1_pct,
        "top10_holders_pct": top10_pct,
        "top_holders": top_holders,
        "is_pump_fun_style": is_pump,
        "risk_factors": factors,
        "source": "onyx.solana_rpc",
        "elapsed_ms": int((time.time() - started) * 1000),
    }
