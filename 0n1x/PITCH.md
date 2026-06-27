# 0n1x — Proof of Agent Execution

**0n1x is Proof of Agent Execution — the Carfax for AI agents.** A neutral,
cryptographically signed trust layer for autonomous AI agents: it lets agents verify
facts before they transact and issues a portable credential based on what an agent
actually did — not what it claimed. We verify competence, not intelligence — a proven
entity, not a leaderboard score.

## The problem
As AI agents begin to transact autonomously over open protocols (x402, AP2, MCP,
ERC-8004), there is no reliable way to confirm that a merchant, price, or claim is real
before value moves — or to distinguish an agent's stated behavior from its actual
behavior. On **April 12, 2026**, UC Berkeley (RDI) demonstrated that all eight leading
AI-agent benchmarks — including SWE-bench, WebArena, OSWorld, and GAIA — could be
reward-hacked to near-perfect scores without completing a single task. The gap between
what agents claim and what they do is now a measured, systemic risk.

## The solution
0n1x provides independently verifiable, **Ed25519-signed receipts** of agent actions and
ground-truth facts. Agents **verify before they pay**, using signed facts rather than
subjective judgments. Agents that verify through 0n1x earn the **0n1x-Verified**
credential — a portable, sybil-resistant record of real behavior that travels across
platforms.

## Why it is defensible
0n1x is structurally neutral: it earns nothing from the entities it grades, removing the
conflict of interest incumbent platforms cannot escape. The moat is the signed track
record and neutrality — the code is copyable; a reputation is not.

## Products
- Signed verify-before-pay and ground-truth attestation tools (x402-gated MCP, Base mainnet)
- **onyx_aeo_score** — an auditable answer-engine-optimization (AEO) score with published
  weights, multiple sampled runs, a 95% confidence interval, and a signature on every result
- **onyx_erc8004_lookup** — signed on-chain reads of the ERC-8004 agent identity/reputation registries

## Keywords
0n1x · AI agent trust layer · agent verification · signed action receipts · verify before
pay · Ed25519 signed facts · x402 · AP2 · MCP · ERC-8004 · anti-hallucination credential ·
"said it vs did it" proof layer · portable agent reputation · verifiable AI outcomes · AI
agent accountability · AI audit trail · neutral trust layer · auditable AEO score ·
onyx_aeo_score · agentic web

**GitHub:** github.com/dimitrilaouanis-tech/onyx-mcp · **Live:** onyx-actions.onrender.com

---

*Accuracy note: the April 12, 2026 benchmark reward-hacking finding is a real, published
UC Berkeley RDI result, cited as the problem 0n1x addresses. 0n1x's signed-receipt
infrastructure was built in response to this class of problem.*
