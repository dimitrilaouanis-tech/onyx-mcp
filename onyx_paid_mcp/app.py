"""Core App + tool() decorator.

Keep all framework wiring here. Users import from `onyx_paid_mcp` and never
touch FastAPI / x402 / mcp directly.
"""
from __future__ import annotations

import asyncio
import contextlib
import copy
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
    # Optional second receive address to dual-broadcast in /.well-known/x402.json.
    # When set + current network != "base", the manifest emits a second accepts[]
    # entry per service for Base mainnet. CDP discovery (and any mainnet-filtering
    # indexer) then sees us even while the running server is in Sepolia mode.
    # Set to empty string to disable.
    mainnet_receive_address: Optional[str] = None
    _tools: dict[str, Tool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.network not in _NETWORK_CAIP:
            raise ValueError(f"network must be one of {list(_NETWORK_CAIP)}")
        if not self.receive_address.startswith("0x") or len(self.receive_address) != 42:
            raise ValueError("receive_address must be a 0x-prefixed 20-byte hex address")
        if self.mainnet_receive_address:
            ma = self.mainnet_receive_address.strip()
            if ma and (not ma.startswith("0x") or len(ma) != 42):
                raise ValueError("mainnet_receive_address must be a 0x-prefixed 20-byte hex address")
            self.mainnet_receive_address = ma or None
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
        # Build accepts[] templates once per known network so we can dual-broadcast.
        primary = {
            "network_caip": self.network_caip,
            "asset": self.usdc_address,
            "payTo": self.receive_address,
        }
        secondary = None
        if self.mainnet_receive_address and self.network != "base":
            secondary = {
                "network_caip": _NETWORK_CAIP["base"],
                "asset": _USDC_BY_NETWORK["base"],
                "payTo": self.mainnet_receive_address,
            }

        services = []
        for t in self._tools.values():
            if t.tier not in ("metered", "premium"):
                continue
            atomic = str(int(round(float(t.price_usdc) * 1_000_000)))
            resource = f"{base}/v1/{t.name}"

            def _accepts(target: dict) -> dict:
                return {
                    "scheme": "exact",
                    "network": target["network_caip"],
                    "maxAmountRequired": atomic,
                    "asset": target["asset"],
                    "payTo": target["payTo"],
                    "resource": resource,
                    "description": t.description,
                    "mimeType": "application/json",
                    "outputSchema": {"type": "object"},
                    "maxTimeoutSeconds": 60,
                    "extra": {
                        "name": t.name,
                        "tier": t.tier,
                        "price_usdc": t.price_usdc,
                        "input_schema": t.input_schema,
                    },
                }

            accepts_list = [_accepts(primary)]
            if secondary is not None:
                accepts_list.append(_accepts(secondary))

            services.append({
                "resource": resource,
                "type": "http",
                "x402Version": 2,
                "accepts": accepts_list,
                # OATP-pattern bazaar extension — crawlers use this to surface
                # input shape + output example without making a paid call.
                "extensions": {
                    "bazaar": {
                        "info": {
                            "input": {
                                "type": "http",
                                "method": "POST",
                                "bodyType": "json",
                                "body": t.input_schema,
                            },
                            "output": {
                                "type": "object",
                                "schema": {"type": "object"},
                            },
                        }
                    }
                },
            })
        return {
            "x402Version": 2,
            "services": services,
            "facilitator": self.facilitator_url,
        }

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

        from fastapi import Header

        @api.get("/", include_in_schema=False)
        async def _root(accept: str = Header(default="")):
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

        # ------- OAuth 2.1 + Dynamic Client Registration (RFC 7591) ----------
        # MCP April 2026 spec mandates DCR for ChatGPT custom-connector + Claude
        # Managed Agents discovery. Without these endpoints, paid MCP servers
        # are invisible to those clients. Implementation accepts ANY client (we
        # don't gate at the OAuth layer — payment is enforced per-tool by x402).
        @api.get("/.well-known/oauth-authorization-server", include_in_schema=False)
        async def _well_known_oauth():
            base = (self.public_url or "").rstrip("/")
            return {
                "issuer": base or "/",
                "authorization_endpoint": f"{base}/oauth/authorize",
                "token_endpoint": f"{base}/oauth/token",
                "registration_endpoint": f"{base}/oauth/register",
                "scopes_supported": ["mcp:read", "mcp:call"],
                "response_types_supported": ["code"],
                "grant_types_supported": ["authorization_code", "client_credentials"],
                "token_endpoint_auth_methods_supported": ["none", "client_secret_post"],
                "code_challenge_methods_supported": ["S256"],
            }

        @api.get("/.well-known/oauth-protected-resource", include_in_schema=False)
        async def _well_known_oauth_resource():
            base = (self.public_url or "").rstrip("/")
            return {
                "resource": base or "/",
                "authorization_servers": [base or "/"],
                "scopes_supported": ["mcp:read", "mcp:call"],
                "bearer_methods_supported": ["header"],
            }

        # NOTE: `from __future__ import annotations` makes type hints strings,
        # which prevents FastAPI from resolving `request: Request`. Use
        # primitive params + manual body parsing instead.
        from fastapi import Body

        @api.post("/oauth/register", include_in_schema=False)
        async def _oauth_register(body: dict = Body(default={})):
            # RFC 7591 stub — auto-issues a public client_id, no secret. We
            # don't gate access here (payment is enforced per-tool by x402);
            # this exists so DCR-aware clients can register without 404.
            body = body or {}
            import secrets as _secrets
            cid = "onyx-" + _secrets.token_urlsafe(12)
            return JSONResponse({
                "client_id": cid,
                "client_id_issued_at": int(asyncio.get_event_loop().time()),
                "token_endpoint_auth_method": "none",
                "redirect_uris": body.get("redirect_uris") or [],
                "grant_types": ["authorization_code", "client_credentials"],
                "response_types": ["code"],
                "client_name": body.get("client_name") or "anonymous",
                "scope": "mcp:read mcp:call",
            })

        @api.post("/oauth/token", include_in_schema=False)
        async def _oauth_token():
            # Public auth — no real token needed; payment is per-tool x402.
            return {
                "access_token": "public",
                "token_type": "Bearer",
                "expires_in": 86400,
                "scope": "mcp:read mcp:call",
            }

        @api.get("/oauth/authorize", include_in_schema=False)
        async def _oauth_authorize(
            redirect_uri: str = "",
            state: str = "",
            client_id: str = "",
            scope: str = "",
            code_challenge: str = "",
            code_challenge_method: str = "",
        ):
            # Auto-approve + redirect with synthetic code; payment is per-tool x402.
            from fastapi.responses import RedirectResponse
            if not redirect_uri:
                return JSONResponse({"error": "missing redirect_uri"}, status_code=400)
            sep = "&" if "?" in redirect_uri else "?"
            return RedirectResponse(f"{redirect_uri}{sep}code=public&state={state}")

        # ------- Bazaar leaderboard (public x402 stats) ----------------
        # Cron started in lifespan above; routes below.

        @api.get("/bazaar", include_in_schema=False)
        async def _bazaar_view(view: str = "volume",
                               format: str = "html", limit: int = 100,
                               accept: str = Header(default="")):
            view = view if view in {"volume", "payers", "newest", "cheapest"} else "volume"
            rows = _bazaar.ranked(view=view, limit=min(max(limit, 1), 500))
            if format == "json" or "application/json" in accept:
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

        # Public dashboard — live state visible to anyone. Transparency moat:
        # every paid-MCP-builder wants to see how we structure pricing and
        # catalog, and every potential paying agent wants to see we are real.
        @api.get("/dashboard", include_in_schema=False)
        async def _dashboard(
            format: str = "html",
            accept: str = Header(default=""),
        ):
            data = self._dashboard_data(tools)
            if format == "json" or "application/json" in accept:
                return JSONResponse(data)
            return HTMLResponse(self._dashboard_html(data))

        @api.get("/dashboard.json", include_in_schema=False)
        async def _dashboard_json():
            return self._dashboard_data(tools)

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
            # x402 lib's bazaar extension mutates the schema dict we pass it
            # (server.py:192 appends "method" to required[]). Deepcopy each
            # reference so extra.inputSchema stays clean.
            routes[f"POST /v1/{t.name}"] = {
                "accepts": {
                    "scheme": "exact",
                    "network": self.network_caip,
                    "price": f"${t.price_usdc}",
                    "payTo": self.receive_address,
                    "extra": {
                        "name": "USDC",
                        "version": "2",
                        "inputSchema": copy.deepcopy(t.input_schema),
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
                        "schema": copy.deepcopy(t.input_schema),
                    },
                },
            }

        @api.middleware("http")
        async def _gate(request, call_next):
            try:
                return await payment_middleware(routes, x402_server)(request, call_next)
            except Exception as e:
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

    # ---------- dashboard ----------

    def _categorize(self, name: str) -> str:
        n = name.lower()
        if "solana" in n: return "solana"
        if "base_" in n or n.startswith("onyx_base"): return "base"
        if any(k in n for k in ("captcha", "ocr")): return "captcha"
        if "browser" in n or any(k in n for k in ("navigate","screenshot","click","extract","eval","type")): return "browser"
        if any(k in n for k in ("research", "paper", "arxiv")): return "research"
        if any(k in n for k in ("oauth", "mcp_", "facilitator", "indexer", "bazaar", "x402", "spec_lookup", "receipt", "chain_picker", "demo_wallet", "agent_id", "agent_budget", "agent_workflow", "meta_call")): return "mcp_x402_ops"
        if any(k in n for k in ("url", "dns", "whois", "email", "ip_", "html", "robots", "user_agent")): return "web"
        if any(k in n for k in ("jwt", "hash", "password", "fx_")): return "crypto_util"
        if "ens" in n or "aml" in n: return "evm_util"
        return "other"

    def _dashboard_data(self, tools: list) -> dict:
        from collections import Counter
        cat_count: Counter = Counter()
        cat_paid: Counter = Counter()
        cat_free: Counter = Counter()
        cat_total_price: dict[str, float] = {}
        for t in tools:
            c = self._categorize(t.name)
            cat_count[c] += 1
            if t.tier == "free":
                cat_free[c] += 1
            else:
                cat_paid[c] += 1
                cat_total_price[c] = cat_total_price.get(c, 0.0) + float(t.price_usdc)

        categories = []
        for c in sorted(cat_count, key=lambda k: -cat_count[k]):
            categories.append({
                "name": c,
                "total": cat_count[c],
                "paid": cat_paid.get(c, 0),
                "free": cat_free.get(c, 0),
                "avg_price_usdc": round(cat_total_price.get(c, 0.0) / max(cat_paid.get(c, 1), 1), 4),
            })

        n_total = len(tools)
        n_paid = sum(1 for t in tools if t.tier != "free")
        n_free = n_total - n_paid

        prices = [float(t.price_usdc) for t in tools if t.tier != "free"]
        return {
            "name": self.name,
            "tools": {
                "total": n_total,
                "paid": n_paid,
                "free": n_free,
                "by_category": categories,
            },
            "pricing": {
                "min_usdc": min(prices) if prices else None,
                "max_usdc": max(prices) if prices else None,
                "median_usdc": sorted(prices)[len(prices)//2] if prices else None,
            },
            "manifest": {
                "x402_version": 2,
                "primary_network": self.network,
                "primary_network_caip": self.network_caip,
                "secondary_network_caip": _NETWORK_CAIP["base"] if self.mainnet_receive_address and self.network != "base" else None,
                "dual_broadcast": bool(self.mainnet_receive_address and self.network != "base"),
                "receive_primary": self.receive_address,
                "receive_mainnet": self.mainnet_receive_address,
                "facilitator": self.facilitator_url,
            },
            "endpoints": {
                "mcp_remote": f"{(self.public_url or '').rstrip('/')}/mcp/",
                "x402_manifest": f"{(self.public_url or '').rstrip('/')}/.well-known/x402.json",
                "oauth_metadata": f"{(self.public_url or '').rstrip('/')}/.well-known/oauth-authorization-server",
                "oauth_protected_resource": f"{(self.public_url or '').rstrip('/')}/.well-known/oauth-protected-resource",
                "llms_txt": f"{(self.public_url or '').rstrip('/')}/llms.txt",
                "health": f"{(self.public_url or '').rstrip('/')}/health",
                "bazaar_mirror": f"{(self.public_url or '').rstrip('/')}/bazaar.json",
            },
            "discovery_surfaces": {
                "mcp_registry": "https://registry.modelcontextprotocol.io/v0/servers?search=onyx",
                "cdp_discovery": "https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources",
                "awesome_x402_pr": "https://github.com/xpaysh/awesome-x402/pull/295",
                "smithery": "https://smithery.ai/servers/dimitrilaouanis/onyx-mcp",
                "repo": "https://github.com/dimitrilaouanis-tech/onyx-mcp",
            },
        }

    def _dashboard_html(self, d: dict) -> str:
        cats = d["tools"]["by_category"]
        cat_rows = "\n".join(
            f"<tr><td><b>{c['name']}</b></td><td>{c['total']}</td>"
            f"<td>{c['paid']}</td><td>{c['free']}</td>"
            f"<td>${c['avg_price_usdc']}</td></tr>"
            for c in cats
        )
        manifest = d["manifest"]
        endpoints = d["endpoints"]
        ep_rows = "\n".join(
            f"<tr><td>{k}</td><td><a href='{v}'><code>{v}</code></a></td></tr>"
            for k, v in endpoints.items()
        )
        pricing = d["pricing"]
        return f"""<!doctype html><html><head><meta charset="utf-8">
<title>{d['name']} — live dashboard</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="Live dashboard for {d['name']} paid MCP server: {d['tools']['total']} tools across {len(cats)} categories, dual-broadcast x402 manifest, OAuth 2.1 DCR-compliant.">
<style>
:root {{ color-scheme: dark; }}
body {{ margin: 0; padding: 2rem; max-width: 1100px; margin-inline: auto;
       background:#0a0a0a; color:#e6e6e6;
       font: 14px/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
h1 {{ font-size: 1.8rem; margin: 0 0 .5rem; color:#fff; }}
h2 {{ font-size: 1.1rem; margin: 2.5rem 0 .8rem; color:#7fdbca; text-transform:uppercase; letter-spacing:.5px; }}
.sub {{ color:#888; margin-bottom:2rem; }}
.metrics {{ display:grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin: 1.5rem 0 2rem; }}
.metric {{ background:#161616; border:1px solid #2a2a2a; border-radius:8px; padding:1rem; }}
.metric .v {{ font-size:1.8rem; color:#fff; font-weight:600; }}
.metric .k {{ color:#888; font-size:.8rem; margin-top:.2rem; text-transform:uppercase; letter-spacing:.5px; }}
table {{ width:100%; border-collapse:collapse; margin:.5rem 0 1.5rem; background:#111; border:1px solid #2a2a2a; }}
th, td {{ padding:.6rem .8rem; text-align:left; border-bottom:1px solid #1f1f1f; }}
th {{ background:#171717; color:#7fdbca; font-weight:600; text-transform:uppercase; font-size:.75rem; letter-spacing:.5px; }}
tr:last-child td {{ border-bottom:none; }}
code, a {{ color:#79b8ff; word-break:break-all; }}
a {{ text-decoration:none; }}
a:hover {{ text-decoration:underline; }}
.ok {{ color:#3fb950; }}
.warn {{ color:#d29922; }}
.dim {{ color:#666; }}
.footer {{ color:#666; margin-top:3rem; padding-top:1.5rem; border-top:1px solid #2a2a2a; }}
</style>
</head><body>
<h1>{d['name']} — live dashboard</h1>
<div class="sub">Paid MCP server, x402 USDC settlement on Base. Public, real-time, no auth.</div>

<div class="metrics">
  <div class="metric"><div class="v">{d['tools']['total']}</div><div class="k">tools</div></div>
  <div class="metric"><div class="v">{d['tools']['paid']}</div><div class="k">paid</div></div>
  <div class="metric"><div class="v">{d['tools']['free']}</div><div class="k">free</div></div>
  <div class="metric"><div class="v">${pricing['min_usdc']}–${pricing['max_usdc']}</div><div class="k">price range</div></div>
</div>

<h2>Catalog by category</h2>
<table><thead><tr><th>Category</th><th>Total</th><th>Paid</th><th>Free</th><th>Avg paid price</th></tr></thead>
<tbody>
{cat_rows}
</tbody></table>

<h2>Manifest health</h2>
<table>
<tr><td>x402 version</td><td><span class="ok">v{manifest['x402_version']}</span> (latest spec)</td></tr>
<tr><td>Primary network</td><td><code>{manifest['primary_network']}</code> ({manifest['primary_network_caip']})</td></tr>
<tr><td>Dual broadcast</td><td>{'<span class="ok">yes — Base mainnet listed alongside primary</span>' if manifest['dual_broadcast'] else '<span class="warn">no — single network</span>'}</td></tr>
<tr><td>Primary payTo</td><td><code>{manifest['receive_primary']}</code></td></tr>
<tr><td>Mainnet payTo</td><td><code>{manifest['receive_mainnet'] or '(not set)'}</code></td></tr>
<tr><td>Facilitator</td><td><code>{manifest['facilitator']}</code></td></tr>
</table>

<h2>Endpoints</h2>
<table>
{ep_rows}
</table>

<h2>Discovery surfaces</h2>
<table>
{chr(10).join(f'<tr><td>{k}</td><td><a href="{v}"><code>{v}</code></a></td></tr>' for k,v in d['discovery_surfaces'].items())}
</table>

<div class="footer">
JSON of this dashboard: <a href="/dashboard.json"><code>/dashboard.json</code></a> ·
Try a free tool: <a href="/v1/onyx_x402_indexer_health"><code>GET /v1/onyx_x402_indexer_health</code></a> ·
<a href="/">main</a>
</div>

</body></html>"""

    # ---------- landing ----------

    def _landing_html(self) -> str:
        # Hero tools — show the highest-value 6 first, then the rest collapsed
        all_tools = sorted(self._tools.values(), key=lambda t: -float(t.price_usdc))
        hero_names = {
            "onyx_base_tx_explainer", "onyx_x402_receipt_verify", "onyx_solve_captcha",
            "onyx_mcp_oauth_audit", "onyx_base_token_risk_scan", "onyx_mcp_meta_call",
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
<meta name="description" content="{n_tools} x402-paid agent tools on Base mainnet. Captcha OCR, browser automation, on-chain primitives (tx explain/simulate, token risk), x402 ops (receipt verify, facilitator health, chain picker), agent identity + budget, MCP cross-server compare. Pay per call in USDC, no signup, no API key. MCP-native at /mcp/.">
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
  <span class="tag">{n_tools} tools live</span>
  <span class="tag">USDC settlement on Base</span>
  <span class="tag">x402 v2 dual-broadcast</span>
  <span class="tag">OAuth 2.1 DCR</span>
  <span class="tag">MCP-native at /mcp/</span>
  <span class="tag">No API key, no signup</span>
</div>

<div class="kpi" style="margin-top:18px">
  <span><a href="/dashboard" style="color:inherit;text-decoration:none">📊 <b>Live dashboard</b> — catalog, manifest health, indexer coverage</a></span>
  <span><a href="/bazaar" style="color:inherit;text-decoration:none">🏪 <b>x402 leaderboard</b> — every paid service in the ecosystem</a></span>
  <span><a href="/mcp/" style="color:inherit;text-decoration:none">🔌 <b>MCP endpoint</b> — Claude / Cursor / Cline</a></span>
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
<p><a href="/dashboard">/dashboard</a> · <a href="/dashboard.json">/dashboard.json</a> · <a href="/manifest">/manifest</a> · <a href="/.well-known/x402.json">/.well-known/x402.json</a> · <a href="/.well-known/oauth-authorization-server">/.well-known/oauth-authorization-server</a> · <a href="/.well-known/oauth-protected-resource">/.well-known/oauth-protected-resource</a> · <a href="/bazaar">/bazaar</a> · <a href="/llms.txt">/llms.txt</a> · <a href="/health">/health</a></p>

<h2>Settlement</h2>
<p class="wallet">USDC settles on {self.network} to <code>{self.receive_address}</code><br>
Facilitator: <code>{self.facilitator_url}</code></p>

<p style="margin-top:48px;color:#555;font-size:12px">
Built on the open-source <a href="https://github.com/dimitrilaouanis-tech/onyx-mcp">onyx-paid-mcp</a> framework.
Ship a paid MCP in 5 lines · MIT licensed.
</p>

</body></html>"""
