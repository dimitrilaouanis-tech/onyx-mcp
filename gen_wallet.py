"""Generate a fresh EVM keypair for the Onyx x402 receiver.

No funding. No network calls. Pure local key derivation.
Writes address + privkey to .env (gitignored).
"""
import secrets
from pathlib import Path

from eth_account import Account

ENV_PATH = Path(__file__).parent / ".env"


def main():
    if ENV_PATH.exists():
        existing = ENV_PATH.read_text()
        if "ONYX_RECEIVE_ADDRESS=" in existing:
            for line in existing.splitlines():
                if line.startswith("ONYX_RECEIVE_ADDRESS="):
                    print(f"[already exists] {line}")
            print("[!] .env already has a wallet. Delete .env first to regenerate.")
            return

    priv = "0x" + secrets.token_hex(32)
    acct = Account.from_key(priv)

    env = (
        f"# Onyx x402 receive wallet (generated locally, never funded yet)\n"
        f"ONYX_RECEIVE_ADDRESS={acct.address}\n"
        f"ONYX_RECEIVE_PRIVKEY={priv}\n"
        f"# Network choices: base-sepolia (free testnet) | base (mainnet, $$$)\n"
        f"ONYX_NETWORK=base-sepolia\n"
        f"# Facilitator (verifies + settles payments). Coinbase public facilitator supports testnet free.\n"
        f"ONYX_FACILITATOR_URL=https://x402.org/facilitator\n"
    )
    ENV_PATH.write_text(env)
    print(f"[ok] wrote {ENV_PATH}")
    print(f"     address: {acct.address}")
    print(f"     network: base-sepolia (testnet, free)")


if __name__ == "__main__":
    main()
