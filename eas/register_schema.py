"""Register the 0n1x merchant-fact schema on EAS SchemaRegistry (Base mainnet).

DRY-RUN by default: computes the deterministic schema UID, checks whether it is
already registered, estimates gas, and prints exactly what --send would do.
Nothing is signed or broadcast without --send AND a funded key.

    py eas/register_schema.py            # dry run (no key needed)
    py eas/register_schema.py --send     # sign + broadcast (key from env)

Key comes from env EAS_REGISTRAR_KEY (0x-hex private key) — never a file arg,
never printed. Eyes-open rule: --send is a user-approved, funded action.
"""
from __future__ import annotations

import argparse
import os
import sys

from web3 import Web3

RPC = os.environ.get("BASE_RPC", "https://mainnet.base.org")
SCHEMA_REGISTRY = "0x4200000000000000000000000000000000000020"
SCHEMA = ("string domain,string factType,string factJson,"
          "bytes32 evidenceHash,uint64 observedAt,uint16 specVersion")
RESOLVER = "0x0000000000000000000000000000000000000000"
REVOCABLE = True

ABI = [
    {"name": "register", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "schema", "type": "string"},
                {"name": "resolver", "type": "address"},
                {"name": "revocable", "type": "bool"}],
     "outputs": [{"name": "", "type": "bytes32"}]},
    {"name": "getSchema", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "uid", "type": "bytes32"}],
     "outputs": [{"name": "", "type": "tuple", "components": [
         {"name": "uid", "type": "bytes32"},
         {"name": "resolver", "type": "address"},
         {"name": "revocable", "type": "bool"},
         {"name": "schema", "type": "string"}]}]},
]


def schema_uid() -> bytes:
    # keccak256(abi.encodePacked(schema, resolver, revocable))
    return Web3.keccak(
        SCHEMA.encode() + bytes.fromhex(RESOLVER[2:]) + (b"\x01" if REVOCABLE else b"\x00"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true", help="sign + broadcast (needs EAS_REGISTRAR_KEY)")
    args = ap.parse_args()

    w3 = Web3(Web3.HTTPProvider(RPC))
    if not w3.is_connected():
        print(f"RPC unreachable: {RPC}"); return 1
    reg = w3.eth.contract(address=Web3.to_checksum_address(SCHEMA_REGISTRY), abi=ABI)

    uid = schema_uid()
    print(f"schema     : {SCHEMA}")
    print(f"schema UID : 0x{uid.hex() if not uid.hex().startswith('0x') else uid.hex()[2:]}")

    existing = reg.functions.getSchema(uid).call()
    if existing[0] != b"\x00" * 32:
        print("ALREADY REGISTERED on Base — nothing to do. Attest away.")
        return 0
    print("not yet registered on Base.")

    fn = reg.functions.register(SCHEMA, Web3.to_checksum_address(RESOLVER), REVOCABLE)
    gas = fn.estimate_gas({"from": "0x" + "11" * 20})
    gas_price = w3.eth.gas_price
    cost_eth = gas * gas_price / 1e18
    print(f"est. gas   : {gas} @ {gas_price/1e9:.4f} gwei  ~= {cost_eth:.8f} ETH on Base")

    if not args.send:
        print("\nDRY RUN — to register: fund the registrar wallet with a little Base ETH,")
        print("set EAS_REGISTRAR_KEY, then re-run with --send  (user go required).")
        return 0

    key = os.environ.get("EAS_REGISTRAR_KEY", "")
    if not key:
        print("EAS_REGISTRAR_KEY not set — refusing."); return 1
    acct = w3.eth.account.from_key(key)
    bal = w3.eth.get_balance(acct.address)
    print(f"registrar  : {acct.address}  balance {bal/1e18:.8f} ETH")
    if bal < gas * gas_price * 2:
        print("insufficient Base ETH for gas — fund first."); return 1

    tx = fn.build_transaction({
        "from": acct.address,
        "nonce": w3.eth.get_transaction_count(acct.address),
        "gas": int(gas * 1.3),
        "maxFeePerGas": int(gas_price * 2),
        "maxPriorityFeePerGas": w3.eth.max_priority_fee,
        "chainId": 8453,
    })
    signed = acct.sign_transaction(tx)
    txh = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"sent: 0x{txh.hex().lstrip('0x')}")
    rcpt = w3.eth.wait_for_transaction_receipt(txh, timeout=180)
    print(f"status={rcpt.status} block={rcpt.blockNumber}")
    print(f"schema page: https://base.easscan.org/schema/view/0x{uid.hex().lstrip('0x')}")
    return 0 if rcpt.status == 1 else 1


if __name__ == "__main__":
    sys.exit(main())
