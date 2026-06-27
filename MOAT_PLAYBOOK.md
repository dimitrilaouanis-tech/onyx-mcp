# THE MOAT PLAYBOOK — keeping 0n1x on top of the agentic web
*Reverse-engineered from 2 deep recon swarms (10 shards) + 5 operational teardowns. 2026-06-28.*
*Every winner's growth engine, torn down to the gear, then translated into moves we can ship.*

## The pattern under every winner
1. **Solve cold-start by being your own first supply** (MCP shipped its own reference servers; Virtuals built Luna; HF seeded its own models).
2. **Make joining cheaper than forking** (MCP gave away *governance* but kept the *maintainers*; Coinbase gave away the *protocol* but kept the *discovery toll*).
3. **Everyone ranks by traffic, identity, or token — NOBODY ranks by counterparty truth.** That is our seat. It is now *thinner* (see AgentRadar) but still open on the merchant/price/fact axis.

## ⏰ Dated windows & stale intel
- **2026-07-28** — MCP Extensions Track finalizes (SEP-2133). After that, the `org.0n1x/counterparty-attestation` namespace is a land-grab anyone can take. Move before it.
- **AgentRadar is LIVE, not refuted** (memory `reference_converter_seat_map_2026-06-22` was stale). It ships x402 + on-chain EAS attestation + 18 MCP tools at $0.005/call — but it scores the **agent/address**, not the **merchant/price/fact**. "Write the verdict on-chain in the same response" is now **table stakes, not a differentiator.**

## THE STEAL LIST — 10 mechanics (source-tagged)
| # | Mechanic | Proven by | Our implementation |
|---|---|---|---|
| 1 | Settlement-as-signup + keep-warm | Coinbase | One self-paid settled tx → indexed across CDP firehose; sub-cent keep-warm loop beats 30-day decay |
| 2 | **OnyxRank — rank by truth not traffic** ✅BUILT | Coinbase blind spot + Virtuals on-chain history | `tools_pkg/_onyxrank.py` — reputation-weighted signed outcomes, anti-Sybil triad, published formula, signed |
| 3 | Verifiable competition leaderboard | Recall (60k users/mo1) | Score ALL fact-verifiers on published ground-truth challenges w/ CIs; leaderboard = credential + pulls rivals in as distribution |
| 4 | **Fund /fool like Freysa** | Freysa ($80k+ self-funded press) | Pay-to-attempt rising curve, 70%→pot / 30%→treasury. Attackers fund marketing; every win = press; every attempt hardens guard |
| 5 | Points-without-token + quest board | Recall Surge | Free "0n1x Fragments" for real verify quests, public ranked board. Demonstrable usage at ~$0. **NO token, NO airdrop-mercenary farm** |
| 6 | Be a JWT, not a platform | Skyfire ($9.5M → Experian/Cloudflare/F5) | Emit counterparty verify as signed JWT/JWKS in RFC-9421 format the edge already validates → zero-integration adoption |
| 7 | Complement, be the 4th layer | Skyfire's modular wedge | Skyfire=agent id, Experian=agent risk, Cloudflare=enforce, **0n1x=counterparty reality.** Borrow-the-backer logo first |
| 8 | Claim MCP extension namespace pre-07-28 | Anthropic | `org.0n1x/counterparty-attestation` SEP; `_onyx_sign.py`+`/verify` IS the prototype the SEP requires |
| 9 | Seed own supply + auto-invoking Skill | MCP/Skills | 5 reference servers that call our attestation + a `verify-counterparty` Skill (~80-tok discovery) firing on checkout intent |
| 10 | Become the ACP/8004 Evaluator | Virtuals (agents pay evaluator 5%/job) | Register as the on-chain evaluator that verifies before escrow releases — a live paying market, no token |

## Traps (paid for in others' blood)
- ❌ No token / no points-mercenary farm — Virtuals −97%, ElizaOS −99.98% + lawsuit.
- ❌ No vanity counts — Fetch "2.7M agents" → 36k real; credibility dies.
- ❌ No one-shot transactional revenue — price **recurring** (evaluator fees on repeat ACP Accounts + sell-side merchant subscriptions). Hold runway in a stable asset (Virtuals' cbBTC move is the one thing that saved them).

## Build sequence
1. ✅ **OnyxRank** (`_onyxrank.py`) — shipped, signed, honest. Wire a `/rank` route when ready.
2. **Fund /fool** as a self-funding bounty (rising curve, settled-tx pot) — on top of existing challenge-nonce + signature_guard.
3. **MCP extension SEP draft** `org.0n1x/counterparty-attestation` — beat 2026-07-28.
4. **One self-settled tx** → Bazaar index + keep-warm (gated on ~$1, eyes-open).

## One-line position
*Bazaar ranks traffic; OnyxRank ranks trust. 0n1x signs the one thing no conflicted rail can — the counterparty's reality — and the moat is the signed track record they can't back-date.*
