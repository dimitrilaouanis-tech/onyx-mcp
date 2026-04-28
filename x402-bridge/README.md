# @onyx/x402-bridge

Universal stdio MCP bridge for any x402-paid HTTP MCP server.

Most MCP clients (Claude Desktop, Cline, Cursor) speak stdio and don't know how to handle the x402 `HTTP 402 → sign payment → retry` flow. This bridge sits between them. It exposes a remote x402-paid MCP as a local stdio MCP, transparently signing USDC payments with your wallet whenever a tool call costs money.

## Install + use

```jsonc
// claude_desktop_config.json (or .cline/config.json, etc.)
{
  "mcpServers": {
    "onyx-actions": {
      "command": "npx",
      "args": ["-y", "@onyx/x402-bridge", "https://onyx-actions.onrender.com/mcp/"],
      "env": {
        "X402_PRIVATE_KEY": "0x...",
        "X402_NETWORK": "base",
        "X402_MAX_PRICE_PER_CALL": "0.10"
      }
    }
  }
}
```

That's it. Every tool the remote server exposes appears as a stdio tool to the client. When a call returns 402, the bridge:

1. Reads the payment requirements from the response.
2. Checks `X402_MAX_PRICE_PER_CALL` (refuses if over limit).
3. Signs an EIP-3009 USDC authorization with the configured wallet.
4. Replays the call with the `X-PAYMENT` header attached.
5. Returns the result to the client.

No human in the loop. No account on the server. The wallet IS the identity.

## Why

- Claude / Cline / Cursor users get access to the entire paid-MCP ecosystem (Onyx Actions, Browserbase paid endpoints, Helius x402 streams, etc.) without waiting for native client support.
- Server authors get one canonical client they can point users at instead of writing five custom bridges.
- Payment flow is auditable: every settlement gets logged to stderr with tx hash and amount.

## Configuration

| env | required | default | meaning |
| --- | --- | --- | --- |
| `X402_PRIVATE_KEY` | yes | — | EVM private key (0x-prefixed hex) the bridge signs payments with |
| `X402_NETWORK` | no | `base` | `base` or `base-sepolia` |
| `X402_MAX_PRICE_PER_CALL` | no | `0.05` | Hard ceiling per call in USDC. Refuse if exceeded. |
| `X402_DAILY_BUDGET_USDC` | no | `1.00` | Stop signing if cumulative spend in 24h exceeds this. |
| `X402_LOG_LEVEL` | no | `info` | `debug`, `info`, `warn`, `error` |

## Status

`v0.1.0` — bridge core only. Roadmap:

- [ ] Cache settled payments to avoid double-charging on retries
- [ ] Per-tool budget caps
- [ ] Receipt persistence to local jsonl
- [ ] Human-confirmation mode for first call to unknown server

## License

MIT.
