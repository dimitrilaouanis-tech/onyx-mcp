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

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from x402 import FacilitatorConfig, x402ResourceServer
from x402.http.facilitator_client import HTTPFacilitatorClient
from x402.http.middleware.fastapi import payment_middleware
from x402.mechanisms.evm.exact import register_exact_evm_server

from tools import solve_captcha, sms_verify

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


class SmsVerifyBody(BaseModel):
    phone_number: str
    service: Optional[str] = "generic"
    timeout_sec: Optional[int] = 60


TOOLS = [
    {
        "name": "onyx_solve_captcha",
        "path": "/v1/solve_captcha",
        "method": "POST",
        "price_usdc": "0.003",
        "description": "Solve an image-based text captcha. OCR via ddddocr, 70-90% accuracy, ~30ms.",
        "input": {"image_url | image_b64": "string"},
    },
    {
        "name": "onyx_sms_verify",
        "path": "/v1/sms_verify",
        "method": "POST",
        "price_usdc": "0.050",
        "description": "Receive an SMS OTP on a physical carrier SIM. Real phone, real tower, no VoIP.",
        "input": {"phone_number": "string", "service": "string (optional)"},
    },
]


def _manifest() -> dict:
    return {
        "service": "onyx-actions",
        "version": "0.2.0",
        "pitch": "Paid agent tools. Physical SIMs. No API keys. x402 USDC per call.",
        "network": NETWORK_ENV,
        "receive_wallet": RECEIVE_ADDR,
        "facilitator": FACILITATOR_URL,
        "tools": TOOLS,
        "docs": "https://github.com/dimitrilaouanis-tech/onyx-mcp",
        "x402": "https://x402.org",
    }


def _landing_html() -> str:
    rows = "\n".join(
        f'''      <tr>
        <td><code>{t["name"]}</code></td>
        <td class="price">${t["price_usdc"]} USDC</td>
        <td>{t["description"]}</td>
        <td><code>{t["method"]} {t["path"]}</code></td>
      </tr>'''
        for t in TOOLS
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Onyx Actions — Paid Tools for AI Agents</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ font: 15px/1.55 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
         background:#0a0a0a; color:#ddd; margin:0; padding:48px 24px; max-width:880px; margin:0 auto; }}
  h1 {{ color:#fff; font-size:28px; margin:0 0 8px; letter-spacing:-.02em; }}
  h2 {{ color:#fff; font-size:16px; margin:40px 0 12px; border-bottom:1px solid #222; padding-bottom:8px; }}
  .tag {{ display:inline-block; padding:2px 8px; border:1px solid #444; border-radius:3px; color:#aaa; font-size:12px; margin-right:6px; }}
  .pitch {{ color:#888; margin:0 0 28px; font-size:16px; }}
  table {{ width:100%; border-collapse:collapse; font-size:14px; }}
  th,td {{ text-align:left; padding:10px 12px; border-bottom:1px solid #222; vertical-align:top; }}
  th {{ color:#888; font-weight:normal; font-size:12px; text-transform:uppercase; letter-spacing:.08em; }}
  code {{ background:#161616; padding:2px 6px; border-radius:3px; color:#7ee787; font-size:13px; }}
  .price {{ color:#ffd166; white-space:nowrap; }}
  pre {{ background:#111; border:1px solid #222; padding:14px; border-radius:4px; overflow:auto; font-size:13px; color:#ccc; }}
  a {{ color:#79c0ff; }}
  .wallet {{ color:#888; font-size:12px; word-break:break-all; }}
</style>
</head>
<body>

<h1>Onyx Actions</h1>
<p class="pitch">Paid tools for AI agents. Real physical SIMs. No API keys, no accounts, no subscriptions. HTTP 402 → sign USDC transfer → 200. That's the whole auth flow.</p>

<span class="tag">x402</span>
<span class="tag">{NETWORK_ENV}</span>
<span class="tag">USDC on Base</span>
<span class="tag">MCP-compatible</span>

<h2>Tools</h2>
<table>
<thead><tr><th>Name</th><th>Price</th><th>Description</th><th>Endpoint</th></tr></thead>
<tbody>
{rows}
</tbody>
</table>

<h2>How an agent calls this</h2>
<pre>curl -X POST https://onyx-actions.onrender.com/v1/sms_verify \\
     -H "content-type: application/json" \\
     -d '{{"phone_number":"+55 11 98765 4321"}}'

# → HTTP 402 Payment Required with accepts[] describing the price.
# Your agent signs an x402 EIP-3009 authorization with its wallet, retries,
# and receives the OTP. One loop. Any x402-aware SDK handles it in ~5 lines.</pre>

<h2>For humans</h2>
<p>Clone the free stdio version and run it locally (no payment):</p>
<pre>git clone https://github.com/dimitrilaouanis-tech/onyx-mcp
cd onyx-mcp &amp;&amp; pip install -r requirements.txt
python server.py  # stdio MCP — wire into Claude Desktop / Cursor / Cline</pre>

<h2>Settlement</h2>
<p class="wallet">Receive wallet: <code>{RECEIVE_ADDR}</code><br>
Facilitator: <code>{FACILITATOR_URL}</code><br>
Network: <code>{NETWORK_ENV}</code></p>

<h2>Machine-readable manifest</h2>
<p>Agents that prefer JSON: <code>curl -H "accept: application/json" /</code> returns the same info as a manifest. <a href="/manifest">/manifest</a> also works.</p>

</body>
</html>"""


@app.get("/")
async def root(request: Request):
    accept = request.headers.get("accept", "")
    if "text/html" in accept and "application/json" not in accept:
        return HTMLResponse(_landing_html())
    return JSONResponse(_manifest())


@app.get("/manifest")
async def manifest():
    return _manifest()


@app.get("/health")
async def health():
    return {"ok": True, "network": NETWORK_ENV, "receive": RECEIVE_ADDR,
            "tools": [t["name"] for t in TOOLS]}


@app.post("/v1/solve_captcha")
async def solve_captcha_endpoint(body: SolveCaptchaBody):
    if not body.image_url and not body.image_b64:
        raise HTTPException(400, "provide image_url or image_b64")
    return solve_captcha(image_url=body.image_url, image_b64=body.image_b64)


@app.post("/v1/sms_verify")
async def sms_verify_endpoint(body: SmsVerifyBody):
    return sms_verify(phone_number=body.phone_number,
                      service=body.service or "generic",
                      timeout_sec=body.timeout_sec or 60)


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
    },
    "POST /v1/sms_verify": {
        "accepts": {
            "scheme": "exact",
            "network": NETWORK,
            "price": "$0.05",
            "payTo": RECEIVE_ADDR,
            "description": "SMS OTP via physical carrier SIM.",
            "mimeType": "application/json",
        }
    },
}


@app.middleware("http")
async def x402_gate(request, call_next):
    return await payment_middleware(ROUTES, _x402_server)(request, call_next)
