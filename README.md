# onyx-paid-mcp — build a paid MCP server in 5 lines

[![PyPI](https://img.shields.io/pypi/v/onyx-paid-mcp.svg)](https://pypi.org/project/onyx-paid-mcp/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![x402](https://img.shields.io/badge/payments-x402-blue.svg)](https://x402.org)

USDC settlement on Base. No Stripe, no API keys, no signup flow. Charge AI agents per call directly through the protocol they already speak.

```python
from onyx_paid_mcp import App

app = App(
    name="hello-paid-mcp",
    receive_address="0xYourBaseWallet",
    network="base",   # or "base-sepolia" for free testnet
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
    app.serve(port=8080)
```

That's it. `pip install onyx-paid-mcp`, point at any wallet address, decorate any function. You now have:

- **Streamable HTTP MCP** at `/mcp/` — installable in Claude Desktop, Cursor, Cline, mcp-use
- **REST endpoint** at `/v1/<tool>` — for non-MCP agents
- **HTTP 402 gate** that charges your wallet per call in USDC
- **Bazaar-discoverable manifest** at `/.well-known/x402.json` — Coinbase auto-indexes
- **Free introspection** at `/`, `/manifest`, `/health`

## Why

Every MCP today is free-as-in-unmetered. That breaks at scale for any tool with real per-call expense (OCR, scraping infra, LLM passes, anything backed by a physical resource). `onyx-paid-mcp` lets you charge directly through the agent's wallet — the same way a paywall works in a browser, except the wallet signs an EIP-3009 USDC authorization instead of pulling out a credit card.

## Install

```bash
pip install onyx-paid-mcp
```

Generate a Base wallet (`gen_wallet.py` in this repo, or any EVM wallet generator), set it as `ONYX_RECEIVE`, run your tool. Agents pay you in USDC the second they call.

## Reference implementation

[`onyx-actions`](https://onyx-actions.onrender.com) — the live server using this framework. 12 paid tools across captcha, SMS OTP, HLR phone validation, URL text extraction, DNS, WHOIS, IP geo, email validation, password strength, UA parsing, FX convert. All shipped as one-file modules in `tools_pkg/`.

| Tool | Price |
|---|---|
| `onyx_solve_captcha` | $0.003 |
| `onyx_sms_verify` | $0.050 |
| `onyx_hlr_lookup` | $0.005 |
| `onyx_url_text` | $0.001 |
| `onyx_url_unshorten` | $0.0005 |
| `onyx_whois` | $0.001 |
| `onyx_dns_lookup` | $0.0005 |
| `onyx_email_validate` | $0.0008 |
| `onyx_ip_geolocate` | $0.0008 |
| `onyx_fx_convert` | $0.0008 |
| `onyx_password_strength` | $0.0003 |
| `onyx_user_agent_parse` | $0.0003 |

Smithery listing: <https://smithery.ai/servers/dimitrilaouanis/onyx-mcp>

## How agents call you

```bash
curl -X POST https://your-server.example.com/v1/echo \
  -H "content-type: application/json" \
  -d '{"text":"hi"}'
# → 402 Payment Required, body has accepts[] describing price + asset + payTo

# Agent's x402 SDK signs an EIP-3009 authorization, retries:
curl -X POST https://your-server.example.com/v1/echo \
  -H "content-type: application/json" \
  -H "X-PAYMENT: <signed authorization>" \
  -d '{"text":"hi"}'
# → 200, {"echoed": "hi"}
```

Any x402-aware client SDK (Coinbase CDP, Cloudflare Agent SDK, etc.) handles the loop in ~5 lines. Agents don't need to know your URL — the Coinbase Bazaar crawler picks up your `/.well-known/x402.json` from on-chain settled payments.

## Configure

The framework defaults are sane. Customize via constructor or env:

| Field | Default | Note |
|---|---|---|
| `name` | required | shows up in MCP, manifest, landing page |
| `receive_address` | required | where USDC settles |
| `network` | `base-sepolia` | or `base` for mainnet |
| `facilitator_url` | x402.org public | swap for Coinbase CDP / xpay / your own |
| `public_url` | None | sets the canonical URL in manifests |
| `description` | empty | short one-liner |
| `homepage` | None | optional landing page URL |

## Self-hosting checklist

1. Generate or pick a Base wallet (just an address — private key never leaves your machine; this is a receive-only flow)
2. Funded wallet not required to receive — only senders need USDC
3. Pick a host: Render free tier works; Fly.io machines for always-on; Cloudflare Tunnel + Oracle ARM for zero-cost-zero-cold-start
4. `pip install onyx-paid-mcp`, write your `app.py`, deploy
5. Submit `https://your-server/.well-known/x402.json` to Coinbase Bazaar — first settled payment auto-indexes you everywhere

## Status

`v0.1.0` — released April 2026. Battle-tested on `onyx-actions.onrender.com` (live since Apr 24).

## License

MIT — see [LICENSE](LICENSE).
