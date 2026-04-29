"""Core App + tool() decorator.

Keep all framework wiring here. Users import from `onyx_paid_mcp` and never
touch FastAPI / x402 / mcp directly.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional


@dataclass
class Tool:
    name: str
    price_usdc: str
    description: str
    input_schema: dict
    handler: Callable[..., Any]
    tier: str = "metered"


def tool(
    *,
    name: str,
    price_usdc: str,
    description: str,
    input_schema: dict,
    tier: str = "metered",
) -> Callable[[Callable[..., Any]], Tool]:
    """Module-level decorator (rare). Prefer `@app.tool(...)` for binding."""
    def wrap(fn: Callable[..., Any]) -> Tool:
        return Tool(
            name=name, price_usdc=price_usdc, description=description,
            input_schema=input_schema, handler=fn, tier=tier,
        )
    return wrap


_NETWORK_CAIP = {"base": "eip155:8453", "base-sepolia": "eip155:84532"}
_USDC_BY_NETWORK = {
    "base": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
    "base-sepolia": "0x036cbd53842c5426634e7929541ec2318f3dcf7e",
}
_DEFAULT_FACILITATORS = {
    "base": "https://x402.org/facilitator",
    "base-sepolia": "https://x402.org/facilitator",
}


@dataclass
class App:
    name: str
    receive_address: str
    network: str = "base-sepolia"
    facilitator_url: Optional[str] = None
    public_url: Optional[str] = None
    description: str = ""
    homepage: Optional[str] = None
    _tools: dict[str, Tool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.network not in _NETWORK_CAIP:
            raise ValueError(f"network must be one of {list(_NETWORK_CAIP)}")
        if not self.receive_address.startswith("0x") or len(self.receive_address) != 42:
            raise ValueError("receive_address must be a 0x-prefixed 20-byte hex address")
        self.facilitator_url = self.facilitator_url or _DEFAULT_FACILITATORS[self.network]

    @property
    def network_caip(self) -> str:
        return _NETWORK_CAIP[self.network]

    @property
    def usdc_address(self) -> str:
        return _USDC_BY_NETWORK[self.network]

    def tool(
        self,
        *,
        name: str,
        price_usdc: str,
        description: str,
        input_schema: dict,
        tier: str = "metered",
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator: register a paid tool on this app."""
        def wrap(fn: Callable[..., Any]) -> Callable[..., Any]:
            self._tools[name] = Tool(
                name=name, price_usdc=price_usdc, description=description,
                input_schema=input_schema, handler=fn, tier=tier,
            )
            return fn
        return wrap

    def add(self, t: Tool) -> None:
        """Register a Tool created by the module-level `tool()` decorator."""
        self._tools[t.name] = t

    def tools(self) -> list[Tool]:
        return list(self._tools.values())

    # ---------- manifests ----------

    def manifest(self) -> dict:
        return {
            "service": self.name,
            "version": "0.1.0",
            "description": self.description,
            "network": self.network,
            "receive_wallet": self.receive_address,
            "facilitator": self.facilitator_url,
            "mcp_endpoint": "/mcp/",
            "homepage": self.homepage,
            "tools": [
                {
                    "name": t.name,
                    "price_usdc": t.price_usdc,
                    "tier": t.tier,
                    "description": t.description,
                    "input_schema": t.input_schema,
                }
                for t in self._tools.values()
            ],
        }

    def x402_manifest(self) -> dict:
        base = (self.public_url or "").rstrip("/")
        services = []
        for t in self._tools.values():
            if t.tier not in ("metered", "premium"):
                continue
            atomic = str(int(round(float(t.price_usdc) * 1_000_000)))
            services.append({
                "resource": f"{base}/v1/{t.name}",
                "type": "http",
                "x402Version": 1,
                "accepts": [{
                    "scheme": "exact",
                    "network": self.network_caip,
                    "maxAmountRequired": atomic,
                    "asset": self.usdc_address,
                    "payTo": self.receive_address,
                    "resource": f"{base}/v1/{t.name}",
                    "description": t.description,
                    "mimeType": "application/json",
                    "outputSchema": {"type": "object"},
                    "extra": {
                        "name": t.name,
                        "tier": t.tier,
                        "price_usdc": t.price_usdc,
                        "input_schema": t.input_schema,
                    },
                }],
            })
        return {"x402Version": 1, "services": services, "facilitator": self.facilitator_url}

    # ---------- runtime build ----------

    def build_asgi(self):
        """Construct the FastAPI ASGI app. Heavy imports happen here."""
        from fastapi import FastAPI, HTTPException, Request
        from fastapi.responses import HTMLResponse, JSONResponse

        import mcp.types as mcp_types
        from mcp.server import Server as MCPServer
        from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

        from x402 import FacilitatorConfig, x402ResourceServer
        from x402.http.facilitator_client import HTTPFacilitatorClient
        from x402.http.middleware.fastapi import payment_middleware
        from x402.mechanisms.evm.exact import register_exact_evm_server

        tools = self.tools()
        tools_by_name = {t.name: t for t in tools}

        # x402 facilitator
        fac = HTTPFacilitatorClient(FacilitatorConfig(url=self.facilitator_url))
        x402_server = x402ResourceServer(facilitator_clients=fac)
        register_exact_evm_server(x402_server)

        # MCP server
        mcp_app: MCPServer = MCPServer(self.name)

        @mcp_app.list_tools()
        async def _list() -> list[mcp_types.Tool]:
            return [
                mcp_types.Tool(
                    name=t.name,
                    description=f"{t.description} (price: ${t.price_usdc} USDC, tier: {t.tier})",
                    inputSchema=t.input_schema,
                )
                for t in tools
            ]

        @mcp_app.call_tool()
        async def _call(name: str, arguments: dict) -> list[mcp_types.TextContent]:
            t = tools_by_name.get(name)
            if t is None:
                raise ValueError(f"Unknown tool: {name}")
            # Paid tools cannot be settled through the MCP JSON-RPC transport —
            # x402 needs an HTTP request/response pair so the wallet can sign the
            # EIP-3009 authorization and the facilitator can settle on-chain.
            # Return a structured 402 message pointing the agent at the REST
            # endpoint. Bridges like @onyx/x402-bridge handle this transparently.
            if t.tier in ("metered", "premium"):
                base = (self.public_url or "").rstrip("/")
                challenge = {
                    "x402Version": 1,
                    "error": "payment_required",
                    "message": (
                        f"Tool '{t.name}' is paid (${t.price_usdc} USDC). "
                        f"MCP JSON-RPC cannot carry x402 payments — call the "
                        f"HTTP endpoint instead."
                    ),
                    "accepts": [{
                        "scheme": "exact",
                        "network": self.network_caip,
                        "maxAmountRequired": str(int(round(float(t.price_usdc) * 1_000_000))),
                        "asset": self.usdc_address,
                        "payTo": self.receive_address,
                        "resource": f"{base}/v1/{t.name}",
                        "description": t.description[:200],
                        "mimeType": "application/json",
                    }],
                    "facilitator": self.facilitator_url,
                    "docs": "https://x402.org/clients",
                    "bridge": "npx @onyx/x402-bridge " + base + "/mcp/",
                }
                return [mcp_types.TextContent(type="text", text=json.dumps(challenge))]
            # Free-tier tool — run normally.
            result = t.handler(**(arguments or {}))
            if asyncio.iscoroutine(result):
                result = await result
            return [mcp_types.TextContent(type="text", text=json.dumps(result))]

        session = StreamableHTTPSessionManager(app=mcp_app, json_response=False, stateless=True)

        @contextlib.asynccontextmanager
        async def lifespan(_):
            async with session.run():
                yield

        api = FastAPI(title=self.name, version="0.1.0", lifespan=lifespan)

        async def _mcp_asgi(scope, receive, send):
            if scope["type"] != "http":
                return
            await session.handle_request(scope, receive, send)

        api.mount("/mcp", _mcp_asgi)

        @api.get("/")
        async def _root(request: Request):
            accept = request.headers.get("accept", "")
            if "text/html" in accept and "application/json" not in accept:
                return HTMLResponse(self._landing_html())
            return JSONResponse(self.manifest())

        @api.get("/manifest")
        async def _manifest():
            return self.manifest()

        @api.get("/.well-known/x402.json")
        async def _well_known():
            return self.x402_manifest()

        @api.get("/services.json")
        async def _services():
            return self.x402_manifest()

        @api.get("/health")
        async def _health():
            return {
                "ok": True, "network": self.network,
                "receive": self.receive_address,
                "tools": [t.name for t in tools],
                "mcp": "/mcp/",
            }

        # Serve llms.txt from CWD if present, so crawlers + LLMs can index us
        from fastapi.responses import PlainTextResponse
        from pathlib import Path as _Path

        @api.get("/llms.txt", response_class=PlainTextResponse)
        async def _llms_txt():
            for p in (_Path("llms.txt"), _Path(__file__).parent.parent / "llms.txt"):
                if p.exists():
                    return p.read_text(encoding="utf-8")
            return f"# {self.name}\nSee {self.public_url or '/manifest'} for tool list.\n"

        # REST per-tool endpoints
        def _make(t: Tool):
            async def handler(request: Request):
                try:
                    body = await request.json()
                except Exception:
                    body = {}
                try:
                    out = t.handler(**(body or {}))
                    if asyncio.iscoroutine(out):
                        out = await out
                    return out
                except (ValueError, NotImplementedError) as e:
                    raise HTTPException(400, str(e))
            handler.__name__ = f"rest_{t.name}"
            return handler

        for t in tools:
            api.add_api_route(f"/v1/{t.name}", _make(t), methods=["POST"], name=t.name)

        # x402 middleware
        routes = {}
        for t in tools:
            if t.tier in ("metered", "premium"):
                routes[f"POST /v1/{t.name}"] = {
                    "accepts": {
                        "scheme": "exact",
                        "network": self.network_caip,
                        "price": f"${t.price_usdc}",
                        "payTo": self.receive_address,
                        "description": t.description[:120],
                        "mimeType": "application/json",
                    }
                }

        @api.middleware("http")
        async def _gate(request, call_next):
            return await payment_middleware(routes, x402_server)(request, call_next)

        return api

    def serve(self, host: str = "0.0.0.0", port: int = 8080) -> None:
        import uvicorn
        uvicorn.run(self.build_asgi(), host=host, port=port)

    # ---------- landing ----------

    def _landing_html(self) -> str:
        rows = "\n".join(
            f"<tr><td><code>{t.name}</code></td>"
            f"<td class='price'>${t.price_usdc}</td>"
            f"<td>{t.description}</td><td>{t.tier}</td></tr>"
            for t in self._tools.values()
        )
        return f"""<!doctype html><html><head><meta charset="utf-8">
<title>{self.name} — paid MCP via x402</title>
<style>body{{font:15px ui-monospace,Menlo,monospace;background:#0a0a0a;color:#ddd;max-width:900px;margin:auto;padding:48px 24px}}
h1{{color:#fff}} table{{width:100%;border-collapse:collapse}} td,th{{padding:8px;border-bottom:1px solid #222;text-align:left}}
code{{background:#161616;padding:2px 6px;border-radius:3px;color:#7ee787}}.price{{color:#ffd166}} a{{color:#79c0ff}}</style>
</head><body>
<h1>{self.name}</h1>
<p>{self.description}</p>
<p>Network: <code>{self.network}</code> · Wallet: <code>{self.receive_address}</code></p>
<h2>Tools</h2><table><thead><tr><th>Name</th><th>Price</th><th>Description</th><th>Tier</th></tr></thead>
<tbody>{rows}</tbody></table>
<h2>Install (MCP)</h2><pre>{{ "mcpServers": {{ "{self.name}": {{ "url": "{(self.public_url or '').rstrip('/')}/mcp/" }} }} }}</pre>
<p><a href="/manifest">/manifest</a> · <a href="/.well-known/x402.json">/.well-known/x402.json</a> · <a href="/health">/health</a></p>
<p>Built with <a href="https://github.com/dimitrilaouanis-tech/onyx-mcp">onyx-paid-mcp</a></p>
</body></html>"""
