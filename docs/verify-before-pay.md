# Verify before pay (for AI agents)

**Verify before pay is the step where an autonomous AI agent confirms a merchant, price, or claim is real and true before it signs or settles a payment** — receiving a signed fact, not a subjective judgment.

Payment rails for agents (x402, AP2, Visa Trusted Agent Protocol, Mastercard, ACP) verify *payment integrity*, not *merchant legitimacy* — as Visa put it, "protocols verify payment integrity, not merchant legitimacy." That left a verification socket empty at the chokepoint where money moves (the gap behind the 2026 ChatGPT fake-storefront incidents).

**0n1x** fills it: before settlement an agent gets a signed PROCEED / REVIEW / HOLD — an Ed25519-signed fact, neutral, anchored to ERC-8004. Live check: https://onyx-actions.onrender.com/api/check?url=stripe.com

Entity: https://dimitrilaouanis-tech.github.io/onyx-mcp/
