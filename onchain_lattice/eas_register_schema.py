"""Register the 0n1x trust-score + merchant-fact schemas on EAS (Base mainnet).

STAGED — broadcast requires ONYX_CHAIN_KEY in env (never in a file) and a
funded gas wallet (~$0.50 total). Run with --dry-run first (default).

EAS on Base is a predeploy:
  SchemaRegistry: 0x4200000000000000000000000000000000000020
  EAS:            0x4200000000000000000000000000000000000021
Schemas are permissionless + tokenless; cost = gas only.
Explorer: https://base.easscan.org/schemas
"""
import os
import sys

SCHEMA_REGISTRY = "0x4200000000000000000000000000000000000020"
RPC = os.environ.get("BASE_RPC", "https://mainnet.base.org")

# schema 1: agent trust score (mirrors 0n1x/trust-score/v1)
TRUST_SCORE_SCHEMA = (
    "address agent,uint8 score,string lane,string standing,"
    "uint64 observedAt,string evidenceURI"
)
# schema 2: merchant/counterparty reality fact (signed FACT, never judgment)
MERCHANT_FACT_SCHEMA = (
    "string subject,string factType,string value,string method,"
    "uint64 observedAt,string sourceURI"
)

ABI = [{
    "name": "register", "type": "function", "stateMutability": "nonpayable",
    "inputs": [
        {"name": "schema", "type": "string"},
        {"name": "resolver", "type": "address"},
        {"name": "revocable", "type": "bool"},
    ],
    "outputs": [{"name": "", "type": "bytes32"}],
}]


def main():
    dry = "--broadcast" not in sys.argv
    from web3 import Web3
    w3 = Web3(Web3.HTTPProvider(RPC))
    print("chain:", w3.eth.chain_id, "| block:", w3.eth.block_number)
    reg = w3.eth.contract(address=SCHEMA_REGISTRY, abi=ABI)
    key = os.environ.get("ONYX_CHAIN_KEY")
    if dry or not key:
        print("[DRY RUN] would register (revocable=True, no resolver):")
        print("  trust-score :", TRUST_SCORE_SCHEMA)
        print("  merchant-fact:", MERCHANT_FACT_SCHEMA)
        if not key:
            print("set ONYX_CHAIN_KEY + pass --broadcast to go live")
        return
    acct = w3.eth.account.from_key(key)
    for label, schema in (("trust-score", TRUST_SCORE_SCHEMA),
                          ("merchant-fact", MERCHANT_FACT_SCHEMA)):
        tx = reg.functions.register(schema, "0x" + "0" * 40, True).build_transaction({
            "from": acct.address,
            "nonce": w3.eth.get_transaction_count(acct.address),
            "maxFeePerGas": w3.eth.gas_price * 2,
            "maxPriorityFeePerGas": w3.to_wei(0.001, "gwei"),
        })
        signed = acct.sign_transaction(tx)
        h = w3.eth.send_raw_transaction(signed.raw_transaction)
        rcpt = w3.eth.wait_for_transaction_receipt(h)
        print(f"{label}: tx {h.hex()} | status {rcpt.status} | "
              f"schema UID in logs -> https://base.easscan.org/schema/view/<uid>")


if __name__ == "__main__":
    main()
