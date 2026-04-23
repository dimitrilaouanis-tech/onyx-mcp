"""Onyx x402-gated HTTP endpoint for solve_captcha.

Returns HTTP 402 Payment Required until the caller supplies a valid
x402 payment header. Uses Coinbase's public facilitator on Base Sepolia
testnet (free) so self-test costs $0.

To switch to mainnet: edit .env → ONYX_NETWORK=base, add funded wallet.

Run:
    uvicorn server_http:app --host 0.0.0.0 --port 8080
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from x402 import FacilitatorConfig, x402ResourceServer
from x402.http.facilitator_client import HTTPFacilitatorClient
from x402.http.middleware.fastapi import payment_middleware
from x402.mechanisms.evm.exact import register_exact_evm_server

from tools import solve_captcha

# ----- env ---------------------------------------------------------------

env_file = os.environ.get("ONYX_ENV_FILE", ".env")
env_path = Path(__file__).parent / env_file
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

RECEIVE_ADDR = os.environ.get("ONYX_RECEIVE_ADDRESS")
NETWORK_ENV = os.environ.get("ONYX_NETWORK", "base-sepolia").lower()
FACILITATOR_URL = os.environ.get(
    "ONYX_FACILITATOR_URL", "https://x402.org/facilitator"
)

if not RECEIVE_ADDR:
    raise RuntimeError("ONYX_RECEIVE_ADDRESS missing — run gen_wallet.py first")

# Map friendly names → CAIP-2 ids
NETWORK_CAIP = {
    "base": "eip155:8453",
    "base-sepolia": "eip155:84532",
}
NETWORK = NETWORK_CAIP.get(NETWORK_ENV, NETWORK_ENV)

# ----- x402 resource server ---------------------------------------------

_facilitator = HTTPFacilitatorClient(FacilitatorConfig(url=FACILITATOR_URL))
_x402_server = x402ResourceServer(facilitator_clients=_facilitator)
register_exact_evm_server(_x402_server)

# ----- FastAPI -----------------------------------------------------------

app = FastAPI(title="Onyx Actions", version="0.1.0")


class SolveCaptchaBody(BaseModel):
    image_url: Optional[str] = None
    image_b64: Optional[str] = None


@app.get("/")
async def root():
    return {
        "service": "onyx-actions",
        "version": "0.1.0",
        "network": NETWORK_ENV,
        "receive": RECEIVE_ADDR,
        "tools": [
            {
                "name": "solve_captcha",
                "path": "POST /v1/solve_captcha",
                "price": "$0.003 USDC",
                "description": "Solve image captcha, returns text answer.",
            }
        ],
        "docs": "https://github.com/onyx/agent-actions",
    }


@app.get("/health")
async def health():
    return {"ok": True, "network": NETWORK_ENV, "receive": RECEIVE_ADDR}


@app.post("/v1/solve_captcha")
async def solve_captcha_endpoint(body: SolveCaptchaBody):
    if not body.image_url and not body.image_b64:
        raise HTTPException(400, "provide image_url or image_b64")
    return solve_captcha(image_url=body.image_url, image_b64=body.image_b64)


# ----- x402 payment middleware ------------------------------------------

ROUTES = {
    "POST /v1/solve_captcha": {
        "accepts": {
            "scheme": "exact",
            "network": NETWORK,
            "price": "$0.003",
            "payTo": RECEIVE_ADDR,
            "description": "Solve image captcha, returns text answer.",
            "mimeType": "application/json",
        }
    }
}


@app.middleware("http")
async def x402_gate(request, call_next):
    return await payment_middleware(ROUTES, _x402_server)(request, call_next)
