# Onyx MCP — Action Primitives for AI Agents

MCP server exposing Onyx's production action workers as tools agents can call. Start with one tool, expanding with each release.

## Tools

| Tool | Description |
|------|-------------|
| `onyx_solve_captcha` | Solve an image-based text captcha via Onyx's OCR stack (ddddocr). Typical accuracy 70–90% on standard web captchas. ~30ms per solve. |

## Install

```bash
pip install -r requirements.txt
```

## Use with Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "onyx": {
      "command": "python",
      "args": ["/absolute/path/to/onyx_mcp/server.py"]
    }
  }
}
```

## Use with Cursor / Cline / Continue

Point the MCP config at `python server.py` with the `onyx_mcp/` directory as cwd. Same as above.

## x402 Paid HTTP Version

`server_http.py` runs the same tool behind an x402 payment gate — agents pay $0.003 USDC per call on Base (testnet/mainnet). See `server_http.py` for the FastAPI variant.

## Development

`test_stdio.py` runs the server end-to-end over stdio with a local test image. Path inside the script is machine-specific; swap it to your own image to verify locally.

## License

MIT — see LICENSE.
