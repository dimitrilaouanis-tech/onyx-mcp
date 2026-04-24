# Onyx Actions — Paid Tools for AI Agents

Agent primitives backed by **physical carrier SIMs**, not VMs or proxies. Pay per call in USDC on Base via [x402](https://x402.org). No API keys, no accounts, no subscriptions. HTTP 402 → sign a USDC transfer → 200. That's the whole auth flow.

## Tools

| Tool | Price | What it does |
|------|-------|--------------|
| `onyx_sms_verify` | $0.050 USDC | Receive an SMS OTP on a real phone + real SIM + real tower. No VoIP, no virtual numbers. |
| `onyx_solve_captcha` | $0.003 USDC | Solve an image-based text captcha. OCR via ddddocr (~30ms, 70–90% accuracy). |

## The positioning

Most MCP servers on directories today wrap somebody else's API — the tool exists whether the MCP exists or not. Onyx wraps **physics**: a Samsung on a Brazilian SIM pulling a real OTP from the carrier network. That capability has no upstream API. The MCP is the only door.

The paid HTTP endpoint runs behind x402 so every call pays for itself in USDC — no publisher subsidy, no free-tier rug-pull, no signup.

## How an agent calls it

```bash
curl -X POST https://onyx-actions.onrender.com/v1/sms_verify \
     -H "content-type: application/json" \
     -d '{"phone_number":"+55 11 98765 4321"}'
# → 402 Payment Required with accepts[] describing the price.
# Your agent signs an x402 EIP-3009 authorization with its wallet, retries,
# receives the OTP. Any x402-aware SDK handles it in ~5 lines.
```

Machine-readable manifest: `GET /manifest` or `GET / -H "accept: application/json"`.

## Run the stdio MCP yourself (free, local)

The stdio MCP in this repo exposes `onyx_solve_captcha` with no payment gate — clone and run locally in Claude Desktop / Cursor / Cline. The paid HTTP endpoint adds `onyx_sms_verify` and other physical-SIM primitives that can't meaningfully exist without per-call billing.

```bash
git clone https://github.com/dimitrilaouanis-tech/onyx-mcp
cd onyx-mcp && pip install -r requirements.txt
python server.py
```

Claude Desktop config:

```json
{
  "mcpServers": {
    "onyx": {
      "command": "python",
      "args": ["/absolute/path/to/onyx-mcp/server.py"]
    }
  }
}
```

## Run the paid HTTP server yourself

```bash
pip install -r requirements.txt
uvicorn server_http:app --host 0.0.0.0 --port 8080
```

Configure via `.env`:

- `ONYX_RECEIVE_ADDRESS` — wallet that receives USDC
- `ONYX_NETWORK` — `base` (mainnet) or `base-sepolia` (testnet, free)
- `ONYX_FACILITATOR_URL` — e.g. `https://x402.org/facilitator` (testnet) or a mainnet facilitator of your choice
- `ONYX_DEMO_MODE` — `1` returns synthetic OTPs for testing; `0` dispatches to the phone fleet

## Demo

`agent_demo.py` simulates an agent: discovers the server, pays $0.05 in testnet USDC, receives an OTP. Runs against local or public servers.

```bash
uvicorn server_http:app --host 127.0.0.1 --port 8080 &
python agent_demo.py
```

## License

MIT — see LICENSE.
