"""Minimal example — one paid tool, five real lines.

Run:
    pip install onyx-paid-mcp
    export ONYX_RECEIVE=0xYourBaseWallet
    python single_tool.py

Then any agent on Base can call POST /v1/echo and pay $0.001 USDC per call.
"""
import os
from onyx_paid_mcp import App

app = App(
    name="hello-paid-mcp",
    receive_address=os.environ["ONYX_RECEIVE"],
    network="base-sepolia",
    description="Demo paid MCP — echoes whatever you send.",
)


@app.tool(
    name="echo",
    price_usdc="0.001",
    description="Returns whatever string you send. Costs one tenth of a cent.",
    input_schema={
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
)
def echo(text: str) -> dict:
    return {"echoed": text}


if __name__ == "__main__":
    app.serve(host="0.0.0.0", port=8080)
