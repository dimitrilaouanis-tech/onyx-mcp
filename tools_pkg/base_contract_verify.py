"""Base contract verification + ABI lookup via Blockscout.

Returns: is_verified, name, compiler version, language, optimization flag,
ABI entry count, proxy detection (auto-resolves to implementation contract),
license, source code size. Optional include_full_abi/include_source.

Composes with onyx_base_token_risk_scan (unverified contracts = automatic
red flag) and onyx_base_event_logs (you need the ABI to decode events
properly).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

NAME = "onyx_base_contract_verify"
PRICE_USDC = "0.002"
TIER = "metered"
DESCRIPTION = (
    "Contract verification + ABI metadata for any Base address. Returns "
    "is_verified, contract name, compiler version, language, optimization, "
    "ABI entry count, license, source code size. Auto-detects EIP-1967/"
    "OZ/UUPS proxies and resolves to the implementation contract. Backed "
    "by Blockscout (free, no auth). Use before any swap or interaction — "
    "unverified contracts are an instant red flag."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "address": {
            "type": "string",
            "description": "Contract address on Base mainnet (0x... 20-byte hex).",
        },
        "include_full_abi": {
            "type": "boolean",
            "default": False,
            "description": "If true, return the full ABI array (can be large). Otherwise just the entry count + function/event name list.",
        },
        "include_source": {
            "type": "boolean",
            "default": False,
            "description": "If true, return full source code (can be 10s of KB). Otherwise just the byte length.",
        },
        "resolve_proxy": {
            "type": "boolean",
            "default": True,
            "description": "If true and address is a proxy, also fetch the implementation contract's metadata.",
        },
    },
    "required": ["address"],
}

_BLOCKSCOUT = "https://base.blockscout.com/api/v2/smart-contracts"
_UA = "onyx-base-contract-verify/1.0"


def _hex_addr(s: str) -> bool:
    s = (s or "").strip()
    return s.startswith("0x") and len(s) == 42


def _fetch(addr: str, timeout: float = 10.0) -> dict | None:
    url = f"{_BLOCKSCOUT}/{addr.lower()}"
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError):
        return None


def _abi_summary(abi: list | None) -> dict:
    if not abi:
        return {"functions": [], "events": [], "errors": [], "total": 0}
    funcs, events, errors = [], [], []
    for item in abi:
        if not isinstance(item, dict):
            continue
        t = item.get("type")
        n = item.get("name")
        if t == "function" and n:
            funcs.append(n)
        elif t == "event" and n:
            events.append(n)
        elif t == "error" and n:
            errors.append(n)
    return {
        "functions": sorted(set(funcs))[:40],
        "events": sorted(set(events))[:20],
        "errors": sorted(set(errors))[:10],
        "total": len(abi),
    }


def _shape(d: dict, include_full_abi: bool, include_source: bool) -> dict:
    abi = d.get("abi") or []
    src = d.get("source_code") or ""
    out = {
        "is_verified": bool(d.get("is_verified")),
        "name": d.get("name"),
        "compiler": d.get("compiler_version"),
        "language": d.get("language"),
        "optimization_enabled": d.get("optimization_enabled"),
        "optimization_runs": d.get("optimization_runs"),
        "license": d.get("license_type") or d.get("license"),
        "proxy_type": d.get("proxy_type"),
        "implementations": d.get("implementations"),
        "external_libraries": d.get("external_libraries"),
        "source_size_bytes": len(src),
        "abi": _abi_summary(abi),
        "evm_version": d.get("evm_version"),
        "verified_at": d.get("verified_at"),
        "is_self_destructed": d.get("is_self_destructed"),
        "has_methods_read": bool(d.get("has_methods_read")),
        "has_methods_write": bool(d.get("has_methods_write")),
    }
    if include_full_abi:
        out["abi_full"] = abi
    if include_source:
        out["source_code"] = src
    return out


def run(
    address: str,
    include_full_abi: bool = False,
    include_source: bool = False,
    resolve_proxy: bool = True,
    **_: object,
) -> dict:
    if not _hex_addr(address):
        return {"ok": False, "error": "address must be 0x... 20-byte hex"}

    d = _fetch(address)
    if d is None:
        return {"ok": False, "address": address.lower(), "is_verified": False, "error": "not_found_or_unverified"}

    shaped = _shape(d, include_full_abi, include_source)
    out = {
        "ok": True,
        "address": address.lower(),
        **shaped,
    }

    # If proxy + resolve_proxy, recurse on implementation
    impls = d.get("implementations") or []
    if resolve_proxy and impls and isinstance(impls, list):
        impl_addr = (impls[0].get("address_hash") or "").strip() if isinstance(impls[0], dict) else ""
        if _hex_addr(impl_addr):
            impl_data = _fetch(impl_addr)
            if impl_data:
                out["implementation_details"] = {
                    "address": impl_addr.lower(),
                    **_shape(impl_data, include_full_abi, include_source),
                }

    # Quick verdict
    if not out["is_verified"]:
        out["risk_signal"] = "RED — unverified contract, do not interact without source review"
    elif out.get("is_self_destructed"):
        out["risk_signal"] = "RED — contract is self-destructed"
    elif out["proxy_type"] and not out.get("implementation_details"):
        out["risk_signal"] = "YELLOW — proxy but implementation could not be fetched"
    else:
        out["risk_signal"] = "GREEN — verified" + (" (proxy + impl verified)" if out["proxy_type"] else "")
    return out


run.__when_to_use__ = (
    "Before any swap, approval, or interaction with an unfamiliar Base "
    "contract. Unverified = instant red flag. Proxies need impl audit."
)
run.__vs_alternatives__ = (
    "Etherscan v2 Base requires paid API plan. Sourcify v2 returns sparse "
    "metadata. Blockscout is the richest free source for Base."
)
run.__example_request__ = {
    "address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
}
