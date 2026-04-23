"""Self-pay test — pay the Onyx x402 tollbooth using our own wallet.

Runs the full loop: call /v1/solve_captcha → get 402 → sign EIP-3009 payment
authorization → retry with X-PAYMENT header → get 200 + captcha answer.

Costs $0 on base-sepolia (testnet USDC, claimed from a free faucet).

Prereqs:
    1. uvicorn server_http:app --host 127.0.0.1 --port 8080
    2. Wallet funded with base-sepolia USDC (faucet: https://faucet.circle.com/)
"""
from __future__ import annotations

import asyncio
import base64
import os
from pathlib import Path

from eth_account import Account
from eth_account.messages import encode_typed_data

from x402 import x402ClientConfig, SchemeRegistration
from x402.http.clients.httpx import wrapHttpxWithPaymentFromConfig
from x402.mechanisms.evm.exact import ExactEvmScheme
from x402.mechanisms.evm.exact.client import ClientEvmSigner


# ----- env ---------------------------------------------------------------

env_file = os.environ.get("ONYX_ENV_FILE", ".env")
env_path = Path(__file__).parent / env_file
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

PRIVKEY = os.environ["ONYX_RECEIVE_PRIVKEY"]
NETWORK_ENV = os.environ.get("ONYX_NETWORK", "base-sepolia").lower()
NETWORK_CAIP = {"base": "eip155:8453", "base-sepolia": "eip155:84532"}
NETWORK = NETWORK_CAIP.get(NETWORK_ENV, NETWORK_ENV)

SERVER = os.environ.get("ONYX_SERVER_URL", "http://127.0.0.1:8080")


# ----- signer adapter ----------------------------------------------------

class EthAccountSigner(ClientEvmSigner):
    """Adapts eth_account.LocalAccount to the x402 ClientEvmSigner protocol."""

    def __init__(self, privkey: str):
        self._acct = Account.from_key(privkey)

    @property
    def address(self) -> str:
        return self._acct.address

    def sign_typed_data(self, domain, types, primary_type, message) -> bytes:
        # x402 passes a TypedDataDomain dataclass + TypedDataField list-of-lists.
        # eth_account.encode_typed_data wants plain dicts with camelCase keys.
        domain_dict = {
            "name": domain.name,
            "version": domain.version,
            "chainId": domain.chain_id,
            "verifyingContract": domain.verifying_contract,
        }
        types_dict = {
            name: [{"name": f.name, "type": f.type} for f in fields]
            for name, fields in types.items()
        }
        full = {
            "domain": domain_dict,
            "types": types_dict,
            "primaryType": primary_type,
            "message": message,
        }
        signable = encode_typed_data(full_message=full)
        sig = self._acct.sign_message(signable)
        return sig.signature  # already bytes


# ----- run ---------------------------------------------------------------

async def main():
    signer = EthAccountSigner(PRIVKEY)
    print(f"[*] payer address  : {signer.address}")
    print(f"[*] network        : {NETWORK} ({NETWORK_ENV})")
    print(f"[*] server         : {SERVER}")

    config = x402ClientConfig(
        schemes=[
            SchemeRegistration(
                network=NETWORK,
                client=ExactEvmScheme(signer=signer),
            ),
        ],
    )

    # use a real captcha image so the OCR returns something meaningful
    img_path = Path(r"C:\Users\intelligence\assemble_debug\xc_target_crop.png")
    tiny_png = base64.b64encode(img_path.read_bytes()).decode()

    async with wrapHttpxWithPaymentFromConfig(config, timeout=60.0) as client:
        print("\n[*] POST /v1/solve_captcha (x402 client auto-handles 402)...")
        try:
            resp = await client.post(
                f"{SERVER}/v1/solve_captcha",
                json={"image_b64": tiny_png},
            )
            print(f"[+] HTTP {resp.status_code}")
            print(f"[+] body : {resp.text[:500]}")
            if resp.status_code == 200:
                print("\n*** SELF-PAY ROUNDTRIP WORKS — first cent earned (testnet) ***")
        except Exception as e:
            print(f"[!] error: {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
