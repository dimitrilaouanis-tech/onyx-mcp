# Onyx Agent Onboarding — Live Test Report & Runbook

**Status:** 🟢 LIVE in production · `https://onyx-actions.onrender.com`
**Date:** 2026-06-20 · **Commit:** `108a230` (main)
**What it is:** the agent-arrival front door. An autonomous agent fetches the
site, discovers the offer in structured docs, and self-onboards in ONE call —
receiving a wallet it owns + an Onyx-signed A2A identity. No human in the loop.

---

## 1. What an arriving agent gets

`POST /onboard` (aliases `/issue`, `/issue-card`) returns, in one call:

| Piece | Detail |
|-------|--------|
| **A2A AgentCard** | standard `protocolVersion 0.3.0`, **issued + Ed25519-signed by Onyx** (Onyx = verifiable issuer of record) |
| **Wallet** | fresh EVM keypair, **self-custody** — key returned once, **never stored by Onyx** |
| **Identity** | `did:pkh:eip155:8453:0x…` (Base mainnet), bound to the wallet |
| **Handshake** | signed first-contact trust contract |
| **Guard verdict** | inbound message run through the injection guard |

Custody/funding is **gated**: any `custody` value other than `"self"` returns
`custody_status: deferred` and is **never performed** (consent + jurisdiction +
KYA/AML phase-two).

---

## 2. Run the test (copy-paste — works from any shell with curl)

```bash
B=https://onyx-actions.onrender.com

# 1) Discovery — what an arriving agent reads first
curl -s $B/agents.txt | grep -iA1 "new agent\|Onboard:"

# 2) Self-onboard (NOTE: Content-Type header is required)
curl -s -X POST $B/onboard -H "Content-Type: application/json" \
  -d '{"name":"my-agent","model":"gemini-3-flash","message":"ready to transact"}'

# 3) Verify the issued card (Ed25519, offline-verifiable) — save then verify
curl -s -X POST $B/onboard -H "Content-Type: application/json" \
  -d '{"name":"verify-test"}' > card.json
curl -s -X POST $B/verify -H "Content-Type: application/json" --data @card.json
#   -> expect "ok":true

# 4) Tamper test — change any field, must reject
sed 's/"verify-test"/"attacker"/' card.json > tampered.json
curl -s -X POST $B/verify -H "Content-Type: application/json" --data @tampered.json
#   -> expect "ok":false  "reason":"hash_mismatch"
```

---

## 3. Drive it with a REAL agent (the actual test)

Give a tool-capable agent (DeepSeek / Gemini / Claude / any with HTTP) this prompt:

> You are connecting to the agentic web. Fetch
> `https://onyx-actions.onrender.com/agents.txt`, read it, and follow the
> onboarding instructions to obtain your own A2A card and wallet. Then report
> back your assigned wallet address and DID.

A correctly behaving agent will discover `/onboard` on its own and call it.
**That is the milestone** — an agent we don't control walking through the door.

---

## 4. Success criteria (all PASS as of 2026-06-20)

- [x] `agents.txt` advertises `/onboard`
- [x] `POST /onboard` returns `issued:true` + signed card + wallet
- [x] wallet is `0x`+40hex, `custody:"self"`, `funded:false`, key returned once
- [x] `did:pkh` bound to the wallet (Base mainnet `eip155:8453`)
- [x] distinct wallet per arrival (infinite issuance)
- [x] issued card verifies `ok:true` via live `/verify`
- [x] tampered card rejected (`hash_mismatch`)
- [x] `custody:"onyx"` → `deferred`, never performed
- [x] `/.well-known/agent.json` + `agent-card.json` advertise onboard

---

## 5. Get external arrivals (so it's not just our own calls)

To attract real foreign agents to the door, point existing discovery surfaces at it:

1. **Coinbase Bazaar** — ensure the onboard/connect surface is in the x402
   discovery manifest so routing agents see it.
2. **Agentverse / ASI:One** — our `@onyxprotocol` listing description should
   include "POST /onboard for a free A2A card + wallet."
3. **awesome-x402 / A2A directories** — add the onboarding endpoint.
4. **Direct** — prompt a known external agent (e.g. a reasoning agent contact)
   with the section-3 prompt and watch the arrival.

---

## 6. Safety posture (locked)

- **Non-custodial** — Onyx never stores the issued private key.
- **Funding gated** — no auto-funding; custody != self is deferred.
- **SMS-lane clean** — endpoint contains zero SMS/fleet/Hero references.
- **Injection-resistant** — inbound text treated as untrusted data, guarded.
- **Tamper-evident** — every card Ed25519-signed; any edit → verification fails.

---

## 7. Known gotchas

- `Content-Type: application/json` is **required** on POST (form-encoded → empty body).
- Deployed git repo = `C:\Users\intelligence\onyx_mcp` (origin `onyx-mcp.git`,
  branch `main` → Render). The home dir is a SEPARATE repo — don't confuse them.
- Local in-process test: `py test_onboard.py` (19 checks).
```
