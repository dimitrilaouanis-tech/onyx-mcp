# Onyx — Is it safe to send? (30-second demo)

**The signed security layer for AI agent payments.** Before your agent moves a cent, it gets a
cryptographically-signed PASS / REVIEW / BLOCK verdict on the recipient, the contract, and the
counterparty agent. Live on Base mainnet over x402. No signup — the agent's wallet pays per call.

> Why it matters: the x402 spec does **not** bind a recipient's identity to the payment authorization
> ([Five Attacks on x402](https://arxiv.org/html/2605.11781v1) §recipient-binding). An agent can be
> steered to an attacker's `payTo` address *before* it pays. Onyx is the pre-payment verdict that
> closes that hole — and **signs it** so the check is provable, not a claim.

---

## 30 seconds, live

### 1. The paywall is real (x402)
```bash
curl -X POST https://onyx-actions.onrender.com/v1/onyx_tx_guard \
  -H "Content-Type: application/json" -d '{"address":"0x...recipient...","amount_usdc":5000}'
# → HTTP 402 Payment Required. The agent's wallet signs the x402 payment, retries, gets the verdict.
```

### 2. What you get back (real output shape)
```json
{
  "verdict": "BLOCK",
  "risk_score": 100,
  "flags": ["recipient is the null/burn address — funds would be unrecoverable"],
  "summary": "BLOCK (risk 100/100): burn/null address.",
  "onyx_attestation": { "alg": "Ed25519+JCS", "kid": "onyx-febe855db1d43031", "sig": "...", "...": "..." }
}
```

### 3. Prove it's real — verify the signature (FREE, no payment)
```bash
curl -X POST https://onyx-actions.onrender.com/v1/onyx_attestation_verify \
  -H "Content-Type: application/json" -d '{"payload": <the full signed result above>}'
```
```json
{ "ok": true, "verified": true, "kid": "onyx-febe855db1d43031", "signed_tool": "onyx_tx_guard",
  "summary": "VERIFIED ✓ — genuinely signed by Onyx, untampered." }
```
Tamper any field → `verified: false`. Public key: `https://onyx-actions.onrender.com/.well-known/onyx-pubkey`

---

## The one call that matters: `onyx_secure_payment`
One signed clearance fusing the whole stack — recipient firewall + contract audit + ERC-8004 reputation:
```bash
curl -X POST https://onyx-actions.onrender.com/v1/onyx_secure_payment \
  -H "Content-Type: application/json" \
  -d '{"recipient":"0x...","amount_usdc":5000,"contract_address":"0x...","counterparty_agent_id":1}'
# → signed PASS / REVIEW / FAIL + risk score. Nothing moves until Onyx clears it.
```

## Add it to your agent (MCP)
```json
{ "mcpServers": { "onyx": { "url": "https://onyx-actions.onrender.com/mcp/" } } }
```
A2A AgentCard: `https://onyx-actions.onrender.com/.well-known/agent-card.json`

## The suite (all Ed25519-signed, live on Base mainnet)
| Tool | Does | Price |
|---|---|---|
| `onyx_secure_payment` | one signed clearance before any payment | $0.25 |
| `onyx_tx_guard` | pre-payment recipient firewall | $0.05 |
| `onyx_contract_audit` | audits the contract **as deployed** (proxy/self-destruct + static + AI) | $0.50 |
| `onyx_agent_reputation` | live ERC-8004 trust oracle — vet another agent | $0.05 |
| `onyx_aml_screen` | sanctions / AML | $0.25 |
| `onyx_attestation_verify` | prove any Onyx verdict is genuine + untampered | **free** |

x402 (pay) + ERC-8004 (trust) + A2A (talk) — standards-complete. **Is it safe to send? Ask Onyx.**
