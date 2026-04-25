"""Onyx tool registry — drop-in single-file modules.

Each tool module exports:
    NAME: str          — MCP tool name (e.g. "onyx_solve_captcha")
    PRICE_USDC: str    — string decimal, "0.003"
    DESCRIPTION: str   — one-liner shown to agents
    INPUT_SCHEMA: dict — JSON schema for tools/list
    TIER: str          — "free" | "metered" | "premium"
    run(**kwargs) -> dict — business logic, raises ValueError on bad input
"""
from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType
from typing import Iterable


def discover() -> list[ModuleType]:
    """Walk this package, import every module, return those that look like tools."""
    found: list[ModuleType] = []
    for info in pkgutil.iter_modules(__path__):
        mod = importlib.import_module(f"{__name__}.{info.name}")
        if all(hasattr(mod, k) for k in ("NAME", "PRICE_USDC", "DESCRIPTION",
                                         "INPUT_SCHEMA", "TIER", "run")):
            found.append(mod)
    return found


def manifest(tools: Iterable[ModuleType]) -> list[dict]:
    return [
        {
            "name": t.NAME,
            "price_usdc": t.PRICE_USDC,
            "tier": t.TIER,
            "description": t.DESCRIPTION,
            "input_schema": t.INPUT_SCHEMA,
        }
        for t in tools
    ]
