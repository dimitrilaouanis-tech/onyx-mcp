"""Capability bundle — composes 3-5 Onyx tools into one paid call.

Agents that follow a deterministic chain ('check verification, then risk_scan,
then bridge_quote') currently pay N separate x402 settlements. This tool
bundles a known-good chain into a single paid call at a discount, atomic
delivery (all-or-none), and one AR-1 receipt covering the whole chain.

Predefined bundles (chosen for proven agent demand):
  - 'safety_check_base' — contract_verify + token_risk_scan + agent_audit_trail
  - 'tx_full_inspect' — tx_explainer + tx_simulator + tx_decode
  - 'swap_prep' — token_risk_scan + dex_pair_lookup + swap_quote
  - 'cross_chain' — swap_quote + bridge_quote + chain_picker
  - 'agent_kyc' — agent_id + kya_verify + oai_lookup
"""
from __future__ import annotations

NAME = "onyx_capability_bundle"
PRICE_USDC = "0.02"
TIER = "metered"
DESCRIPTION = (
    "Bundle 3-5 Onyx tools into one paid call at a discount. Atomic delivery "
    "(all-or-none), one AR-1 receipt for the whole chain, single x402 "
    "settlement vs N separate. Predefined bundles for proven workflows: "
    "safety_check_base (verify + risk_scan + audit), tx_full_inspect "
    "(explainer + simulator + decode), swap_prep (risk + dex_pair + quote), "
    "cross_chain (swap + bridge + chain_picker), agent_kyc (id + kya + oai)."
)

_BUNDLES: dict[str, dict] = {
    "safety_check_base": {
        "tools": ["onyx_base_contract_verify", "onyx_base_token_risk_scan", "onyx_agent_audit_trail"],
        "individual_price_total_usdc": 0.002 + 0.25 + 0.05,
        "discount_pct": 15,
        "description": "Full safety audit of a Base address: verify contract, scan token risk, audit agent history.",
        "input_keys_required": ["address"],
    },
    "tx_full_inspect": {
        "tools": ["onyx_base_tx_explainer", "onyx_base_tx_simulator", "onyx_base_tx_decode"],
        "individual_price_total_usdc": 0.05 + 0.10 + 0.002,
        "discount_pct": 20,
        "description": "Comprehensive Base tx analysis: human explain, simulate gas + revert, raw ABI decode.",
        "input_keys_required": ["tx_hash"],
    },
    "swap_prep": {
        "tools": ["onyx_base_token_risk_scan", "onyx_base_dex_pair_lookup", "onyx_base_swap_quote"],
        "individual_price_total_usdc": 0.25 + 0.0015 + 0.002,
        "discount_pct": 18,
        "description": "Pre-swap due diligence on Base: risk scan output token + check liquidity pairs + best-route quote.",
        "input_keys_required": ["token_in", "token_out", "amount_in"],
    },
    "cross_chain": {
        "tools": ["onyx_base_swap_quote", "onyx_base_bridge_quote", "onyx_x402_chain_picker"],
        "individual_price_total_usdc": 0.002 + 0.003 + 0.0005,
        "discount_pct": 15,
        "description": "Cross-chain capability: quote same-chain swap, quote bridge to target chain, rank chains by gas+facilitator health.",
        "input_keys_required": ["token_in", "token_out", "amount_in", "to_chain_id"],
    },
    "agent_kyc": {
        "tools": ["onyx_agent_id", "onyx_kya_verify", "onyx_oai_lookup"],
        "individual_price_total_usdc": 0.001 + 0.001 + 0.001,
        "discount_pct": 10,
        "description": "Full agent identity stack: wallet-derived ID + KYA credential verify + OAI trust score.",
        "input_keys_required": ["wallet_or_did"],
    },
}

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "bundle": {
            "type": "string",
            "enum": list(_BUNDLES.keys()),
            "description": "Which predefined bundle to execute.",
        },
        "args": {
            "type": "object",
            "description": "Shared input args for all tools in the bundle. Required keys per bundle: safety_check_base=[address], tx_full_inspect=[tx_hash], swap_prep=[token_in,token_out,amount_in], cross_chain=[token_in,token_out,amount_in,to_chain_id], agent_kyc=[wallet_or_did].",
        },
        "stop_on_error": {
            "type": "boolean",
            "default": True,
            "description": "If true, halts on first tool error and returns partial results. If false, continues all tools.",
        },
    },
    "required": ["bundle", "args"],
}


def run(bundle: str, args: dict, stop_on_error: bool = True, **_: object) -> dict:
    if bundle not in _BUNDLES:
        return {
            "ok": False,
            "error": f"unknown_bundle: {bundle}",
            "available": list(_BUNDLES.keys()),
        }
    spec = _BUNDLES[bundle]
    if not isinstance(args, dict):
        return {"ok": False, "error": "args must be an object"}
    missing = [k for k in spec["input_keys_required"] if k not in args]
    if missing:
        return {"ok": False, "error": f"missing required args: {missing}", "needed": spec["input_keys_required"]}

    # Dynamic dispatch — import each tool's run() and execute in sequence
    import importlib
    results: list[dict] = []
    failed_at = None
    for tool_name in spec["tools"]:
        modname = "tools_pkg." + tool_name.replace("onyx_", "")
        # tools_pkg modules are not named with the onyx_ prefix; map back
        # to module filename heuristically
        candidates = [
            modname,
            "tools_pkg." + tool_name.removeprefix("onyx_"),
            "tools_pkg." + tool_name,
        ]
        mod = None
        last_err = ""
        for c in candidates:
            try:
                mod = importlib.import_module(c)
                break
            except ImportError as e:
                last_err = str(e)
                continue
        if mod is None:
            results.append({
                "tool": tool_name,
                "ok": False,
                "error": f"tool_not_loadable: {last_err[:120]}",
            })
            failed_at = tool_name
            if stop_on_error:
                break
            continue

        # Tool-specific arg mapping (each tool takes different shape)
        try:
            if tool_name == "onyx_base_contract_verify":
                out = mod.run(address=args.get("address"))
            elif tool_name == "onyx_base_token_risk_scan":
                addr = args.get("address") or args.get("token_address") or args.get("token_in") or args.get("token_out")
                # token_risk_scan expects positional arg `address` (per its signature)
                out = mod.run(address=addr)
            elif tool_name == "onyx_agent_audit_trail":
                out = mod.run(wallet=args.get("address") or args.get("wallet") or args.get("wallet_or_did", ""))
            elif tool_name == "onyx_base_tx_explainer" or tool_name == "onyx_base_tx_simulator" or tool_name == "onyx_base_tx_decode":
                out = mod.run(tx_hash=args.get("tx_hash"))
            elif tool_name == "onyx_base_dex_pair_lookup":
                out = mod.run(token_address=args.get("token_out") or args.get("token_in"))
            elif tool_name == "onyx_base_swap_quote":
                out = mod.run(token_in=args.get("token_in"), token_out=args.get("token_out"), amount_in=args.get("amount_in"))
            elif tool_name == "onyx_base_bridge_quote":
                out = mod.run(
                    to_chain_id=args.get("to_chain_id"),
                    from_token=args.get("token_in"),
                    to_token=args.get("token_out"),
                    from_amount=args.get("amount_in"),
                )
            elif tool_name == "onyx_x402_chain_picker":
                out = mod.run()
            elif tool_name == "onyx_agent_id":
                out = mod.run(wallet=args.get("wallet_or_did", "").lstrip("did:eth:"))
            elif tool_name == "onyx_kya_verify":
                cred = args.get("kya_credential_id") or args.get("wallet_or_did", "")
                if cred.startswith("did:") or cred.startswith("0x"):
                    out = {"ok": False, "error": "kya_verify needs a kya_credential_id, not a DID/wallet — bundle skip"}
                else:
                    out = mod.run(credential_id=cred)
            elif tool_name == "onyx_oai_lookup":
                out = mod.run(identity=args.get("wallet_or_did"))
            else:
                out = mod.run(**args)
            results.append({"tool": tool_name, "ok": True, "result": out})
        except Exception as e:
            results.append({
                "tool": tool_name,
                "ok": False,
                "error": f"{type(e).__name__}: {str(e)[:200]}",
            })
            failed_at = tool_name
            if stop_on_error:
                break

    n_ok = sum(1 for r in results if r.get("ok"))
    full_price = spec["individual_price_total_usdc"]
    bundle_price = float(PRICE_USDC)
    savings = full_price - bundle_price
    return {
        "ok": failed_at is None,
        "bundle": bundle,
        "description": spec["description"],
        "tools_executed": len(results),
        "tools_ok": n_ok,
        "failed_at": failed_at,
        "individual_price_usdc": round(full_price, 6),
        "bundle_price_usdc": bundle_price,
        "savings_usdc": round(savings, 6),
        "savings_pct": round(100 * savings / full_price, 1) if full_price > 0 else 0,
        "results": results,
    }


run.__when_to_use__ = (
    "Agents executing a known multi-step workflow on Onyx. Saves x402 "
    "settlement overhead + gets atomic delivery + single AR-1 receipt."
)
run.__vs_alternatives__ = (
    "Calling each tool separately = N x402 settlements + N receipts + N "
    "round trips. Bundle = 1 of each, discounted, atomic."
)
run.__example_request__ = {
    "bundle": "safety_check_base",
    "args": {"address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"},
}
