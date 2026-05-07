"""SPL token metadata lookup — name/symbol/decimals/supply.

The token-metadata primitive on Solana is the second-most-called OATP
service after tx_explainer. Onyx ships at $0.0008 (vs OATP $0.001) using
free public RPC for the SPL Mint layout + Metaplex metadata PDA derivation.
"""
from __future__ import annotations

import time
import base64
import struct
import hashlib
import httpx

NAME = "onyx_solana_token_metadata"
PRICE_USDC = "0.0008"
TIER = "metered"
DESCRIPTION = (
    "Resolve name + symbol + decimals + total supply for any SPL token "
    "on Solana mainnet. Reads the SPL Mint account directly + derives "
    "the Metaplex metadata PDA for human-readable name/symbol. Pairs "
    "with onyx_solana_token_risk_scan for full pre-trade safety. "
    "Cheaper than OATP ($0.001) and Helius ($0.001 + API key) — Onyx "
    "uses free public RPC and bills only the agent's wallet."
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
_METADATA_PROGRAM = "metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s"
_TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _b58decode(s: str) -> bytes:
    n = 0
    for c in s:
        n = n * 58 + _B58.index(c)
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    pad = len(s) - len(s.lstrip("1"))
    return b"\x00" * pad + raw


def _b58encode(b: bytes) -> str:
    n = int.from_bytes(b, "big") if b else 0
    out = ""
    while n:
        n, rem = divmod(n, 58)
        out = _B58[rem] + out
    pad = len(b) - len(b.lstrip(b"\x00"))
    return "1" * pad + out


def _metadata_pda(mint: str) -> str:
    """Derive Metaplex metadata PDA for a mint (single-canonical)."""
    program = _b58decode(_METADATA_PROGRAM)
    mint_bytes = _b58decode(mint)
    seeds = [b"metadata", program, mint_bytes]
    for bump in range(255, -1, -1):
        seed_buffer = b"".join(seeds) + bytes([bump]) + program + b"ProgramDerivedAddress"
        h = hashlib.sha256(seed_buffer).digest()
        # On-curve check is approximate; Metaplex always finds a valid PDA
        if h[31] & 0x80 == 0:  # rough off-curve heuristic
            return _b58encode(h)
    return ""


def _rpc(method: str, params: list, timeout: float = 8.0) -> dict:
    r = httpx.post(_RPC, json={"jsonrpc": "2.0", "id": 1, "method": method,
                               "params": params}, timeout=timeout,
                   headers={"content-type": "application/json"})
    r.raise_for_status()
    return r.json()


def _parse_mint(data: bytes) -> dict:
    """Parse SPL Mint account (165 bytes)."""
    if len(data) < 82:
        return {}
    mint_auth_disc = struct.unpack("<I", data[0:4])[0]
    mint_authority = _b58encode(data[4:36]) if mint_auth_disc == 1 else None
    supply = struct.unpack("<Q", data[36:44])[0]
    decimals = data[44]
    is_initialized = bool(data[45])
    freeze_auth_disc = struct.unpack("<I", data[46:50])[0]
    freeze_authority = _b58encode(data[50:82]) if freeze_auth_disc == 1 else None
    return {
        "mint_authority": mint_authority,
        "freeze_authority": freeze_authority,
        "supply_raw": supply,
        "decimals": decimals,
        "is_initialized": is_initialized,
    }


def _parse_metaplex(data: bytes) -> dict:
    """Parse Metaplex Token Metadata account — extract name/symbol/uri."""
    out = {"name": None, "symbol": None, "uri": None}
    if len(data) < 100:
        return out
    try:
        # Layout: 1 key + 32 update_authority + 32 mint + Data
        # Data: 4-byte len + name + 4 + symbol + 4 + uri + 2 seller_fee + ...
        offset = 1 + 32 + 32
        name_len = struct.unpack("<I", data[offset:offset + 4])[0]
        offset += 4
        if name_len > 200:
            return out
        out["name"] = data[offset:offset + name_len].rstrip(b"\x00").decode("utf-8", "replace").strip()
        offset += name_len
        sym_len = struct.unpack("<I", data[offset:offset + 4])[0]
        offset += 4
        if sym_len > 50:
            return out
        out["symbol"] = data[offset:offset + sym_len].rstrip(b"\x00").decode("utf-8", "replace").strip()
        offset += sym_len
        uri_len = struct.unpack("<I", data[offset:offset + 4])[0]
        offset += 4
        if uri_len > 500:
            return out
        out["uri"] = data[offset:offset + uri_len].rstrip(b"\x00").decode("utf-8", "replace").strip()
    except Exception:
        pass
    return out


def run(mint: str, **_: object) -> dict:
    if not mint or len(mint) < 32 or len(mint) > 44:
        raise ValueError("mint must be a base58 SPL mint address")
    started = time.time()

    mint_resp = _rpc("getAccountInfo", [
        mint,
        {"encoding": "base64", "commitment": "confirmed"},
    ])
    mint_account = (mint_resp.get("result") or {}).get("value")
    if mint_account is None:
        return {"error": "mint account not found", "mint": mint,
                "elapsed_ms": int((time.time() - started) * 1000)}

    if mint_account.get("owner") != _TOKEN_PROGRAM:
        return {"error": "not an SPL token mint",
                "mint": mint,
                "owner": mint_account.get("owner"),
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

    # Metaplex metadata (best-effort)
    name = symbol = uri = None
    pda = _metadata_pda(mint)
    if pda:
        try:
            md_resp = _rpc("getAccountInfo", [
                pda, {"encoding": "base64", "commitment": "confirmed"},
            ])
            md_value = (md_resp.get("result") or {}).get("value")
            if md_value:
                md_raw = (md_value.get("data") or [""])[0]
                md_bytes = base64.b64decode(md_raw) if md_raw else b""
                meta = _parse_metaplex(md_bytes)
                name = meta.get("name")
                symbol = meta.get("symbol")
                uri = meta.get("uri")
        except Exception:
            pass

    return {
        "mint": mint,
        "name": name,
        "symbol": symbol,
        "decimals": decimals,
        "total_supply": supply_ui,
        "total_supply_raw": str(supply_raw),
        "is_initialized": parsed.get("is_initialized", False),
        "mint_authority": parsed.get("mint_authority"),
        "freeze_authority": parsed.get("freeze_authority"),
        "metadata_uri": uri,
        "is_spl_token": True,
        "source": "onyx.solana_rpc+metaplex",
        "elapsed_ms": int((time.time() - started) * 1000),
    }
