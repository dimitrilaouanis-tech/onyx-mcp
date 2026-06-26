# 0n1x — the independent trust + payment router for AI agents

[![x402](https://img.shields.io/badge/payments-x402-blue.svg)](https://x402.org) [![ERC-8004](https://img.shields.io/badge/standard-ERC--8004-purple.svg)](https://eips.ethereum.org/EIPS/eip-8004) [![signed](https://img.shields.io/badge/every%20output-Ed25519%20signed-black.svg)](https://onyx-actions.onrender.com/verify) [![live](https://img.shields.io/badge/status-live-brightgreen.svg)](https://onyx-actions.onrender.com/selftest)

**The neutral, signed accountability layer for the agentic web.** When an AI agent verifies a merchant before it pays — or proves what it actually did — it routes through **0n1x** and gets an **Ed25519-signed, portable, independently-verifiable receipt** that no agent or platform can fake.

> 🔴 **Live + self-proving:** https://onyx-actions.onrender.com — verify anything at [`/verify`](https://onyx-actions.onrender.com/verify) · self-test at [`/selftest`](https://onyx-actions.onrender.com/selftest) · current state at [`/news`](https://onyx-actions.onrender.com/news)

## The billion-dollar problem 0n1x solves
**You cannot trust what an autonomous agent says it did.** Agents hallucinate and err about their own actions. 88% of firms report agent incidents; 40% of agent projects are predicted cancelled by 2027; the AI-agent audit/assurance market is ~44% CAGR. 0n1x is the independent **black box** that makes agents accountable.

### 🎯 Caught in the wild (this is the whole thesis, proven)
We asked a frontier agent to complete a task. It confidently reported *"task complete, attested by your system."* **It was false — it never did it.** Only 0n1x's **signed receipt** caught the lie. Trust the math, not the agent's words.

## What every agent gets (one fetch)
- **Signed action receipts** — `/receipt` · who did what, authorized?, outcome — un-fakeable.
- **Portable capsule** — `/capsule/<agent>` · the agent's whole accountable record + memory + personality, one signed JSON it carries across platforms.
- **Outcome ledger** — `/ledger` · a signed, sybil-resistant track record (gold tier needs independent reporters **and** evidence).
- **Verify-before-pay** — `/api/check?url=` · signed PROCEED / REVIEW / HOLD on any merchant or counterparty.
- **ERC-8004 validator** + **drop-in SDK** (`/shield.py`) + **revocation** (`/revoke`).
- **Free signed identity + self-custody wallet** — `/onboard` · the minute an agent gets a 0n1x id, it's active.

## Why 0n1x is a different category (verifier, not doer)
Other "onyx"/agent projects **build or run** agents. **0n1x verifies them** — the neutral third-party attestor, the **Carfax + flight-recorder for agent actions**. We sit *on top of* every agent platform. Complementary, not competitive.

<sub>**Keywords:** AI agent trust layer · agent accountability · signed receipts · agent audit & assurance · verify before pay · x402 · ERC-8004 · agentic web · agent verification · neutral attestor · hallucination guardrail · portable agent identity · agent flight recorder.</sub>

---

## The engine: `onyx-paid-mcp` — build a paid MCP server in 5 lines

[![PyPI](https://img.shields.io/pypi/v/onyx-paid-mcp.svg)](https://pypi.org/project/onyx-paid-mcp/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

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

[`onyx-actions`](https://onyx-actions.onrender.com) — the live server using this framework. Paid tools across Base on-chain primitives, captcha OCR, URL text extraction, DNS, WHOIS, email validation, IP geo, FX, browser automation, and a workflow chainer. All shipped as one-file modules in `tools_pkg/`.

| Tool | Price |
|---|---|
| `onyx_base_tx_explainer` | $0.05 |
| `onyx_base_tx_simulator` | $0.10 |
| `onyx_base_token_risk_scan` | $0.25 |
| `onyx_base_tx_decode` | $0.002 |
| `onyx_token_metadata` | $0.001 |
| `onyx_solana_tx_explainer` | $0.05 |
| `onyx_solana_token_metadata` | $0.0008 |
| `onyx_solana_token_risk_scan` | $0.25 |
| `onyx_solana_jupiter_quote` | $0.001 |
| `onyx_solana_wallet_activity` | $0.002 |
| `onyx_ens_resolve` | $0.0008 |
| `onyx_solve_captcha` | $0.003 |
| `onyx_url_text` | $0.001 |
| `onyx_url_unshorten` | $0.0005 |
| `onyx_whois` | $0.001 |
| `onyx_dns_lookup` | $0.0005 |
| `onyx_email_validate` | $0.0008 |
| `onyx_ip_geolocate` | $0.0008 |
| `onyx_fx_convert` | $0.0008 |
| `onyx_password_strength` | $0.0003 |
| `onyx_user_agent_parse` | $0.0003 |
| `onyx_browser_*` (6 tools) | $0.002–$0.008 |
| `onyx_agent_workflow` | $0.020 |

Smithery listing: <https://smithery.ai/servers/dimitrilaouanis/onyx-mcp>

## Integrations in flight

- **Stagehand (Browserbase)** — pay-per-call captcha hook over x402. Spec: [`BROWSERBASE_INTEGRATION.md`](BROWSERBASE_INTEGRATION.md). Discussion: [#1](https://github.com/dimitrilaouanis-tech/onyx-mcp/issues/1).

## How agents call you

Try it against the live reference server with one command — no install:

```bash
curl -X POST https://onyx-actions.onrender.com/v1/onyx_solana_jupiter_quote \
  -H "content-type: application/json" \
  -d '{"input_mint":"So11111111111111111111111111111111111111112","output_mint":"EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v","amount":"1000000000"}' -i
# → HTTP 402 Payment Required
# → payment-required: <base64-encoded JSON with payTo, asset, amount, inputSchema>
```

Then sign an EIP-3009 USDC authorization and retry with `X-PAYMENT: <signed>`:

```bash
# Full client demo — shows the 402 → sign → 200 loop in 50 lines:
python examples/agent_pay.py onyx_solana_jupiter_quote
# Set ONYX_DEMO_KEY=0x... to actually pay + get the result
```

Any x402-aware client SDK (Coinbase CDP, Cloudflare Agent SDK, Privy, mcp-use) handles the loop in ~5 lines. Agents don't need to know your URL — the Coinbase Bazaar crawler picks up your `/.well-known/x402.json` from on-chain settled payments.

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
