"""Onyx MCP server — stdio entrypoint.

Exposes every tool registered in tools_pkg/ as an MCP tool over stdio.
This is the no-payment-gate variant (Glama / introspection / local dev).
The paid HTTP server lives in onyx_paid_mcp/app.py with x402 middleware.

Tool count is whatever tools_pkg.discover() returns — currently 33
across Base + Solana on-chain primitives, captcha OCR, browser
automation, and standard web utility (DNS, WHOIS, email, IP geo, FX).
"""
from __future__ import annotations

import asyncio
import json

import mcp.server.stdio
import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions

from tools_pkg import discover

# Discover once at startup — every module under tools_pkg/ that exports
# (NAME, PRICE_USDC, DESCRIPTION, INPUT_SCHEMA, TIER, run) registers itself.
_TOOLS = discover()
_BY_NAME = {t.NAME: t for t in _TOOLS}

app = Server("onyx-actions")


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name=t.NAME,
            description=t.DESCRIPTION,
            inputSchema=t.INPUT_SCHEMA,
        )
        for t in _TOOLS
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
    tool = _BY_NAME.get(name)
    if tool is None:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"unknown tool: {name}",
                             "available": sorted(_BY_NAME.keys())}),
        )]
    try:
        result = tool.run(**(arguments or {}))
    except ValueError as e:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": str(e), "tool": name}),
        )]
    except Exception as e:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"{type(e).__name__}: {e}", "tool": name}),
        )]
    return [types.TextContent(type="text", text=json.dumps(result, default=str))]


async def main() -> None:
    async with mcp.server.stdio.stdio_server() as (read, write):
        await app.run(
            read,
            write,
            InitializationOptions(
                server_name="onyx-actions",
                server_version="0.2.0",
                capabilities=app.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
