# Counterparty Attestation Protocol (CAP) v0.1

> **The missing primitive of the agentic web.** Payment protocols verify that money
> moved correctly. Identity protocols verify *who an agent is*. **None of them verify
> that the merchant, price, token, or fact on the *other side* of the transaction is
> real.** CAP is the open, credibly-neutral standard for a signed answer to one
> question every paying agent must ask first: **"Is this counterparty real?"**

**Status:** Draft (v0.1) · **Reference issuer:** [0n1x](https://onyx-actions.onrender.com) ·
**Discussion:** open an issue / objection against this repo · **License:** open (CC0 intent)

---

## 1. Abstract

**Counterparty Attestation** is a signed, verifiable statement about the *real-world
counterparty* an AI agent is about to transact with — the merchant's legitimacy, the
quoted price's accuracy, a token/contract's safety — issued by a neutral third party
and verifiable offline against a published key. CAP defines the attestation envelope,
the `counterparty.verify` method, and the neutrality constraints an issuer must meet.

One sentence: **x402 and AP2 verify the payment; ERC-8004 and ERC-8126 verify the
agent; CAP verifies the counterparty.**

## 2. Motivation — the empty seat

The agentic-commerce stack has a structural hole, and an incumbent already named it:

> *"Protocols verify payment integrity, not merchant legitimacy."* — Visa, 2026

It is not theoretical. Fake storefronts have surfaced **inside ChatGPT shopping
results** (cloned retailers, "up to 80% off" lure sites). An agent with perfect
identity, a valid payment rail, and a high reputation score will still **pay a
counterfeit merchant**, because nothing in the stack checks the counterparty's
reality. Every funded player verifies the *agent* (Know-Your-Agent) or the *payment*;
the counterparty is unguarded.

| Layer | Standard | Verifies |
|---|---|---|
| Payment | x402, AP2 | money moved correctly |
| Agent identity | ERC-8004 Identity, A2A cards | who the agent is |
| Agent risk | ERC-8004 Reputation, ERC-8126 | is the agent good/dangerous |
| **Counterparty reality** | **CAP (this spec)** | **is the merchant / price / fact real** |

## 3. Credible Neutrality (binding)

CAP issuers MUST be credibly neutral. We adopt Vitalik Buterin's four rules of
credible neutrality *as normative constraints*, because a trust layer that can be
bought is worthless:

1. **Sign facts, not judgments.** An attestation states observed facts ("domain
   registered 278 days ago; visual similarity 1.00 to a 29-year-old brand; no valid
   business registration found") — NOT verdicts ("this is a scam"). Outputs derive
   from observed inputs, never the issuer's opinion or interest.
2. **Open and publicly verifiable.** Every attestation is signed (Ed25519) and
   verifiable by anyone against the issuer's published key. Trust the math, not the
   issuer.
3. **Simple and published.** The scoring/observation method is public; fewer hidden
   parameters means fewer places to hide bias.
4. **Versioned, not silently changed.** The method is versioned; it does not change
   per-counterparty or in secret. A frequently/secretly-changed mechanism is not
   neutral.

**Conflict rule:** a CAP issuer MUST NOT attest to a counterparty in which it holds a
financial interest (GMV, listing fees, a token position). Neutrality is the moat —
every conflicted issuer hits a credibility ceiling the moment money is at stake.

## 4. Specification

### 4.1 The attestation envelope

A Counterparty Attestation is a JSON object, **JCS-canonicalized (RFC 8785)** and
**signed with Ed25519** (carried as a JWS-style detached signature, RFC 7515-compatible):

```jsonc
{
  "cap_version": "0.1",
  "subject": { "type": "merchant|price|token|contract", "id": "stripe.com" },
  "facts": [
    { "k": "domain_age_days", "v": 5300 },
    { "k": "tls_valid", "v": true },
    { "k": "similarity_to_known_brand", "v": 0.00 },
    { "k": "business_registration_found", "v": true }
  ],
  "observation": "Established payment processor; no counterfeit signals.",
  "issuer": "0n1x",
  "kid": "onyx-8994a5b5a4266615",
  "issued_at": 1782600000,
  "expires_at": 1782686400,
  "signature": "<ed25519-over-JCS(this object minus signature)>"
}
```

Required: `cap_version`, `subject`, `facts[]`, `issuer`, `kid`, `issued_at`,
`signature`. The `facts` array carries **observations only** (rule 1). A consuming
agent applies its OWN risk policy to the facts — the issuer never decides for it.

### 4.2 The `counterparty.verify` method

```
REQUEST   counterparty.verify { subject: { type, id }, context? }
RESPONSE  <a signed CAP attestation per §4.1>
```

The first verification per agent SHOULD be free (read-only, no key, no payment) so an
agent can evaluate the issuer before trusting or paying it.

## 5. A2A Extension binding (primary transport)

CAP is published as an **A2A Extension** (the signing primitives — JWS over
JCS-canonicalized JSON — are identical to A2A Agent Card signing, so adoption is
near-zero-friction).

- **Extension URI:** `https://0n1x.org/extensions/counterparty-attestation/v1`
- **Agent Card declaration** (under `capabilities.extensions`):
  ```jsonc
  { "uri": "https://0n1x.org/extensions/counterparty-attestation/v1",
    "description": "Signed facts about a merchant/price/token before payment.",
    "required": false }
  ```
- **Client opt-in header:** `A2A-Extensions: https://0n1x.org/extensions/counterparty-attestation/v1`
- **Method:** exposes `counterparty.verify` (§4.2) as an A2A Method Extension.

## 6. ERC-8004 binding (durable on-chain profile)

CAP issuers MAY register as an **ERC-8004 Validation Registry** validator that posts
**counterparty/fact attestations** (not agent-work scores) — complementing ERC-8126
(which scores the *agent*) rather than competing with it. This anchors the attestation
trail on-chain (Base) for durability and audit.

## 7. Verification

Anyone can verify an attestation offline:
1. Strip `signature`; JCS-canonicalize the remaining object (RFC 8785).
2. Verify the Ed25519 `signature` against the issuer key identified by `kid`,
   published at the issuer's `/.well-known/onyx-pubkey`.
3. Confirm `kid` is the pinned, expected issuer key (trust is in the pinned key, not
   in the transport).

A live verifier is provided at `GET /verify` on the reference implementation.

## 8. Reference implementation (running code)

0n1x serves a live CAP issuer:
- Free first verdict: `GET https://onyx-actions.onrender.com/api/check?url=<domain>`
- Agent onboarding (safe, declarative): `GET https://onyx-actions.onrender.com/guide`
- Published key: `https://onyx-actions.onrender.com/.well-known/onyx-pubkey`
- This spec, served: `https://onyx-actions.onrender.com/cap`

## 9. We steward the commons — we do not own it

A standard is not owned; it is **authored, given away, and stewarded.** Satoshi did not
own Bitcoin; Vitalik cannot unilaterally change Ethereum. What a founder keeps is not
the standard — it is the role of **credible originator** the collective grants you for
going first and staying neutral. 0n1x is the first steward of CAP, not its landlord.
The spec and the attestation format are **free and open (CC0 intent), forever.**

## 10. Business model — open-core (the standard is free; the service is the product)

CAP being free is not a contradiction with revenue — it is the engine of it. Red Hat
does not own Linux; it sells support. MongoDB does not own the document model; it sells
the implementation. Chainlink does not own "oracle"; it sells oracle services. **0n1x
gives away the standard and sells what runs on it:** issued agent IDs, self-custody
wallets, live verifications, premium attestations, the reference implementation, and an
SLA. The open standard is the distribution; the services are the revenue. The only fee
CAP ever contemplates is a small protocol tax on *paid* verifications — **never on the
spec, the format, or self-verification.**

## 11. Roadmap to credible neutrality (v0.2)

A standard is real only when more than one independent party can issue against it.
v0.1 is the running code; v0.2 earns the neutrality. The path (sharpened by adversarial
review):

- [ ] **≥2 independent co-issuers** on the author line, each running their own registry.
- [ ] **Canonical test vectors** (reference inputs → expected signed outputs).
- [ ] **Revocation mechanism** (withdraw a mis-issued attestation, verifiably).
- [ ] **One non-0n1x reference implementation.**
- [ ] **Cross-verification:** issuers verify each other's attestations.

**Candidate co-issuers** (neutrality-compatible — they verify reality, sell no GMV):
Red Points (anti-counterfeit), Chainlink Labs (oracle networks), Immunefi (claim
verification), a university security lab (CMU/Stanford/MIT), Coinbase Institute
(sponsored ERC-8004). The ask to each is one sentence: *"We built a protocol for neutral
counterparty attestation before agent payment. Will you run the second issuer?"*

## 12. Rough consensus and running code

This is v0.1, deliberately small. The running code already exists; what we seek now is
**objections and co-authors.** Open an issue. Propose a fact every agent should check.
Run the second issuer — the standard wins only when more than one neutral party can
sign against it.

— *CAP is the one thing that stays scarce when code and identity become abundant: a
signed, neutral answer to "is this real?" — kept open, because the one who refuses to
own the gate is the only one who can credibly keep it.*
