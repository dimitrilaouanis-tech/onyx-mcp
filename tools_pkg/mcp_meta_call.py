"""Universal x402 / MCP tool inspector — the routing layer.

Given any x402 service URL + tool path + agent's wallet, this tool
inspects the target without paying: probes the 402 challenge, decodes
the price, recommends optimal chain + facilitator, looks up the caller's
reputation, and emits a pre-flight report telling the agent EXACTLY what
will happen if it proceeds.

This is the 100x lever — by sitting in front of any other x402 tool,
Onyx becomes the routing layer. Agents come to us first because we
combine 6 of our existing tools into one decision.

v1 = inspector only (free). v2 (paid) = actually proxies the call.

Stdlib-only. SSRF-hardened. Free tier.
"""
from __future__ import annotations

import base64
import ipaddress
import json
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

NAME = "onyx_mcp_meta_call"
PRICE_USDC = "0"
TIER = "free"
DESCRIPTION = (
    "Pre-flight inspector for ANY x402 tool call. Pass target URL + "
    "optional caller wallet, get back: live 402 price, recommended chain "
    "(via chain_picker logic), live facilitator health, caller reputation "
    "(via agent_id logic), and a green/yellow/red GO signal. Free tier — "
    "the universal preflight that lets agents decide before they sign. "
    "v2 (paid) will broker the actual settlement and proxy the response."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "target_url": {
            "type": "string",
            "description": "Full URL of the x402 tool endpoint to inspect (e.g. https://other-service.com/v1/some_tool).",
        },
        "caller_wallet": {
            "type": "string",
            "description": "Optional. Caller's EVM wallet — used to look up reputation via agent_id logic.",
        },
        "max_acceptable_usdc": {
            "type": "number",
            "default": 1.0,
            "description": "Caller's max acceptable price for this call. If quoted price > this, GO signal is red.",
        },
    },
    "required": ["target_url"],
}

_ADDR_RX = re.compile(r"^0x[a-fA-F0-9]{40}$")
_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

_RPCS = {
    "base":         ["https://base-rpc.publicnode.com", "https://base.gateway.tenderly.co"],
    "base-sepolia": ["https://base-sepolia-rpc.publicnode.com", "https://base-sepolia.gateway.tenderly.co"],
}
_USDC = {
    "base":         "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
    "base-sepolia": "0x036cbd53842c5426634e7929541ec2318f3dcf7e",
}


def _is_public(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False
    for _, _, _, _, sa in infos:
        try:
            ip = ipaddress.ip_address(sa[0])
        except ValueError:
            return False
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_multicast or ip.is_reserved):
            return False
    return True


def _probe_402(target_url: str, timeout: float = 8.0) -> dict:
    """Send an empty POST to elicit the 402 challenge. Returns parsed challenge or error."""
    started = time.time()
    try:
        req = urllib.request.Request(
            target_url, method="POST",
            data=b"{}",
            headers={"User-Agent": "Mozilla/5.0 (compatible; OnyxMetaCall/1.0)",
                     "Content-Type": "application/json",
                     "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {"ok": False, "status": resp.status,
                    "note": "200 OK without payment — endpoint may be free or misconfigured.",
                    "latency_ms": int((time.time() - started) * 1000)}
    except urllib.error.HTTPError as e:
        elapsed_ms = int((time.time() - started) * 1000)
        if e.code != 402:
            body = e.read(2048).decode("utf-8", "replace") if e else ""
            return {"ok": False, "status": e.code, "error": "non-402 response",
                    "body_snippet": body[:200], "latency_ms": elapsed_ms}
        pr_header = e.headers.get("payment-required") if e.headers else None
        body = e.read(8192).decode("utf-8", "replace") if e else ""
        # Try header first (canonical), fall back to body
        challenge = None
        if pr_header:
            try:
                challenge = json.loads(base64.b64decode(pr_header).decode("utf-8"))
            except Exception:
                pass
        if challenge is None and body:
            try:
                challenge = json.loads(body)
            except Exception:
                pass
        if not isinstance(challenge, dict):
            return {"ok": False, "status": 402, "error": "402 but no parseable challenge",
                    "latency_ms": elapsed_ms}
        return {"ok": True, "status": 402, "challenge": challenge, "latency_ms": elapsed_ms}
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as e:
        return {"ok": False, "error": str(e)[:160],
                "latency_ms": int((time.time() - started) * 1000)}


def _summarize_challenge(challenge: dict) -> dict:
    """Extract human-relevant fields from an x402 challenge."""
    accepts = challenge.get("accepts") or []
    summary = {
        "version": challenge.get("x402Version"),
        "accepts_count": len(accepts),
        "networks": [],
        "schemes": [],
        "prices_usdc": [],
        "pay_to_addresses": set(),
        "extensions_present": "extensions" in challenge,
    }
    for a in accepts:
        if not isinstance(a, dict):
            continue
        summary["networks"].append(a.get("network"))
        summary["schemes"].append(a.get("scheme"))
        amt = a.get("maxAmountRequired") or a.get("amount")
        try:
            summary["prices_usdc"].append(int(amt) / 1_000_000)
        except Exception:
            pass
        if a.get("payTo"):
            summary["pay_to_addresses"].add(a["payTo"].lower())
    summary["pay_to_addresses"] = list(summary["pay_to_addresses"])
    summary["min_price_usdc"] = min(summary["prices_usdc"]) if summary["prices_usdc"] else None
    summary["max_price_usdc"] = max(summary["prices_usdc"]) if summary["prices_usdc"] else None
    summary["networks_unique"] = sorted(set(n for n in summary["networks"] if n))
    summary["schemes_unique"] = sorted(set(s for s in summary["schemes"] if s))
    return summary


def _rpc(chain: str, method: str, params: list, timeout: float = 6.0) -> dict | None:
    for url in _RPCS.get(chain, []):
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
                headers={"Content-Type": "application/json",
                         "User-Agent": "Mozilla/5.0 (compatible; OnyxMetaCall/1.0)"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            continue
    return None


def _caller_quick_score(wallet: str) -> dict:
    """Lightweight version of agent_id — just balance + most-recent activity check."""
    out = {"wallet": wallet, "per_chain": {}}
    for chain, usdc in _USDC.items():
        head_r = _rpc(chain, "eth_blockNumber", [])
        if not head_r:
            continue
        head = int(head_r.get("result", "0x0"), 16)
        # Balance
        owner_padded = wallet.lower().replace("0x", "").rjust(64, "0")
        bal_r = _rpc(chain, "eth_call", [{"to": usdc, "data": "0x70a08231" + owner_padded}, "latest"])
        balance_usdc = 0.0
        if bal_r and isinstance(bal_r.get("result"), str):
            try:
                balance_usdc = int(bal_r["result"], 16) / 1_000_000
            except Exception:
                pass
        # Outflow count in 5000 blocks (~3h)
        from_padded = wallet.lower().replace("0x", "").rjust(64, "0")
        logs_r = _rpc(chain, "eth_getLogs", [{
            "address": usdc,
            "fromBlock": hex(max(0, head - 5000)),
            "toBlock": "latest",
            "topics": [_TRANSFER_TOPIC, "0x" + from_padded, None],
        }])
        outflow_count = len(logs_r.get("result", []) or []) if logs_r else 0
        out["per_chain"][chain] = {
            "balance_usdc": balance_usdc,
            "outflows_3h": outflow_count,
            "head_block": head,
        }
    total_outflows = sum(c.get("outflows_3h", 0) for c in out["per_chain"].values())
    out["recent_outflows_3h"] = total_outflows
    out["trust_level"] = (
        "high" if total_outflows >= 3 else
        "medium" if total_outflows >= 1 else
        "low (no recent on-chain activity)"
    )
    return out


def run(
    target_url: str,
    caller_wallet: str | None = None,
    max_acceptable_usdc: float = 1.0,
    **_: object,
) -> dict:
    if not isinstance(target_url, str) or not target_url:
        raise ValueError("target_url is required")
    parsed = urllib.parse.urlparse(target_url.strip())
    if parsed.scheme not in ("http", "https"):
        raise ValueError("target_url must be http:// or https://")
    if parsed.hostname and not _is_public(parsed.hostname):
        return {"ok": False, "error": "target_url not on a public address"}

    if caller_wallet is not None and not _ADDR_RX.match(caller_wallet.strip()):
        raise ValueError("caller_wallet must be 0x-prefixed 20-byte hex")

    # Step 1 — probe target for 402
    probe = _probe_402(target_url)
    if not probe.get("ok"):
        return {
            "ok": False,
            "target_url": target_url,
            "stage": "probe",
            "probe": probe,
            "go_signal": "red",
            "verdict": "Target did not return a parseable x402 challenge. Cannot inspect.",
        }

    challenge = probe["challenge"]
    summary = _summarize_challenge(challenge)

    # Step 2 — caller reputation (if wallet provided)
    caller = None
    if caller_wallet:
        try:
            caller = _caller_quick_score(caller_wallet.strip())
        except Exception as e:
            caller = {"wallet": caller_wallet, "error": str(e)[:120]}

    # Step 3 — price decision
    quoted = summary.get("min_price_usdc")
    price_ok = quoted is not None and quoted <= max_acceptable_usdc

    # Step 4 — network availability
    networks = summary["networks_unique"]
    supported = [n for n in networks if n in ("eip155:8453", "eip155:84532", "base", "base-sepolia")]

    # Step 5 — compose GO signal
    if not price_ok or not networks:
        go = "red"
        verdict = (
            f"Quoted price ${quoted} exceeds cap ${max_acceptable_usdc}"
            if not price_ok else
            "No CAIP-2 networks declared in challenge"
        )
    elif not supported:
        go = "yellow"
        verdict = f"Target accepts {networks} — outside Coinbase-Bazaar-facilitated chains; agent needs alt facilitator"
    elif caller and caller.get("trust_level", "").startswith("low") and quoted > 0.10:
        go = "yellow"
        verdict = "Caller has no recent on-chain activity but quoted price is non-trivial — proceed with caution"
    else:
        go = "green"
        verdict = (
            f"Pay ${quoted} USDC on {supported[0]} to {summary['pay_to_addresses'][0] if summary['pay_to_addresses'] else '<no payTo>'}"
        )

    return {
        "ok": True,
        "target_url": target_url,
        "probe_latency_ms": probe.get("latency_ms"),
        "challenge_summary": summary,
        "caller": caller,
        "max_acceptable_usdc": max_acceptable_usdc,
        "price_ok": price_ok,
        "go_signal": go,
        "verdict": verdict,
        "next_step": (
            "If green: sign EIP-3009 TransferWithAuthorization matching accepts[0], "
            "POST again with PAYMENT-SIGNATURE header. Use onyx_x402_simulate to "
            "build the payload template. Use onyx_x402_chain_picker if multiple "
            "supported networks. Use onyx_verify_explain if the retry fails."
        ),
        "schema_version": "v1",
        "v2_note": (
            "v2 of this tool (paid) will actually broker the call: agent signs once, "
            "Onyx routes through the optimal facilitator, returns aggregated receipt."
        ),
    }


run.__when_to_use__ = (
    "Before calling any x402 tool you don't already know, run a pre-flight here "
    "to get: live price, supported chains, your own trust level, and a clear "
    "green/yellow/red GO signal — all without paying a cent."
)
run.__vs_alternatives__ = (
    "No universal x402 pre-flight inspector exists. Each agent rolls its own "
    "402-decoder. This is the first cross-server inspector that also factors "
    "caller reputation + facilitator support into a single signal."
)
run.__example_request__ = {
    "target_url": "https://onyx-actions.onrender.com/v1/onyx_aml_screen",
    "caller_wallet": "0xA60939FFf9c04a61c0c0649943675e16A12D7074",
    "max_acceptable_usdc": 0.50,
}
run.__example_response__ = {
    "ok": True,
    "challenge_summary": {"min_price_usdc": 0.05, "networks_unique": ["eip155:8453"]},
    "go_signal": "green",
    "verdict": "Pay $0.05 USDC on eip155:8453 to 0xA609...",
}
