"""Client-side demo — what an x402-aware AI agent does to call Onyx Actions.

Run any of:
    python agent_pay.py                                        # 402-only diagnostic
    python agent_pay.py onyx_solana_jupiter_quote              # specific tool
    ONYX_DEMO_KEY=0x... python agent_pay.py                    # signs + retries

Output:
    [STEP 1]  Calls tool with empty body
    [STEP 2]  Server responds 402 + payment-required header (base64 JSON)
    [STEP 3]  Decodes the challenge: payTo, amount, asset, network, inputSchema
    [STEP 4]  If ONYX_DEMO_KEY set: signs EIP-3009 USDC authorization, retries
              with PAYMENT-SIGNATURE header. Server settles via facilitator and returns
              the tool result.

No dependencies you don't already have for any x402 client:
    pip install httpx eth-account

This is the exact loop every paid x402-aware agent runs. Drop into Cloudflare
Agents SDK, Coinbase AgentKit, Privy, mcp-use, or any custom client.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time

import httpx

SERVER = os.environ.get("ONYX_SERVER", "https://onyx-actions.onrender.com")
TOOL = sys.argv[1] if len(sys.argv) > 1 else "onyx_solana_jupiter_quote"

# Per-tool example bodies. Add your own — every Onyx tool's input_schema is in
# the 402 challenge under accepts[0].extra.inputSchema.
EXAMPLE_BODIES: dict[str, dict] = {
    "onyx_solana_jupiter_quote": {
        "input_mint": "So11111111111111111111111111111111111111112",
        "output_mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "amount": "1000000000",
    },
    "onyx_solana_token_metadata": {"mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"},
    "onyx_solana_token_risk_scan": {"mint": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"},
    "onyx_solana_tx_explainer": {"signature": "5j7s4abcd" + "x" * 80},
    "onyx_base_token_risk_scan": {"address": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"},
    "onyx_token_metadata": {"address": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"},
    "onyx_url_text": {"url": "https://en.wikipedia.org/wiki/Model_Context_Protocol", "max_chars": 2000},
    "onyx_dns_lookup": {"host": "vitalik.eth"},
}


def step(n: int, msg: str) -> None:
    print(f"\n[STEP {n}] {msg}")


def main() -> int:
    url = f"{SERVER}/v1/{TOOL}"
    body = EXAMPLE_BODIES.get(TOOL, {})

    step(1, f"POST {url}")
    print(f"          body: {json.dumps(body)}")
    r = httpx.post(url, json=body, timeout=20)
    print(f"          -> HTTP {r.status_code}")

    if r.status_code != 402:
        print(f"\nUnexpected status. Body:\n{r.text[:400]}")
        return 1

    challenge_b64 = r.headers.get("payment-required") or r.headers.get("X-Payment-Required")
    if not challenge_b64:
        print("\nServer returned 402 but no payment-required header.")
        print(f"Body: {r.text[:400]}")
        return 1

    step(2, "Decoding the payment-required challenge")
    challenge = json.loads(base64.b64decode(challenge_b64))
    accept = challenge["accepts"][0]
    print(f"          x402 version:    {challenge.get('x402Version')}")
    print(f"          resource:        {challenge.get('resource', {}).get('url')}")
    print(f"          scheme:          {accept.get('scheme')}")
    print(f"          network:         {accept.get('network')}")
    print(f"          asset (USDC):    {accept.get('asset')}")
    amt_atomic = int(accept.get("amount", "0"))
    print(f"          amount:          {amt_atomic} ({amt_atomic / 1e6:.6f} USDC)")
    print(f"          payTo:           {accept.get('payTo')}")
    print(f"          maxTimeoutSec:   {accept.get('maxTimeoutSeconds')}")
    schema = accept.get("extra", {}).get("inputSchema", {})
    print(f"          inputSchema:     required={schema.get('required')} props={list((schema.get('properties') or {}).keys())}")

    step(3, "Building EIP-3009 transferWithAuthorization typed-data payload")
    valid_after = 0
    valid_before = int(time.time()) + accept.get("maxTimeoutSeconds", 300)
    nonce = "0x" + os.urandom(32).hex()

    typed_data = {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            "TransferWithAuthorization": [
                {"name": "from", "type": "address"},
                {"name": "to", "type": "address"},
                {"name": "value", "type": "uint256"},
                {"name": "validAfter", "type": "uint256"},
                {"name": "validBefore", "type": "uint256"},
                {"name": "nonce", "type": "bytes32"},
            ],
        },
        "primaryType": "TransferWithAuthorization",
        "domain": {
            "name": "USD Coin",
            "version": accept.get("extra", {}).get("version", "2"),
            "chainId": int(accept["network"].split(":")[1]) if ":" in accept["network"] else 8453,
            "verifyingContract": accept["asset"],
        },
        "message": {
            "from": "0x0000000000000000000000000000000000000000",  # filled below
            "to": accept["payTo"],
            "value": amt_atomic,
            "validAfter": valid_after,
            "validBefore": valid_before,
            "nonce": nonce,
        },
    }
    print(f"          chainId:         {typed_data['domain']['chainId']}")
    print(f"          validBefore:     {valid_before} ({accept.get('maxTimeoutSeconds')}s window)")
    print(f"          nonce:           {nonce[:18]}...")

    demo_key = os.environ.get("ONYX_DEMO_KEY", "").strip()
    if not demo_key:
        print("\n[STEP 4] Skipped — set ONYX_DEMO_KEY=0x... to a wallet with sepolia/mainnet")
        print("          USDC + matching network and re-run to actually pay + get the result.")
        print("\nThis 402 challenge is everything an x402-aware agent needs to settle the call.")
        return 0

    try:
        from eth_account import Account
        from eth_account.messages import encode_typed_data
    except ImportError:
        print("\nMissing eth-account. Install with: pip install eth-account")
        return 1

    acct = Account.from_key(demo_key)
    typed_data["message"]["from"] = acct.address
    print(f"\n[STEP 4] Signing as {acct.address}")
    signable = encode_typed_data(full_message=typed_data)
    sig = acct.sign_message(signable)

    payment_payload = {
        "x402Version": 2,
        "scheme": "exact",
        "network": accept["network"],
        "payload": {
            "signature": sig.signature.hex(),
            "authorization": {
                "from": acct.address,
                "to": accept["payTo"],
                "value": str(amt_atomic),
                "validAfter": str(valid_after),
                "validBefore": str(valid_before),
                "nonce": nonce,
            },
        },
    }
    payment_header = base64.b64encode(json.dumps(payment_payload).encode()).decode()

    print("[STEP 5] Retrying with PAYMENT-SIGNATURE header...")
    r2 = httpx.post(url, json=body, timeout=30, headers={"PAYMENT-SIGNATURE": payment_header})
    print(f"          -> HTTP {r2.status_code}")
    settle = r2.headers.get("x-payment-response")
    if settle:
        print(f"          x-payment-response: {settle[:100]}...")
    print("\n[RESULT]")
    try:
        print(json.dumps(r2.json(), indent=2)[:2000])
    except Exception:
        print(r2.text[:2000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
