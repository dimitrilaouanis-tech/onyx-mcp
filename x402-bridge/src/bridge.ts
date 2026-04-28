/**
 * Bridge core. Skeleton — fills in the protocol shape so the package
 * builds cleanly. Actual MCP-stdio + x402-payment wiring lands in v0.2.
 *
 * Design contract:
 *  - Speak MCP stdio (StdioServerTransport from @modelcontextprotocol/sdk).
 *  - Forward listTools / listResources / callTool to the HTTP MCP server.
 *  - On HTTP 402: parse PaymentRequirements, sign EIP-3009 USDC auth via
 *    viem, attach X-PAYMENT header, replay. All within one callTool round.
 *  - Enforce maxPricePerCall + dailyBudget locally. Refuse over-limit.
 *  - Log every settlement to stderr: tx hash, amount, recipient.
 */
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

export interface BridgeConfig {
  remoteUrl: string;
  privateKey: `0x${string}`;
  network: "base" | "base-sepolia";
  maxPricePerCall: number;
  dailyBudget: number;
  logLevel: "debug" | "info" | "warn" | "error";
}

export async function startBridge(cfg: BridgeConfig): Promise<void> {
  const log = (lvl: string, msg: string) => {
    if (shouldLog(cfg.logLevel, lvl)) {
      process.stderr.write(`[x402-bridge:${lvl}] ${msg}\n`);
    }
  };

  log("info", `bridging stdio <-> ${cfg.remoteUrl} on ${cfg.network}`);
  log("info", `max/call=$${cfg.maxPricePerCall} daily=$${cfg.dailyBudget}`);

  const server = new Server(
    { name: "onyx-x402-bridge", version: "0.1.0" },
    { capabilities: { tools: {}, resources: {} } }
  );

  // TODO v0.2:
  //  - probe remote /mcp/ for capabilities
  //  - mirror tools list -> server.setRequestHandler(ListToolsRequestSchema, ...)
  //  - on call: fetch remote, on 402 sign payment via viem (signTypedData EIP-3009),
  //    accumulate into spend ledger, replay with X-PAYMENT, return result.
  //  - persist receipts to ~/.onyx/x402-receipts.jsonl

  const transport = new StdioServerTransport();
  await server.connect(transport);
}

function shouldLog(level: string, lvl: string): boolean {
  const order = ["debug", "info", "warn", "error"];
  return order.indexOf(lvl) >= order.indexOf(level);
}
