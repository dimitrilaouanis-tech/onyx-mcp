# Stagehand × Onyx Actions — pay-per-call captcha hook (integration spec)

> Reference for the discussion thread following [browserbase/stagehand#2070](https://github.com/browserbase/stagehand/issues/2070) and [dimitrilaouanis-tech/onyx-mcp#1](https://github.com/dimitrilaouanis-tech/onyx-mcp/issues/1).

## Context

Stagehand agents on real-world signup/login flows hit image-captcha walls. Existing options (2captcha, Anti-captcha, self-hosted OCR) all assume a human admin holds an API key and tops up an account. For autonomous agents — particularly Coinbase AgentKit / Cloudflare Agents SDK ones with their own USDC wallets — none of these fit cleanly.

**x402 is the missing piece**: HTTP 402 Payment Required + EIP-3009 USDC authorization = the agent's wallet pays per call, no signup, no key.

## Proposed integration shape

A single optional config field in Stagehand's page/automation options:

```ts
const stagehand = new Stagehand({
  // ...existing options
  captcha: {
    solver: 'x402',                                    // enables the pay-per-call hook
    endpoint: 'https://onyx-actions.onrender.com/v1/onyx_solve_captcha',
    walletKey: process.env.STAGEHAND_AGENT_PRIVATE_KEY, // EOA with USDC on Base
    network: 'base',                                    // or 'base-sepolia' for testing
    maxPricePerSolve: '0.005',                         // USDC ceiling, optional
  },
});
```

Or vendor-neutral, parametrized to ANY x402 captcha provider:

```ts
captcha: {
  solver: 'x402',
  endpoint: '<any x402 captcha url>',
  walletKey: '<priv key>',
  // ... rest same
}
```

## Behavior

When Stagehand detects an image captcha:

1. Call the configured x402 endpoint with the captcha image (URL or base64).
2. Receive HTTP 402 with `payment-required` header (base64-encoded JSON challenge).
3. Decode the challenge, sign an EIP-3009 `transferWithAuthorization` USDC payload using the agent's private key.
4. Retry with `X-PAYMENT: <signed authorization>` header.
5. Receive HTTP 200 with the solved captcha text.
6. Type/submit the answer in the page flow.
7. Continue.

The full 402→sign→200 loop is ~150 lines in our reference client at [`examples/agent_pay.py`](examples/agent_pay.py).

## What Onyx Actions provides today

- `POST /v1/onyx_solve_captcha` — image captcha → text, ~30ms latency, ddddocr backend
- Pricing: $0.003/call USDC on Base
- Manifest: [`/.well-known/x402.json`](https://onyx-actions.onrender.com/.well-known/x402.json) — Bazaar-spec, `inputSchema` carried in the 402 challenge
- Streamable HTTP MCP at `/mcp/` for agents that prefer MCP tool-call shape
- Currently on Base sepolia for testing; mainnet flip is one env-var on our side

## What Stagehand would need to provide

A small middleware in the page-automation pipeline that:
- Detects image captcha (existing capability)
- Calls a configurable HTTP endpoint with the captcha image
- Handles the 402 → sign → retry loop using a wallet key the agent provides
- Inserts the result into the page

Minimal new dependency: `eth-account` (or equivalent EVM EIP-3009 signer) — most x402-aware agent stacks already have one. If Stagehand prefers no new EVM deps, the loop can be delegated to a callback the consumer registers.

## Vendor-neutral framing

Onyx Actions is one of several x402-capable captcha providers. The integration shape above is intentionally generic — `solver: 'x402'` should accept ANY URL that returns x402-compliant challenges. Stagehand consumers pick whichever provider best fits price/uptime/jurisdiction. This avoids vendor lock-in and keeps Stagehand neutral.

## Suggested split of work

- **Stagehand side**: design the `captcha.solver` config interface; wire the 402-loop middleware; document the contract for x402 providers.
- **Onyx side**: ensure the captcha endpoint matches whatever input shape Stagehand sends (URL vs base64); provide a Stagehand-specific README walkthrough; co-author tests against the live endpoint.

## Open questions for the call

1. Is `captcha.solver: 'x402'` the right level of abstraction, or should this be an existing pluggable solver interface in Stagehand?
2. Does Stagehand prefer to ship the EVM signing path, or delegate via callback to keep the dep tree clean?
3. Is there appetite for a Stagehand-side x402 helper module, or should it stay in user-land examples?
4. Sepolia for the integration tests, or mainnet for end-to-end demonstration?

## Reference material

- Onyx Actions live: https://onyx-actions.onrender.com
- Source: https://github.com/dimitrilaouanis-tech/onyx-mcp
- Runnable client demo: [`examples/agent_pay.py`](examples/agent_pay.py)
- x402 spec: https://github.com/coinbase/x402/tree/main/specs
- Coinbase x402 docs: https://docs.cdp.coinbase.com/x402/welcome
