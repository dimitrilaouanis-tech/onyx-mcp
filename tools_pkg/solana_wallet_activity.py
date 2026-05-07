"""Recent on-chain activity for any Solana wallet.

Whale-watching, copy-trading, and KYT agents all need a fast feed of
"what is wallet X doing right now." This tool returns the last N
signatures for a wallet, parsed into an event-style summary so agents
don't have to make a second tx_explainer call per signature.
"""
from __future__ import annotations

import time
import httpx

NAME = "onyx_solana_wallet_activity"
PRICE_USDC = "0.002"
TIER = "metered"
DESCRIPTION = (
    "Recent on-chain activity for any Solana wallet. Returns the last "
    "N signatures (default 25, max 100) with slot, block_time, status, "
    "fee, and best-effort program/action classification (swap, "
    "transfer, stake, NFT). Designed for whale-watching, copy-trading, "
    "and risk-monitoring agents that need a sub-second feed without "
    "managing their own RPC. Cheaper than Helius webhooks ($25/mo) and "
    "Birdeye wallet-portfolio ($0.002 + API key). x402-direct, no signup."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "wallet": {"type": "string",
                   "description": "base58-encoded Solana wallet address"},
        "limit": {"type": "integer",
                  "description": "Number of recent signatures (1-100, default 25)",
                  "default": 25},
    },
    "required": ["wallet"],
}

_RPC = "https://api.mainnet-beta.solana.com"

_KNOWN_PROGRAMS = {
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": "jupiter_swap",
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc": "whirlpool_swap",
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "raydium_amm",
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P": "pump_fun",
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA": "spl_token",
    "Stake11111111111111111111111111111111111111": "stake_program",
    "Vote111111111111111111111111111111111111111": "vote_program",
    "11111111111111111111111111111111": "system_program",
    "metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s": "metaplex_metadata",
    "MEisE1HzehtrDpAAT8PnLHjpSSkRYakotTuJRPjTpo8": "magiceden_v2",
    "TSWAPaqyCSx2KABk68Shruf4rp7CxcNi8hAsbdwmHbN": "tensor_swap",
}


def _rpc(method: str, params: list, timeout: float = 8.0) -> dict:
    r = httpx.post(_RPC, json={"jsonrpc": "2.0", "id": 1, "method": method,
                               "params": params}, timeout=timeout,
                   headers={"content-type": "application/json"})
    r.raise_for_status()
    return r.json()


def run(wallet: str, limit: int = 25, **_: object) -> dict:
    if not wallet or len(wallet) < 32 or len(wallet) > 44:
        raise ValueError("wallet must be a base58 Solana address")
    if not (1 <= limit <= 100):
        raise ValueError("limit must be in [1, 100]")
    started = time.time()

    sig_resp = _rpc("getSignaturesForAddress", [
        wallet, {"limit": limit, "commitment": "confirmed"},
    ])
    sigs = sig_resp.get("result") or []
    if not sigs:
        return {"wallet": wallet, "count": 0, "activity": [],
                "source": "onyx.solana_rpc",
                "elapsed_ms": int((time.time() - started) * 1000)}

    activity = []
    error_count = 0
    for s in sigs:
        sig = s.get("signature")
        entry = {
            "signature": sig,
            "slot": s.get("slot"),
            "block_time": s.get("blockTime"),
            "status": "fail" if s.get("err") else "success",
            "fee_sol": None,
            "actions": [],
            "memo": s.get("memo"),
        }
        if s.get("err"):
            error_count += 1
        activity.append(entry)

    # Best-effort classification — fetch first 10 txs for program tags
    classify_n = min(10, len(activity))
    for i in range(classify_n):
        sig = activity[i]["signature"]
        try:
            tx_resp = _rpc("getTransaction", [
                sig, {"encoding": "jsonParsed",
                       "maxSupportedTransactionVersion": 0,
                       "commitment": "confirmed"},
            ], timeout=5.0)
            tx = tx_resp.get("result")
            if tx is None:
                continue
            meta = tx.get("meta") or {}
            msg = (tx.get("transaction") or {}).get("message") or {}
            instrs = msg.get("instructions") or []
            programs = []
            for ins in instrs:
                pid = ins.get("programId")
                if pid:
                    tag = _KNOWN_PROGRAMS.get(pid, pid[:8])
                    if tag not in programs:
                        programs.append(tag)
            activity[i]["actions"] = programs[:8]
            activity[i]["fee_sol"] = (meta.get("fee", 0) or 0) / 1e9
        except Exception:
            continue

    return {
        "wallet": wallet,
        "count": len(activity),
        "error_count": error_count,
        "classified": classify_n,
        "activity": activity,
        "source": "onyx.solana_rpc",
        "elapsed_ms": int((time.time() - started) * 1000),
    }
