#!/usr/bin/env node
/**
 * @onyx/x402-bridge — stdio MCP bridge for x402-paid HTTP MCP servers.
 *
 * Usage:
 *   npx @onyx/x402-bridge <remote-url>
 *
 * The bridge speaks stdio MCP to the client and HTTP MCP to the server.
 * On HTTP 402 it signs an EIP-3009 USDC authorization with the configured
 * wallet and replays the request, all transparent to the client.
 */
import { startBridge } from "./bridge.js";

const remoteUrl = process.argv[2];
if (!remoteUrl) {
  console.error("usage: onyx-x402-bridge <remote-url>");
  console.error("example: onyx-x402-bridge https://onyx-actions.onrender.com/mcp/");
  process.exit(2);
}

const privateKey = process.env.X402_PRIVATE_KEY;
if (!privateKey) {
  console.error("X402_PRIVATE_KEY env var required (0x-prefixed hex private key)");
  process.exit(2);
}

const network = process.env.X402_NETWORK ?? "base";
const maxPricePerCall = Number(process.env.X402_MAX_PRICE_PER_CALL ?? "0.05");
const dailyBudget = Number(process.env.X402_DAILY_BUDGET_USDC ?? "1.00");
const logLevel = (process.env.X402_LOG_LEVEL ?? "info") as "debug" | "info" | "warn" | "error";

await startBridge({
  remoteUrl,
  privateKey: privateKey as `0x${string}`,
  network: network as "base" | "base-sepolia",
  maxPricePerCall,
  dailyBudget,
  logLevel,
});
