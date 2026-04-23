"""Onyx MCP server — action primitives for AI agents.

Exposes Onyx's battle-tested action workers as MCP tools over stdio.
This is the local-mode server (no payment gate). The paid HTTP version
lives in server_http.py (step 3: x402 gate).
"""
from __future__ import annotations

import asyncio
import json
import sys

import mcp.server.stdio
import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions

from tools import solve_captcha

app = Server("onyx-actions")


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="onyx_solve_captcha",
            description=(
                "Solve an image-based text captcha. Returns the recognized "
                "text. Backed by Onyx's production OCR stack (ddddocr). "
                "Typical accuracy 70-90% on standard web captchas."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "image_url": {
                        "type": "string",
                        "description": "URL of captcha image to fetch.",
                    },
                    "image_b64": {
                        "type": "string",
                        "description": "Base64-encoded captcha image bytes "
                                       "(use when agent already has the image).",
                    },
                },
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == "onyx_solve_captcha":
        result = solve_captcha(**arguments)
        return [types.TextContent(type="text", text=json.dumps(result))]
    raise ValueError(f"Unknown tool: {name}")


async def main():
    async with mcp.server.stdio.stdio_server() as (read, write):
        await app.run(
            read,
            write,
            InitializationOptions(
                server_name="onyx-actions",
                server_version="0.0.1",
                capabilities=app.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
