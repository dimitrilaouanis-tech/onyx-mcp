"""onyx-paid-mcp — build a paid MCP server in 5 lines.

Charge agents in USDC over x402 for any function you expose. Auto-generates:
  - Streamable HTTP MCP at /mcp/  (what Claude Desktop / Cursor / Cline install)
  - REST endpoint at /v1/<tool>   (for non-MCP agents)
  - /.well-known/x402.json        (Coinbase Bazaar discovery manifest)
  - /manifest, /health, HTML landing — introspection

Usage:
    from onyx_paid_mcp import App, tool

    app = App(
        name="my-mcp",
        receive_address="0xYourBaseWallet",
        network="base",  # or "base-sepolia" for free testnet
    )

    @app.tool(
        name="echo",
        price_usdc="0.001",
        description="Returns whatever you send.",
        input_schema={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
    )
    def echo(text: str) -> dict:
        return {"echoed": text}

    if __name__ == "__main__":
        app.serve(host="0.0.0.0", port=8080)

That's the whole thing. USDC settlement on Base, no Stripe, no API keys.
"""
from __future__ import annotations

from .app import App, Tool, tool
from .version import __version__

__all__ = ["App", "Tool", "tool", "__version__"]
