"""Agent demo — a simulated AI agent visits Onyx Actions, discovers tools, and pays for an SMS verification.

Flow:
  1. DISCOVER — GET / with Accept: application/json. Agent sees the manifest
     (service name, tool list, prices, wallet, network).
  2. REGISTER — nothing to do. No signup, no API key. Wallet IS the identity.
  3. PAY + CALL — POST /v1/sms_verify → 402 → x402 client signs USDC transfer
     authorization → retry → 200 with the OTP.

Costs $0 on base-sepolia (testnet USDC). Flip ONYX_NETWORK=base for mainnet.

Prereq:
    uvicorn server_http:app --host 127.0.0.1 --port 8080
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import httpx
from eth_account import Account
from eth_account.messages import encode_typed_data

from x402 import x402ClientConfig, SchemeRegistration
from x402.http.clients.httpx import wrapHttpxWithPaymentFromConfig
from x402.mechanisms.evm.exact import ExactEvmScheme
from x402.mechanisms.evm.exact.client import ClientEvmSigner


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
PHONE_NUMBER = os.environ.get("ONYX_DEMO_PHONE", "+55 11 98765 4321")


class EthAccountSigner(ClientEvmSigner):
    def __init__(self, privkey: str):
        self._acct = Account.from_key(privkey)

    @property
    def address(self) -> str:
        return self._acct.address

    def sign_typed_data(self, domain, types, primary_type, message) -> bytes:
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
        signable = encode_typed_data(full_message={
            "domain": domain_dict,
            "types": types_dict,
            "primaryType": primary_type,
            "message": message,
        })
        return self._acct.sign_message(signable).signature


def hr(label: str = "") -> None:
    bar = "─" * 72
    if label:
        print(f"\n{bar}\n  {label}\n{bar}")
    else:
        print(bar)


async def main():
    signer = EthAccountSigner(PRIVKEY)
    print(f"[agent] wallet : {signer.address}")
    print(f"[agent] target : {SERVER}")
    print(f"[agent] network: {NETWORK_ENV}")

    # ── 1. DISCOVER ───────────────────────────────────────────────────────
    hr("STEP 1 — DISCOVER")
    async with httpx.AsyncClient(timeout=10.0) as c:
        r = await c.get(SERVER + "/", headers={"accept": "application/json"})
    manifest = r.json()
    print(f"[agent] HTTP {r.status_code}")
    print(f"[agent] service : {manifest['service']} v{manifest['version']}")
    print(f"[agent] pitch   : {manifest['pitch']}")
    print(f"[agent] network : {manifest['network']}")
    print(f"[agent] tools:")
    for t in manifest["tools"]:
        print(f"          - {t['name']:24} ${t['price_usdc']:<7} {t['description']}")

    # ── 2. REGISTER ───────────────────────────────────────────────────────
    hr("STEP 2 — REGISTER")
    print(f"[agent] no signup. wallet = identity.")
    print(f"[agent] will pay from {signer.address}")

    # ── 3. PAY + CALL ─────────────────────────────────────────────────────
    hr("STEP 3 — PAY + CALL onyx_sms_verify")
    config = x402ClientConfig(schemes=[
        SchemeRegistration(network=NETWORK, client=ExactEvmScheme(signer=signer)),
    ])
    async with wrapHttpxWithPaymentFromConfig(config, timeout=60.0) as client:
        print(f"[agent] POST {SERVER}/v1/sms_verify  phone={PHONE_NUMBER}")
        print(f"[agent] (x402 client auto-handles the 402 and retries with payment)")
        resp = await client.post(
            f"{SERVER}/v1/sms_verify",
            json={"phone_number": PHONE_NUMBER, "service": "demo"},
        )
        print(f"[agent] HTTP {resp.status_code}")
        body = resp.json() if resp.status_code == 200 else resp.text
        print(f"[agent] body:")
        print("        " + json.dumps(body, indent=2).replace("\n", "\n        "))

        paid_header = resp.request.headers.get("X-PAYMENT") if hasattr(resp, 'request') else None
        receipt = resp.headers.get("X-PAYMENT-RESPONSE")

        hr("RESULT")
        if resp.status_code == 200 and isinstance(body, dict) and body.get("otp"):
            print(f"[✓] closed loop confirmed.")
            print(f"    agent asked for an OTP to {PHONE_NUMBER}")
            print(f"    paid in USDC on {NETWORK_ENV}")
            print(f"    received: OTP {body['otp']} (sim: {body.get('sim_carrier')}/{body.get('sim_country')})")
            if receipt:
                print(f"    settlement receipt: {receipt[:80]}...")
            if body.get("demo"):
                print(f"    (demo mode — synthetic OTP; flip ONYX_DEMO_MODE=0 for real phone)")
        else:
            print(f"[!] loop did not close. status={resp.status_code}")


if __name__ == "__main__":
    asyncio.run(main())
