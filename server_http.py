"""Onyx Actions — paid MCP over x402.

Surfaces the same tool registry over three transports:
  1. /mcp          — Streamable HTTP MCP (JSON-RPC, what Smithery/Cursor/Cline install)
  2. /v1/<tool>    — REST fallback (POST JSON, x402-gated, for non-MCP agents)
  3. /             — HTML landing + JSON manifest (content-negotiated)

Tools are auto-discovered from tools_pkg/. Drop a new file in there to add a tool.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

import mcp.types as mcp_types
from mcp.server import Server as MCPServer
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

from x402 import FacilitatorConfig, x402ResourceServer
from x402.http.facilitator_client import HTTPFacilitatorClient
from x402.http.middleware.fastapi import payment_middleware
from x402.mechanisms.evm.exact import register_exact_evm_server

import tools_pkg

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

NETWORK_CAIP = {"base": "eip155:8453", "base-sepolia": "eip155:84532"}
NETWORK = NETWORK_CAIP.get(NETWORK_ENV, NETWORK_ENV)

# ----- tool registry -----------------------------------------------------

TOOLS = tools_pkg.discover()
TOOLS_BY_NAME = {t.NAME: t for t in TOOLS}
MANIFEST_TOOLS = tools_pkg.manifest(TOOLS)

# ----- x402 resource server ---------------------------------------------

_facilitator = HTTPFacilitatorClient(FacilitatorConfig(url=FACILITATOR_URL))
_x402_server = x402ResourceServer(facilitator_clients=_facilitator)
register_exact_evm_server(_x402_server)

# ----- MCP server (Streamable HTTP) -------------------------------------

mcp_server: MCPServer = MCPServer("onyx-actions")


@mcp_server.list_tools()
async def _mcp_list_tools() -> list[mcp_types.Tool]:
    return [
        mcp_types.Tool(
            name=t.NAME,
            description=f"{t.DESCRIPTION} (price: ${t.PRICE_USDC} USDC, tier: {t.TIER})",
            inputSchema=t.INPUT_SCHEMA,
        )
        for t in TOOLS
    ]


@mcp_server.call_tool()
async def _mcp_call_tool(name: str, arguments: dict) -> list[mcp_types.TextContent]:
    tool = TOOLS_BY_NAME.get(name)
    if tool is None:
        raise ValueError(f"Unknown tool: {name}")
    result = await asyncio.to_thread(tool.run, **(arguments or {}))
    return [mcp_types.TextContent(type="text", text=json.dumps(result))]


_mcp_session = StreamableHTTPSessionManager(
    app=mcp_server,
    json_response=False,
    stateless=True,
)

# ----- FastAPI -----------------------------------------------------------


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    async with _mcp_session.run():
        yield


app = FastAPI(title="Onyx Actions", version="0.2.0", lifespan=lifespan)


def _manifest() -> dict:
    return {
        "service": "onyx-actions",
        "version": "0.2.0",
        "pitch": "Paid agent tools. x402 USDC per call. No API keys.",
        "network": NETWORK_ENV,
        "receive_wallet": RECEIVE_ADDR,
        "facilitator": FACILITATOR_URL,
        "mcp_endpoint": "/mcp",
        "tools": MANIFEST_TOOLS,
        "docs": "https://github.com/dimitrilaouanis-tech/onyx-mcp",
        "x402": "https://x402.org",
    }


def _landing_html() -> str:
    rows = "\n".join(
        f"      <tr><td><code>{t['name']}</code></td>"
        f"<td class='price'>${t['price_usdc']} USDC</td>"
        f"<td>{t['description']}</td>"
        f"<td><span class='tier'>{t['tier']}</span></td></tr>"
        for t in MANIFEST_TOOLS
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Onyx Actions — Paid Tools for AI Agents</title>
<style>
:root {{ color-scheme: dark; }}
body {{ font: 15px/1.55 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
       background:#0a0a0a; color:#ddd; margin:0; padding:48px 24px; max-width:880px; margin:0 auto; }}
h1 {{ color:#fff; font-size:28px; margin:0 0 8px; letter-spacing:-.02em; }}
h2 {{ color:#fff; font-size:16px; margin:36px 0 12px; border-bottom:1px solid #222; padding-bottom:8px; }}
.tag {{ display:inline-block; padding:2px 8px; border:1px solid #444; border-radius:3px; color:#aaa; font-size:12px; margin-right:6px; }}
.pitch {{ color:#888; margin:0 0 28px; font-size:16px; }}
table {{ width:100%; border-collapse:collapse; font-size:14px; }}
th,td {{ text-align:left; padding:10px 12px; border-bottom:1px solid #222; vertical-align:top; }}
th {{ color:#888; font-weight:normal; font-size:12px; text-transform:uppercase; letter-spacing:.08em; }}
code {{ background:#161616; padding:2px 6px; border-radius:3px; color:#7ee787; font-size:13px; }}
.price {{ color:#ffd166; white-space:nowrap; }}
.tier {{ color:#79c0ff; font-size:12px; }}
pre {{ background:#111; border:1px solid #222; padding:14px; border-radius:4px; overflow:auto; font-size:13px; color:#ccc; }}
a {{ color:#79c0ff; }}
.wallet {{ color:#888; font-size:12px; word-break:break-all; }}
</style></head><body>

<h1>Onyx Actions</h1>
<p class="pitch">Paid tools for AI agents. HTTP 402 → sign a USDC transfer → 200. The whole auth flow.</p>

<span class="tag">x402</span><span class="tag">{NETWORK_ENV}</span>
<span class="tag">USDC on Base</span><span class="tag">MCP-native</span>

<h2>Tools</h2>
<table><thead><tr><th>Name</th><th>Price</th><th>Description</th><th>Tier</th></tr></thead>
<tbody>{rows}</tbody></table>

<h2>Install (MCP)</h2>
<pre>// claude_desktop_config.json — Streamable HTTP MCP
{{
  "mcpServers": {{
    "onyx": {{
      "url": "https://onyx-actions.onrender.com/mcp"
    }}
  }}
}}</pre>

<h2>REST fallback</h2>
<pre>curl -X POST https://onyx-actions.onrender.com/v1/onyx_solve_captcha \\
     -H "content-type: application/json" \\
     -d '{{"image_url":"https://example.com/captcha.png"}}'
# → 402 Payment Required. Agent signs x402 EIP-3009 auth, retries, gets answer.</pre>

<h2>Settlement</h2>
<p class="wallet">Wallet: <code>{RECEIVE_ADDR}</code><br>
Facilitator: <code>{FACILITATOR_URL}</code><br>
Network: <code>{NETWORK_ENV}</code></p>

<h2>Manifest</h2>
<p><a href="/manifest">/manifest</a> · <a href="/health">/health</a> · <a href="https://github.com/dimitrilaouanis-tech/onyx-mcp">source</a></p>

</body></html>"""


# ----- Streamable HTTP MCP mount (pure ASGI sub-app) -------------------

async def _mcp_asgi(scope, receive, send):
    if scope["type"] != "http":
        return
    await _mcp_session.handle_request(scope, receive, send)


app.mount("/mcp", _mcp_asgi)


# ----- Public surfaces ---------------------------------------------------

@app.get("/")
async def root(request: Request):
    accept = request.headers.get("accept", "")
    if "text/html" in accept and "application/json" not in accept:
        return HTMLResponse(_landing_html())
    return JSONResponse(_manifest())


@app.get("/manifest")
async def manifest():
    return _manifest()


# ----- Bazaar / x402 service discovery ----------------------------------
# https://docs.cdp.coinbase.com/x402/bazaar — crawler reads this manifest

USDC_BY_NETWORK = {
    "base": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
    "base-sepolia": "0x036cbd53842c5426634e7929541ec2318f3dcf7e",
}


def _x402_manifest() -> dict:
    services = []
    for t in TOOLS:
        if t.TIER not in ("metered", "premium"):
            continue
        amount_atomic = str(int(round(float(t.PRICE_USDC) * 1_000_000)))
        services.append({
            "resource": f"https://onyx-actions.onrender.com/v1/{t.NAME}",
            "type": "http",
            "x402Version": 1,
            "accepts": [{
                "scheme": "exact",
                "network": NETWORK,
                "maxAmountRequired": amount_atomic,
                "asset": USDC_BY_NETWORK.get(NETWORK_ENV, ""),
                "payTo": RECEIVE_ADDR,
                "resource": f"https://onyx-actions.onrender.com/v1/{t.NAME}",
                "description": t.DESCRIPTION,
                "mimeType": "application/json",
                "outputSchema": {"type": "object"},
                "extra": {
                    "name": t.NAME,
                    "tier": t.TIER,
                    "price_usdc": t.PRICE_USDC,
                    "input_schema": t.INPUT_SCHEMA,
                },
            }],
        })
    return {
        "x402Version": 1,
        "services": services,
        "facilitator": FACILITATOR_URL,
    }


@app.get("/.well-known/x402.json")
async def well_known_x402():
    return _x402_manifest()


@app.get("/services.json")
async def services_json():
    return _x402_manifest()


@app.get("/health")
async def health():
    return {
        "ok": True,
        "network": NETWORK_ENV,
        "receive": RECEIVE_ADDR,
        "tools": [t.NAME for t in TOOLS],
        "mcp": "/mcp",
    }


# REST per-tool endpoints (auto-generated)
def _make_rest_handler(tool):
    async def handler(request: Request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        try:
            return await asyncio.to_thread(tool.run, **(body or {}))
        except (ValueError, NotImplementedError) as e:
            raise HTTPException(400, str(e))
    handler.__name__ = f"rest_{tool.NAME}"
    return handler


for _tool in TOOLS:
    app.add_api_route(
        f"/v1/{_tool.NAME}",
        _make_rest_handler(_tool),
        methods=["POST"],
        name=_tool.NAME,
    )


# ----- x402 payment middleware ------------------------------------------

ROUTES = {}
for _tool in TOOLS:
    if _tool.TIER in ("metered", "premium"):
        ROUTES[f"POST /v1/{_tool.NAME}"] = {
            "accepts": {
                "scheme": "exact",
                "network": NETWORK,
                "price": f"${_tool.PRICE_USDC}",
                "payTo": RECEIVE_ADDR,
                "description": _tool.DESCRIPTION[:120],
                "mimeType": "application/json",
            }
        }


@app.middleware("http")
async def x402_gate(request, call_next):
    return await payment_middleware(ROUTES, _x402_server)(request, call_next)
