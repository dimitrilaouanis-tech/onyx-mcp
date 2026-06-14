"""Register Onyx's own ERC-8004 identity on Base. Dry-run by default.

ERC-8004 IdentityRegistry (Base mainnet): 0x8004A169FB4a3325136EB29fA0ceB6D2e539a432
We call register(string agentURI) with our A2A AgentCard URL. It mints an
ERC-721 identity owned by the signer and points the on-chain tokenURI at the
card — so any agent that vets us via onyx_agent_reputation (or the live
registry directly) sees a real, registered identity instead of UNKNOWN.

This deliberately holds NO key. Onyx wallets are receive-only by policy. To
actually register, the wallet owner runs this with a funded key they control:

    # 1. dry-run (no key needed) — prints the exact unsigned transaction
    python register_erc8004.py

    # 2. broadcast — owner supplies a key funded with ~$0.005 of ETH on Base
    ERC8004_PRIVATE_KEY=0x...  python register_erc8004.py --broadcast

Cost is ~180k gas (well under one cent on Base). The signer becomes the owner
of the identity NFT; bind the public receive address afterward via
setAgentWallet if you want the verified-wallet field populated.
"""
import json
import os
import sys
import urllib.request

from eth_abi import encode
from eth_utils import function_signature_to_4byte_selector as selector

AGENT_URI = os.environ.get(
    "ONYX_AGENT_URI", "https://onyx-actions.onrender.com/.well-known/agent-card.json"
)
IDENTITY = "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432"
RPC = os.environ.get("BASE_RPC", "https://mainnet.base.org")
CHAIN_ID = 8453
# Used only to simulate gas in dry-run (the registry reverts on a zero-address
# sender). The real owner is whoever signs the broadcast.
SIM_FROM = os.environ.get("ONYX_RECEIVE_ADDRESS", "0x3fD9ee1373562f894D322B37DFFAd7a5D2b2d78f")


def _rpc(method, params):
    req = urllib.request.Request(
        RPC,
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "onyx-erc8004/1.0"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        body = json.load(r)
    if "error" in body:
        raise RuntimeError(body["error"])
    return body["result"]


def calldata() -> str:
    return "0x" + selector("register(string)").hex() + encode(["string"], [AGENT_URI]).hex()


def main() -> None:
    data = calldata()
    broadcast = "--broadcast" in sys.argv
    key = os.environ.get("ERC8004_PRIVATE_KEY", "").strip()

    print(f"IdentityRegistry : {IDENTITY} (Base mainnet, chainId {CHAIN_ID})")
    print(f"function         : register(string agentURI)")
    print(f"agentURI         : {AGENT_URI}")
    print(f"calldata         : {data}")

    if not (broadcast and key):
        gas = int(_rpc("eth_estimateGas", [{"from": SIM_FROM, "to": IDENTITY, "data": data}]), 16)
        price = int(_rpc("eth_gasPrice", []), 16)
        print(f"\nestimated gas    : {gas} units @ {price/1e9:.4f} gwei "
              f"= {gas*price/1e18:.8f} ETH")
        print("\nUnsigned transaction (paste into any wallet's 'send custom tx', "
              "or set ERC8004_PRIVATE_KEY and re-run with --broadcast):")
        print(json.dumps({"to": IDENTITY, "data": data, "value": "0x0",
                          "chainId": CHAIN_ID, "gas": hex(int(gas * 1.2))}, indent=2))
        if broadcast and not key:
            print("\n[--broadcast given but ERC8004_PRIVATE_KEY not set — staying dry-run]")
        return

    # broadcast path — owner-supplied funded key
    from eth_account import Account
    acct = Account.from_key(key)
    nonce = int(_rpc("eth_getTransactionCount", [acct.address, "pending"]), 16)
    gas = int(_rpc("eth_estimateGas", [{"from": acct.address, "to": IDENTITY, "data": data}]), 16)
    price = int(_rpc("eth_gasPrice", []), 16)
    tx = {"to": IDENTITY, "value": 0, "data": data, "nonce": nonce, "chainId": CHAIN_ID,
          "gas": int(gas * 1.3), "maxFeePerGas": int(price * 2), "maxPriorityFeePerGas": price}
    signed = acct.sign_transaction(tx)
    txh = _rpc("eth_sendRawTransaction", ["0x" + signed.raw_transaction.hex()
               if not signed.raw_transaction.hex().startswith("0x") else signed.raw_transaction.hex()])
    print(f"\nsigner           : {acct.address}")
    print(f"broadcast tx     : {txh}")
    print(f"track            : https://basescan.org/tx/{txh}")


if __name__ == "__main__":
    main()
