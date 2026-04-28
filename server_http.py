"""onyx-actions — reference implementation built on onyx_paid_mcp.

Loads every tool in tools_pkg/ and exposes them as paid MCP via the
framework. Live at https://onyx-actions.onrender.com.

Run:
    uvicorn server_http:app --host 0.0.0.0 --port 8080
"""
from __future__ import annotations

import os
from pathlib import Path

# ---- env (.env loader, no extra dependency) -----------------------------

env_file = os.environ.get("ONYX_ENV_FILE", ".env")
env_path = Path(__file__).parent / env_file
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

# ---- App ---------------------------------------------------------------

from onyx_paid_mcp import App, Tool

app_obj = App(
    name="onyx-actions",
    receive_address=os.environ.get("ONYX_RECEIVE_ADDRESS")
    or (_ for _ in ()).throw(RuntimeError("ONYX_RECEIVE_ADDRESS missing")),
    network=os.environ.get("ONYX_NETWORK", "base-sepolia").lower(),
    facilitator_url=os.environ.get("ONYX_FACILITATOR_URL"),
    public_url=os.environ.get("ONYX_PUBLIC_URL", "https://onyx-actions.onrender.com"),
    description="Paid agent tools over x402 USDC. Reference impl of onyx-paid-mcp.",
    homepage="https://github.com/dimitrilaouanis-tech/onyx-mcp",
)

# ---- Auto-discover every tools_pkg/*.py ---------------------------------

import tools_pkg

for mod in tools_pkg.discover():
    app_obj.add(Tool(
        name=mod.NAME,
        price_usdc=mod.PRICE_USDC,
        description=mod.DESCRIPTION,
        input_schema=mod.INPUT_SCHEMA,
        handler=mod.run,
        tier=mod.TIER,
    ))

# ASGI app uvicorn binds to
app = app_obj.build_asgi()
