"""Generic workflow chainer — connect any sequence of Onyx tools in one call.

This is the dot-connector. Agent submits a list of step{tool, args} and the
workflow runs them in sequence, passing the previous step's output into the
next via $prev or named bindings. Single x402 payment covers the entire
chain.
"""
from __future__ import annotations

import time
from typing import Any

NAME = "onyx_agent_workflow"
PRICE_USDC = "0.020"
TIER = "metered"
DESCRIPTION = (
    "Run a multi-step workflow across Onyx tools in one paid call. "
    "Each step names a tool and its args; later steps can reference earlier "
    "outputs via {\"$ref\": \"step_N.field\"} or {\"$prev\": \"field\"}. "
    "Saves agents the round-trip + per-call gas of N separate x402 settles "
    "when they know the chain in advance — e.g. validate email → check "
    "domain DNS → solve captcha → fetch SMS OTP, all atomic. Stops on first "
    "step error and returns partial results. Cheaper than the unit-call "
    "sum because it bundles."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "steps": {
            "type": "array",
            "description": "Ordered list of {tool, args}",
            "items": {
                "type": "object",
                "properties": {
                    "tool": {"type": "string"},
                    "args": {"type": "object"},
                },
                "required": ["tool"],
            },
            "minItems": 1,
            "maxItems": 10,
        }
    },
    "required": ["steps"],
}


def _resolve(value: Any, prev: Any, results: list[dict]) -> Any:
    """Resolve {$ref}, {$prev} placeholders in step args."""
    if isinstance(value, dict):
        if set(value.keys()) == {"$prev"}:
            field = value["$prev"]
            if isinstance(prev, dict) and field in prev:
                return prev[field]
            return None
        if set(value.keys()) == {"$ref"}:
            ref = value["$ref"]
            try:
                step_str, field = ref.split(".", 1)
                idx = int(step_str.replace("step_", ""))
                return results[idx].get("output", {}).get(field)
            except (ValueError, IndexError, KeyError):
                return None
        return {k: _resolve(v, prev, results) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve(v, prev, results) for v in value]
    return value


def run(steps: list[dict], **_: object) -> dict:
    if not isinstance(steps, list) or not steps:
        raise ValueError("steps must be a non-empty list")
    if len(steps) > 10:
        raise ValueError("max 10 steps per workflow")
    # Late import to avoid circular registry import at module load time
    from . import discover
    by_name = {m.NAME: m for m in discover()}

    started = time.time()
    results: list[dict] = []
    prev_output: Any = None
    overall_ok = True

    for i, step in enumerate(steps):
        tool_name = step.get("tool")
        args_in = step.get("args") or {}
        if tool_name not in by_name:
            results.append({"step": i, "tool": tool_name, "ok": False,
                            "error": f"unknown tool: {tool_name}"})
            overall_ok = False
            break
        if tool_name == "onyx_agent_workflow":
            results.append({"step": i, "tool": tool_name, "ok": False,
                            "error": "recursion not allowed"})
            overall_ok = False
            break
        resolved = _resolve(args_in, prev_output, results)
        try:
            output = by_name[tool_name].run(**(resolved or {}))
            results.append({"step": i, "tool": tool_name, "ok": True,
                            "output": output})
            prev_output = output
        except Exception as e:
            results.append({"step": i, "tool": tool_name, "ok": False,
                            "error": f"{type(e).__name__}: {e}"})
            overall_ok = False
            break

    return {
        "ok": overall_ok,
        "steps_ran": len(results),
        "steps_total": len(steps),
        "results": results,
        "elapsed_ms": int((time.time() - started) * 1000),
    }
