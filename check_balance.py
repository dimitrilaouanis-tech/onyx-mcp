"""Check our wallet's testnet USDC balance on base-sepolia.

Free. Uses public base-sepolia RPC. No API key, no spend.
"""
from __future__ import annotations

import os
from pathlib import Path

from web3 import Web3

env_file = os.environ.get("ONYX_ENV_FILE", ".env")
env_path = Path(__file__).parent / env_file
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

ADDR = os.environ["ONYX_RECEIVE_ADDRESS"]
NETWORK = os.environ.get("ONYX_NETWORK", "base-sepolia").lower()

# base-sepolia public RPC + USDC testnet contract
CONFIG = {
    "base-sepolia": {
        "rpc": "https://sepolia.base.org",
        "usdc": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        "explorer": "https://sepolia.basescan.org/address/",
    },
    "base": {
        "rpc": "https://mainnet.base.org",
        "usdc": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "explorer": "https://basescan.org/address/",
    },
}[NETWORK]

ERC20_ABI = [
    {"constant": True, "inputs": [{"name": "owner", "type": "address"}],
     "name": "balanceOf", "outputs": [{"name": "", "type": "uint256"}],
     "type": "function"},
    {"constant": True, "inputs": [], "name": "decimals",
     "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
]


def main():
    w3 = Web3(Web3.HTTPProvider(CONFIG["rpc"]))
    usdc = w3.eth.contract(
        address=Web3.to_checksum_address(CONFIG["usdc"]),
        abi=ERC20_ABI,
    )
    addr = Web3.to_checksum_address(ADDR)
    raw = usdc.functions.balanceOf(addr).call()
    dec = usdc.functions.decimals().call()
    eth = w3.eth.get_balance(addr)

    print(f"wallet     : {addr}")
    print(f"network    : {NETWORK}")
    print(f"ETH balance: {Web3.from_wei(eth, 'ether'):.6f} ETH")
    print(f"USDC       : {raw / 10**dec:.6f} USDC  (raw={raw})")
    print(f"explorer   : {CONFIG['explorer']}{addr}")
    if raw == 0:
        print()
        print("[!] wallet has 0 USDC. Claim from faucet:")
        if NETWORK == "base-sepolia":
            print("    https://faucet.circle.com/   (pick Base Sepolia, paste address)")
        else:
            print("    Buy USDC on Coinbase and send to this address.")


if __name__ == "__main__":
    main()
