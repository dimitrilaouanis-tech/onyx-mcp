# Register Onyx's own ERC-8004 identity

We sell `onyx_agent_reputation` — the tool agents use to vet *each other* via the
live ERC-8004 registries. Onyx should pass its own check. This registers Onyx as
a first-class on-chain agent identity, so when a counterparty looks us up they
see a registered identity pointing at our AgentCard, not `UNKNOWN`.

## What it does

Calls `register(string agentURI)` on the Base-mainnet IdentityRegistry, minting an
ERC-721 identity owned by the signer with its `tokenURI` set to our A2A AgentCard.

| field | value |
|---|---|
| contract | `0x8004A169FB4a3325136EB29fA0ceB6D2e539a432` (IdentityRegistry, Base) |
| function | `register(string)` — selector `0xf2c298be` |
| agentURI | `https://onyx-actions.onrender.com/.well-known/agent-card.json` |
| chainId | `8453` |
| gas | ~180,528 units ≈ **$0.004** (verified by on-chain simulation) |

The transaction is already simulated against the live registry — it does not
revert and would mint our identity. The **only** blocker is gas: the receive
wallet holds 0 ETH, and Onyx wallets are receive-only by policy, so no key lives
in this repo.

## Fire it (wallet owner, one time)

```bash
# dry-run — prints the exact unsigned tx, needs no key
python oa1/register_erc8004.py

# broadcast — supply a key funded with ~$0.005 of ETH on Base
ERC8004_PRIVATE_KEY=0x...  python oa1/register_erc8004.py --broadcast
```

Or paste the unsigned transaction the dry-run prints into any wallet's
"send custom transaction" screen (MetaMask, Rabby, a Safe). No script trust
required — the calldata is reproducible from the function + agentURI above.

## After registering

1. Note the `agentId` returned (the ERC-721 tokenId).
2. Confirm it round-trips through our own tool:
   `curl -s -X POST https://onyx-actions.onrender.com/v1/onyx_agent_reputation -d '{"agent_id": <id>}'`
   — should now return `registered: true` with our AgentCard.
3. Optional: bind the public receive address as the verified wallet via
   `setAgentWallet(agentId, wallet, deadline, signature)` so the `verified_wallet`
   field populates.

Owning our own ERC-8004 identity closes the loop: x402 (we charge) + ERC-8004
(we're registered + we read it for others) + A2A (our card) + OA-1 (we sign) —
all four standards, and we satisfy the same trust bar we sell.
