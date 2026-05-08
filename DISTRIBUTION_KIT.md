# Onyx Actions — Distribution Kit (Day-1 Launch Pack)

Everything below is **copy-paste ready**. Each block lists target venue, paste content, and what to click. Total fire time end-to-end: ~12 minutes.

Last validated: 2026-05-08. **TODAY WE MADE: $0** — that's the line every announcement frames around.

---

## 1. Smithery — list the server (60 sec)

**URL:** https://smithery.ai/servers/new
1. Sign in with GitHub (will use your existing session)
2. Paste repo: `https://github.com/dimitrilaouanis-tech/onyx-mcp`
3. Smithery auto-detects `smithery.yaml`, indexes immediately
4. Verify at `https://smithery.ai/server/dimitrilaouanis-tech/onyx-mcp`

**Reaches:** Claude Desktop + Cursor + Cline + Goose users via deep-link install (4 clients in 1 listing).

---

## 2. PR #295 retitle — drops "SMS OTP" wording (30 sec)

**URL:** https://github.com/xpaysh/awesome-x402/pull/295
- Click pencil icon next to current title
- Replace with:

```
Add Onyx Actions — paid MCP, x402 USDC on Base + Solana (33 tools)
```

- Click Save
- Drop a comment to nudge the maintainer:

```
Updated title to reflect the actual scope. The endpoint
list (https://onyx-actions.onrender.com/.well-known/x402.json)
now exposes 33 services across Base + Solana on-chain
primitives (tx_explainer, token_risk_scan, jupiter_quote, etc.),
captcha OCR, browser automation, and 12 utility tools. All
routes carry inputSchema in the 402 challenge — x402scan-validator
clean. Ready to merge whenever convenient.
```

---

## 3. dev.to long-form post (3 min to publish)

**URL:** https://dev.to/new
**Tags:** `#x402 #mcp #ai #webdev`
**Cover image:** screenshot of `https://onyx-actions.onrender.com/`

**Title:**
```
I Shipped 33 Pay-Per-Call Endpoints Across Base + Solana — Here's the P&L and What Agents Actually Pay For
```

**Body:**
```markdown
TL;DR — 33 endpoints live, 5 of them Solana-native (tx_explainer, token_risk_scan, token_metadata, jupiter_quote, wallet_activity), pricing $0.0003 to $0.25 per call, USDC settlement via x402 protocol. Server: https://onyx-actions.onrender.com.

This is what I learned shipping it.

## Why x402 for an MCP server

Most MCP servers expect free unlimited use. That breaks at scale for any tool with real per-call expense (OCR, RPC reads, scraping infra). x402 lets the server return HTTP 402 with payment requirements, the agent signs an EIP-3009 USDC authorization, the server settles via a facilitator (Coinbase CDP for Base mainnet, x402.org for Sepolia), and the tool returns. **No API keys, no signup, no credit card.** The wallet IS the identity.

## The 33 tools, ranked by build effort

| Tool | Price | What it does |
|---|---|---|
| `onyx_base_tx_explainer` | $0.05 | Decode any Base tx into human-readable summary |
| `onyx_base_token_risk_scan` | $0.25 | Rug-vector scan for ERC-20s |
| `onyx_solana_tx_explainer` | $0.05 | Same on Solana — half OATP price |
| `onyx_solana_token_risk_scan` | $0.25 | SPL token rug check incl. pump.fun heuristic |
| `onyx_solana_jupiter_quote` | $0.001 | Best-route swap quote across all Solana DEXes |
| `onyx_solana_wallet_activity` | $0.002 | Recent N signatures, parsed + classified |
| `onyx_solve_captcha` | $0.003 | OCR captcha solve, ~30ms |
| `onyx_url_text` | $0.001 | Fetch URL, return clean main-content text |
| ... 25 more | $0.0003–$0.25 | DNS, WHOIS, email validate, IP geo, FX, browser ops |

## What the 402 challenge actually looks like

```
HTTP/1.1 402 Payment Required
payment-required: <base64-encoded JSON>
```

Decoded:
```json
{
  "x402Version": 2,
  "accepts": [{
    "scheme": "exact",
    "network": "eip155:8453",
    "asset": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
    "amount": "50000",
    "payTo": "0xA60939FFf9c04a61c0c0649943675e16A12D7074",
    "extra": {"inputSchema": {...}}
  }]
}
```

Coinbase Bazaar's discovery crawler reads `/.well-known/x402.json` and indexes every route. x402scan validates that each accept block carries an `inputSchema`.

## Three traps I hit

1. **x402.org/facilitator only does Base Sepolia.** For real USDC mainnet, you need Coinbase CDP API keys at portal.cdp.coinbase.com and `ONYX_FACILITATOR=https://api.cdp.coinbase.com/platform/v2/x402`.
2. **The lib's bazaar extension MUTATES the input_schema dict you pass to it.** It appends `"method"` to the `required[]` array of whatever you give it. Deepcopy at insertion or you ship a broken schema to crawlers. (Fixed in onyx-paid-mcp v0.1.x.)
3. **`/openapi.json` returning 500 silently kills x402scan auto-discovery.** FastAPI's pydantic introspection chokes on `request: Request` parameters in your paid handlers. Use `body: dict = Body(default_factory=dict)` instead.

## P&L

Mainnet USDC inbound to `0xA60939FFf9c04a61c0c0649943675e16A12D7074` today: **$0.00**.

That's not a typo. Shipping the server is ~5% of the work — the other 95% is being findable. Smithery, MCP Registry, awesome-x402 PR, x402.org/ecosystem, Coinbase Bazaar listing, Cloudflare Agents directory: every channel is 30-60 seconds of clicks but every click matters because no agent runtime ships with `https://onyx-actions.onrender.com/mcp/` in its default tool catalog.

Will update P&L weekly. **The P&L IS the post.**

Repo: https://github.com/dimitrilaouanis-tech/onyx-mcp
Server: https://onyx-actions.onrender.com
Try a tool: `curl -X POST https://onyx-actions.onrender.com/v1/onyx_solana_jupiter_quote -H "content-type: application/json" -d '{"input_mint":"So11111111111111111111111111111111111111112","output_mint":"EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v","amount":"1000000000"}'`
```

---

## 4. Hacker News — Show HN (60 sec)

**URL:** https://news.ycombinator.com/submit

**Title (≤80 chars):**
```
Show HN: Onyx Actions – 33 paid MCP endpoints, USDC via x402, no signup
```

**URL field:** `https://onyx-actions.onrender.com`

**First comment (post immediately yourself):**
```
Author here. This is a paid MCP server with 33 tools across Base + Solana
on-chain primitives, captcha OCR, browser automation, and standard web
utilities (DNS, WHOIS, email validation, IP geo, FX). Pricing is $0.0003–$0.25
per call. There's no API key, no signup, no rate-limited free tier — the agent
just calls the endpoint, gets HTTP 402 with payment requirements, signs an
EIP-3009 USDC authorization, retries, and the tool returns.

Try it without paying anything via the GET introspection card on any tool, e.g.
https://onyx-actions.onrender.com/v1/onyx_solana_jupiter_quote.

Today's mainnet inbound: $0. The server's been live for two weeks, x402scan
indexing is in flight, and I'm shipping a weekly P&L post to dev.to to track
what actually drives an agent to call you. Happy to answer anything about
shipping a paid MCP — the bazaar extension, the facilitator trap, the
schema-mutation bug in x402-py, etc.
```

---

## 5. Twitter/X thread (90 sec)

**URL:** https://x.com/compose/post

```
1/ I shipped 33 paid endpoints on x402 USDC across Base + Solana.

Mainnet inbound today: $0.00.

Here's what I'm learning.

🧵
```

```
2/ The shipping isn't the moat. Tool count isn't the moat.

x402engine has 38. agentsvc.io has 20. Voidly has 84. We're all crowded into the same $0.001-$0.10 band.

The moat is being findable when an agent searches.
```

```
3/ Free directories that index your `/.well-known/x402.json`:

– Coinbase Bazaar (auto-crawls after first paid call)
– x402scan.com
– agentic.market
– x402.org/ecosystem
– Smithery (for MCP-aware agents)

If your manifest returns empty, none of them see you.
```

```
4/ The 3 traps I hit:

– x402.org/facilitator is Sepolia-only. Mainnet needs CDP keys.
– The bazaar lib mutates your inputSchema dict in-place. Deepcopy.
– /openapi.json returning 500 silently kills x402scan validation.
```

```
5/ Fastest path I've found to first paid call:
1. Smithery listing (4 clients in 1)
2. awesome-x402 PR
3. dev.to weekly P&L post
4. Coinbase Bazaar surface area

Distribution > shipping. Will update.

Server: https://onyx-actions.onrender.com
Repo:   https://github.com/dimitrilaouanis-tech/onyx-mcp
```

---

## 6.5. Glama submission — UNBLOCKS PR #5761 (60 sec)

**URL:** https://glama.ai/mcp/servers
1. Sign in (GitHub OAuth)
2. Click "Submit MCP server"
3. Paste repo: `https://github.com/dimitrilaouanis-tech/onyx-mcp`
4. Glama auto-pulls the `Dockerfile` + runs the stdio entry → expects `python server.py` to start cleanly and respond to introspection. **Already verified locally: 33 tools discovered, no crashes.**
5. Once Glama check is green, drop a comment on `punkpeye/awesome-mcp-servers#5761` linking the green Glama check.

This is the only auth-walled prereq for that PR — and the maintainer's bot explicitly asked for it on 2026-05-03.

## 7. Reddit r/AI_Agents (60 sec)

**URL:** https://reddit.com/r/AI_Agents/submit?type=LINK

**Title:**
```
I shipped 33 paid agent endpoints on x402 USDC. Today's revenue: $0. Here's the playbook.
```

**Body / link:** https://onyx-actions.onrender.com (or your dev.to post if published first)

**First comment:**
```
Built a server where agents pay per call in USDC instead of needing API keys.
33 tools live, $0 revenue today. The interesting part isn't the build — it's
that distribution to agent-runtimes is its own moat.

Open to questions on the protocol, the schema-mutation bug, or what actually
makes an agent find a paid MCP.
```

---

## Order of fire (clicks ascending)

1. PR #295 retitle (30s) — fixes a stale-state liability first
2. Smithery (60s) — biggest leverage per click
3. HN Show (60s) — high variance, often produces nothing, sometimes produces 5k visits
4. Reddit (60s) — slower burn but durable
5. Twitter thread (90s) — tag @CoinbaseDev @x402_org @fewsats for amplification
6. dev.to (3 min) — durable SEO, archives well

After this batch, the only remaining auth-walled action is **portal.cdp.coinbase.com → 4 env vars on Render** for mainnet flip. Until then, all paid calls go to Sepolia (test USDC) and don't count toward TODAY WE MADE $X.
