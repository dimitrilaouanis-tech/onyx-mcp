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


def _make_cdp_header_factory(facilitator_url: str, key_id: str, key_secret: str):
    """Returns a callable that mints fresh CDP-JWT auth headers per request.

    The Coinbase CDP facilitator authenticates every request with a short-lived
    JWT signed with the customer's API key (Ed25519). The cdp-sdk handles JWT
    signing; if the SDK isn't installed we fall back to a manual JWT mint via
    PyNaCl + base64. Either path returns {"Authorization": "Bearer <jwt>"}.
    """
    from urllib.parse import urlparse
    parsed = urlparse(facilitator_url)
    host = parsed.netloc
    base_path = parsed.path.rstrip("/") or "/"

    def _build_uri(method: str, path: str) -> str:
        # CDP JWT spec: uri is "<METHOD> <host><path>" without scheme
        full = f"{base_path}{path}" if path.startswith("/") else f"{base_path}/{path}"
        return f"{method.upper()} {host}{full}"

    try:
        from cdp.auth.utils.jwt import generate_jwt, JwtOptions  # type: ignore

        def make(method: str = "POST", path: str = "/verify") -> dict[str, str]:
            jwt = generate_jwt(JwtOptions(
                api_key_id=key_id,
                api_key_secret=key_secret,
                request_method=method.upper(),
                request_host=host,
                request_path=f"{base_path}{path}" if path.startswith("/") else f"{base_path}/{path}",
                expires_in=120,
            ))
            return {"Authorization": f"Bearer {jwt}"}
        return make
    except ImportError:
        pass

    # Manual JWT mint fallback (Ed25519 via cryptography).
    import base64, json as _json, time as _time, secrets as _secrets

    def _b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except ImportError as e:
        raise RuntimeError(
            "Either install cdp-sdk or cryptography to use CDP facilitator auth"
        ) from e

    # CDP secrets are typically base64-PKCS8 Ed25519 private key
    try:
        priv_bytes = base64.b64decode(key_secret)
    except Exception as e:
        raise RuntimeError(f"CDP_API_KEY_SECRET must be base64-encoded: {e}")
    priv_key = Ed25519PrivateKey.from_private_bytes(priv_bytes[-32:])

    def make(method: str = "POST", path: str = "/verify") -> dict[str, str]:
        now = int(_time.time())
        header = {"alg": "EdDSA", "typ": "JWT", "kid": key_id, "nonce": _secrets.token_hex(16)}
        payload = {
            "iss": "cdp",
            "sub": key_id,
            "aud": ["cdp_service"],
            "nbf": now,
            "exp": now + 120,
            "uri": _build_uri(method, path),
        }
        signing_input = f"{_b64url(_json.dumps(header, separators=(',', ':')).encode())}." \
                        f"{_b64url(_json.dumps(payload, separators=(',', ':')).encode())}"
        sig = priv_key.sign(signing_input.encode("ascii"))
        return {"Authorization": f"Bearer {signing_input}.{_b64url(sig)}"}

    return make


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

        # x402 facilitator. When ONYX_NETWORK=base, the public x402.org
        # facilitator does NOT support mainnet — Coinbase CDP is the only
        # production-ready facilitator. Build a create_headers callable that
        # mints a CDP JWT per request when API keys are present in env.
        cdp_id = os.environ.get("CDP_API_KEY_ID", "").strip()
        cdp_secret = os.environ.get("CDP_API_KEY_SECRET", "").strip()
        create_headers = None
        if cdp_id and cdp_secret:
            create_headers = _make_cdp_header_factory(self.facilitator_url, cdp_id, cdp_secret)
            print(f"[onyx-paid-mcp] CDP auth ENABLED for {self.facilitator_url}")
        else:
            print(f"[onyx-paid-mcp] CDP auth NOT set — using {self.facilitator_url} unauthenticated (testnet only)")
        cfg = FacilitatorConfig(url=self.facilitator_url)
        if create_headers is not None:
            cfg["create_headers"] = create_headers
        fac = HTTPFacilitatorClient(cfg)
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

        from . import bazaar as _bazaar

        async def _bazaar_loop():
            while True:
                try:
                    await _bazaar.cache.refresh()
                except Exception:
                    pass
                await asyncio.sleep(_bazaar.REFRESH_SEC)

        @contextlib.asynccontextmanager
        async def lifespan(_):
            # Kick bazaar refresh + background loop alongside the MCP session
            asyncio.create_task(_bazaar.cache.refresh())
            loop_task = asyncio.create_task(_bazaar_loop())
            try:
                async with session.run():
                    yield
            finally:
                loop_task.cancel()

        api = FastAPI(title=self.name, version="0.1.0", lifespan=lifespan)

        async def _mcp_asgi(scope, receive, send):
            if scope["type"] != "http":
                return
            await session.handle_request(scope, receive, send)

        api.mount("/mcp", _mcp_asgi)

        @api.get("/", include_in_schema=False)
        async def _root(request: Request):
            accept = request.headers.get("accept", "")
            if "text/html" in accept and "application/json" not in accept:
                return HTMLResponse(self._landing_html())
            return JSONResponse(self.manifest())

        @api.get("/manifest", include_in_schema=False)
        async def _manifest():
            return self.manifest()

        @api.get("/.well-known/x402", include_in_schema=False)
        async def _well_known_x402_canonical():
            return self.x402_manifest()

        @api.get("/.well-known/x402.json", include_in_schema=False)
        async def _well_known():
            return self.x402_manifest()

        @api.get("/services.json", include_in_schema=False)
        async def _services():
            return self.x402_manifest()

        # ------- Bazaar leaderboard (public x402 stats) ----------------
        # Cron started in lifespan above; routes below.

        @api.get("/bazaar", include_in_schema=False)
        async def _bazaar_view(request: Request, view: str = "volume",
                               format: str = "html", limit: int = 100):
            view = view if view in {"volume", "payers", "newest", "cheapest"} else "volume"
            rows = _bazaar.ranked(view=view, limit=min(max(limit, 1), 500))
            if format == "json" or "application/json" in request.headers.get("accept", ""):
                return JSONResponse({
                    "view": view,
                    "rows": rows,
                    "stats": _bazaar.stats_summary(),
                })
            return HTMLResponse(_bazaar.render_html(view, rows, _bazaar.stats_summary()))

        @api.get("/bazaar.json", include_in_schema=False)
        async def _bazaar_json(view: str = "volume", limit: int = 100):
            view = view if view in {"volume", "payers", "newest", "cheapest"} else "volume"
            return {
                "view": view,
                "rows": _bazaar.ranked(view=view, limit=min(max(limit, 1), 500)),
                "stats": _bazaar.stats_summary(),
            }

        @api.get("/health", include_in_schema=False)
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

        @api.get("/llms.txt", response_class=PlainTextResponse, include_in_schema=False)
        async def _llms_txt():
            for p in (_Path("llms.txt"), _Path(__file__).parent.parent / "llms.txt"):
                if p.exists():
                    return p.read_text(encoding="utf-8")
            return f"# {self.name}\nSee {self.public_url or '/manifest'} for tool list.\n"

        # REST per-tool endpoints
        def _make(t: Tool):
            # Use Body(...) so FastAPI's OpenAPI introspector treats this as
            # a JSON body param (which we override via openapi_extra), instead
            # of trying to derive a schema from `request: Request` (which
            # crashes pydantic's TypeAdapter on ForwardRef).
            from fastapi import Body
            from typing import Any as _Any
            async def handler(body: dict = Body(default_factory=dict)):
                try:
                    out = t.handler(**(body or {}))
                    if asyncio.iscoroutine(out):
                        out = await out
                    return out
                except (ValueError, NotImplementedError) as e:
                    raise HTTPException(400, str(e))
            handler.__name__ = f"rest_{t.name}"
            return handler

        def _make_introspect(t: Tool):
            base = (self.public_url or "").rstrip("/")
            example = getattr(t.handler, "__example_request__", None)
            example_response = getattr(t.handler, "__example_response__", None)
            when_to_use = getattr(t.handler, "__when_to_use__", None)
            vs_alternatives = getattr(t.handler, "__vs_alternatives__", None)

            async def introspect():
                return {
                    "name": t.name,
                    "tier": t.tier,
                    "price_usdc": t.price_usdc,
                    "endpoint": f"{base}/v1/{t.name}",
                    "method": "POST",
                    "input_schema": t.input_schema,
                    "description": t.description,
                    "when_to_use": when_to_use,
                    "vs_alternatives": vs_alternatives,
                    "example_request": example,
                    "example_response": example_response,
                    "settle_to": self.receive_address,
                    "network": self.network,
                    "facilitator": self.facilitator_url,
                    "payment_required": t.tier in ("metered", "premium"),
                    "free_introspection": True,
                    "note": "GET this URL = free introspection card. POST with x402 payment header to call.",
                }
            introspect.__name__ = f"introspect_{t.name}"
            return introspect

        for t in tools:
            # Explicit OpenAPI body schema — FastAPI's auto-derive crashes on
            # our handler signature (Request-typed param). x402scan probes
            # /openapi.json to discover inputSchema; without this its registration
            # validator fails with "Missing input schema". This is the single
            # mechanical gate between Onyx and the indexer ecosystem.
            paid_openapi_extra = {
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": t.input_schema,
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Tool result",
                        "content": {"application/json": {"schema": {"type": "object"}}},
                    },
                    "402": {
                        "description": "Payment required (x402)",
                        "headers": {
                            "Payment-Required": {
                                "description": "Base64-encoded x402 challenge",
                                "schema": {"type": "string"},
                            }
                        },
                    },
                },
                "summary": t.name,
                "description": t.description[:500],
                "x-x402-tool": t.name,
                "x-x402-price-usdc": t.price_usdc,
                "x-x402-tier": t.tier,
            }
            api.add_api_route(
                f"/v1/{t.name}", _make(t), methods=["POST"], name=t.name,
                openapi_extra=paid_openapi_extra,
            )
            api.add_api_route(
                f"/v1/{t.name}", _make_introspect(t), methods=["GET"],
                name=f"{t.name}_introspect",
                openapi_extra={
                    "summary": f"{t.name} — free introspection card",
                    "description": "Free GET — returns tool metadata, schemas, comparison anchors. POST same URL with x402 payment to actually call.",
                },
            )

        # x402 middleware — proper shape per x402 python lib docs:
        # - accepts: {scheme, network, payTo, price, ...} (flat)
        # - extensions.bazaar: surfaces inputSchema/outputSchema to discovery
        #   crawlers (x402scan, Coinbase Bazaar). Library auto-registers the
        #   bazaar extension when it sees `extensions.bazaar` in any route.
        routes = {}
        for t in tools:
            if t.tier not in ("metered", "premium"):
                continue
            example_body = {}
            if isinstance(t.input_schema, dict):
                props = t.input_schema.get("properties", {}) or {}
                # build a minimal example from required props
                for req in t.input_schema.get("required", []) or []:
                    spec = props.get(req, {})
                    typ = spec.get("type", "string")
                    if typ == "string":
                        example_body[req] = spec.get("example", "")
                    elif typ in ("integer", "number"):
                        example_body[req] = 0
                    elif typ == "boolean":
                        example_body[req] = False
                    else:
                        example_body[req] = None
            routes[f"POST /v1/{t.name}"] = {
                "accepts": {
                    "scheme": "exact",
                    "network": self.network_caip,
                    "price": f"${t.price_usdc}",
                    "payTo": self.receive_address,
                    # PaymentOption fields are strict; description/mimeType
                    # live at route level. Use `extra` for x402scan-required
                    # fields (inputSchema/outputSchema): it's a free dict the
                    # lib passes through to the 402 challenge verbatim.
                    "extra": {
                        "name": "USDC",
                        "version": "2",
                        "inputSchema": t.input_schema,
                        "outputSchema": {"type": "object"},
                        "tool": t.name,
                    },
                },
                "description": t.description[:300],
                "mime_type": "application/json",
                "extensions": {
                    "bazaar": {
                        "info": {
                            "input": {
                                "type": "http",
                                "method": "POST",
                                "bodyType": "json",
                                "body": example_body,
                            },
                            "output": {"type": "object", "format": "json"},
                        },
                        "schema": t.input_schema,
                    },
                },
            }

        @api.middleware("http")
        async def _gate(request, call_next):
            try:
                return await payment_middleware(routes, x402_server)(request, call_next)
            except Exception as e:
                # Silent log to stderr (Render captures these). Do NOT leak
                # internals to the response — return a generic 500.
                import sys, traceback
                from fastapi.responses import JSONResponse
                sys.stderr.write(
                    f"[gate-error] {type(e).__name__}: {str(e)[:300]} "
                    f"path={request.url.path} method={request.method}\n"
                    f"{traceback.format_exc()}\n"
                )
                sys.stderr.flush()
                return JSONResponse(
                    status_code=500,
                    content={"error": "internal_error"},
                )

        return api

    def serve(self, host: str = "0.0.0.0", port: int = 8080) -> None:
        import uvicorn
        uvicorn.run(self.build_asgi(), host=host, port=port)

    # ---------- landing ----------

    def _landing_html(self) -> str:
        # Hero tools — show the highest-value 6 first, then the rest collapsed
        all_tools = sorted(self._tools.values(), key=lambda t: -float(t.price_usdc))
        hero_names = {
            "onyx_base_tx_explainer", "onyx_sms_verify", "onyx_solve_captcha",
            "onyx_agent_signup_kit", "onyx_base_token_risk_scan", "onyx_base_tx_simulator",
        }
        hero = [t for t in all_tools if t.name in hero_names]
        rest = [t for t in all_tools if t.name not in hero_names]

        def card(t):
            when = getattr(t.handler, "__when_to_use__", None)
            vs = getattr(t.handler, "__vs_alternatives__", None)
            extra = ""
            if when:
                extra += f"<div class='when'><strong>When:</strong> {when}</div>"
            if vs:
                extra += f"<div class='vs'><strong>vs:</strong> {vs}</div>"
            return (
                f"<div class='tool'>"
                f"<div class='th'><code>{t.name}</code><span class='price'>${t.price_usdc}</span></div>"
                f"<div class='desc'>{t.description}</div>"
                f"{extra}"
                f"<div class='probe'>Free probe: <code>GET {(self.public_url or '').rstrip('/')}/v1/{t.name}</code></div>"
                f"</div>"
            )

        hero_html = "\n".join(card(t) for t in hero)
        rest_rows = "\n".join(
            f"<tr><td><code>{t.name}</code></td><td class='price'>${t.price_usdc}</td>"
            f"<td>{t.description[:160]}...</td></tr>"
            for t in rest
        )
        n_tools = len(all_tools)
        public = (self.public_url or "").rstrip("/")
        return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{self.name} — {n_tools} paid agent tools, USDC on Base, no API key</title>
<meta name="description" content="{n_tools} x402-paid agent tools on Base mainnet. Captcha, SMS OTP, HLR, on-chain primitives. Pay per call in USDC, no signup, no API key. MCP-native at /mcp/.">
<style>
:root {{ color-scheme: dark; }}
body {{ font: 15px/1.55 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
       background:#0a0a0a; color:#ddd; margin:0; padding:48px 24px; max-width:980px; margin:0 auto; }}
h1 {{ color:#fff; font-size:34px; margin:0 0 8px; letter-spacing:-.02em; }}
.tag {{ display:inline-block; padding:3px 10px; border:1px solid #2a2a2a; border-radius:3px; color:#aaa; font-size:12px; margin-right:6px; }}
.lede {{ color:#ccc; font-size:17px; margin:18px 0 32px; line-height:1.5; }}
h2 {{ color:#fff; font-size:18px; margin:42px 0 16px; border-bottom:1px solid #1f1f1f; padding-bottom:10px; }}
.tool {{ background:#101010; border:1px solid #1c1c1c; border-radius:6px; padding:18px 20px; margin:14px 0; }}
.th {{ display:flex; justify-content:space-between; align-items:baseline; margin-bottom:6px; }}
.th code {{ color:#7ee787; font-size:15px; }}
.price {{ color:#ffd166; font-weight:600; }}
.desc {{ color:#bbb; font-size:13px; margin:8px 0; }}
.when {{ color:#9aaccd; font-size:13px; margin:6px 0; }}
.vs {{ color:#a48f6a; font-size:13px; margin:6px 0; }}
.probe {{ color:#666; font-size:12px; margin-top:10px; }}
.probe code {{ color:#79c0ff; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; margin-top:12px; }}
th,td {{ text-align:left; padding:9px 12px; border-bottom:1px solid #1a1a1a; vertical-align:top; }}
th {{ color:#888; font-weight:normal; font-size:11px; text-transform:uppercase; letter-spacing:.08em; }}
td code {{ background:#161616; padding:2px 6px; border-radius:3px; color:#7ee787; font-size:13px; }}
pre {{ background:#101010; border:1px solid #1c1c1c; padding:16px; border-radius:5px; overflow:auto; font-size:12.5px; color:#ddd; }}
a {{ color:#79c0ff; }}
.cta {{ background:#0e1418; border-left:3px solid #79c0ff; padding:14px 18px; margin:28px 0; font-size:14px; }}
.cta strong {{ color:#fff; }}
.wallet {{ color:#666; font-size:11px; word-break:break-all; }}
.kpi {{ display:flex; gap:16px; margin:14px 0 28px; flex-wrap:wrap; }}
.kpi span {{ background:#101010; border:1px solid #1c1c1c; padding:8px 14px; border-radius:4px; color:#ddd; font-size:12.5px; }}
.kpi b {{ color:#7ee787; }}
</style></head><body>

<h1>{self.name}</h1>
<p class="lede">{self.description}</p>

<div>
  <span class="tag">{n_tools} paid tools</span>
  <span class="tag">{self.network} mainnet</span>
  <span class="tag">USDC settlement</span>
  <span class="tag">No API key, no signup</span>
  <span class="tag">MCP-native</span>
</div>

<div class="cta">
  <strong>Try free, pay only when you call.</strong> Every paid endpoint accepts
  <code>GET</code> for a free introspection card (price, when-to-use, comparison vs alternatives,
  example request/response). When you're ready, <code>POST</code> with an x402 payment header
  and your wallet settles USDC directly to ours. No middleman, no monthly fee, no minimum.
</div>

<h2>Top tools</h2>
{hero_html}

<h2>Install in any MCP client</h2>
<pre>// claude_desktop_config.json / Cursor / Cline
{{
  "mcpServers": {{
    "{self.name}": {{
      "url": "{public}/mcp/"
    }}
  }}
}}</pre>

<h2>Free public x402 leaderboard</h2>
<p>The only public dashboard of every paid x402 service indexed from Coinbase's CDP discovery API,
refreshed every 15 minutes. Four views, JSON variant for programmatic consumers.</p>
<pre>{public}/bazaar      — HTML leaderboard
{public}/bazaar.json — JSON variant</pre>

<h2>Other tools ({len(rest)})</h2>
<table><thead><tr><th>Name</th><th>Price</th><th>Description</th></tr></thead>
<tbody>{rest_rows}</tbody></table>

<h2>Endpoints</h2>
<p><a href="/manifest">/manifest</a> · <a href="/.well-known/x402.json">/.well-known/x402.json</a> · <a href="/bazaar">/bazaar</a> · <a href="/llms.txt">/llms.txt</a> · <a href="/health">/health</a></p>

<h2>Settlement</h2>
<p class="wallet">USDC settles on {self.network} to <code>{self.receive_address}</code><br>
Facilitator: <code>{self.facilitator_url}</code></p>

<p style="margin-top:48px;color:#555;font-size:12px">
Built on the open-source <a href="https://github.com/dimitrilaouanis-tech/onyx-mcp">onyx-paid-mcp</a> framework.
Ship a paid MCP in 5 lines · MIT licensed.
</p>

</body></html>"""
