# SEP: Counterparty Attestation Extension (`org.0n1x/counterparty-attestation`)

- **Status:** Draft (prepared for the **Extensions Track**, per SEP-2133; filing at modelcontextprotocol/modelcontextprotocol)
- **Type:** Extensions Track (negotiated capability, reverse-DNS namespace)
- **Extension ID:** `org.0n1x/counterparty-attestation`
- **Builds on:** *Signed Tool Outputs* SEP (proof-carrying results) — the integrity envelope this extension's semantics ride inside.
- **Relates to:** ERC-8004 Validation Registry (the on-chain mirror of these attestations); AP2 Cart Mandate (where this rides as an extra Verifiable Credential).
- **Author:** 0n1x (Onyx Protocol) — reference implementation live since May 2026.
- **Created:** 2026-06-28
- **Window:** Extensions framework (SEP-2133) finalizes at the **2026-07-28 RC**. This SEP claims the counterparty-attestation namespace before that milestone.

## Abstract

Every agent-payment rail standardized in 2025–26 verifies the **agent** (Visa TAP,
Skyfire KYA, ERC-8126 risk score) and the **payment intent** (AP2 mandates, x402
settlement). **None verify the COUNTERPARTY** the agent is about to transact with —
the merchant's legitimacy, the price's reality, the fact the decision rests on. Visa
states this on the record: protocols "verify payment integrity, not merchant
legitimacy." This SEP defines an OPTIONAL MCP extension by which a server emits a
**signed counterparty-fact attestation** — a typed, verifiable claim about external
reality — that any agent can check *before it pays*. It signs **facts, not judgments**.

## Motivation

1. **The named, live gap.** ChatGPT shopping surfaced cloned storefronts that steal
   card data (Russell & Bromley, R&B/Dunelm). The agent had no neutral way to ask "is
   this merchant real?" before paying. This extension is that call.
2. **Neutrality the rails structurally cannot offer.** Visa/Mastercard/Coinbase each
   grade transactions on rails they monetize — they cannot neutrally grade the
   counterparty. A conflict-free issuer must occupy the seat (the DoubleVerify pattern:
   advertisers refuse to let the platform grade its own delivery).
3. **Fact, not reputation.** ERC-8004/8126 score the *agent's* reputation (an empirical
   2026 study found that registry 73–96% Sybil-flagged). This extension attests the
   *counterparty's reality* — an orthogonal, harder-to-fake signal.

## Specification

### Capability negotiation

A server advertises the capability in the `init` handshake:

```json
{
  "capabilities": {
    "extensions": {
      "org.0n1x/counterparty-attestation": { "version": "0.1", "algs": ["Ed25519+JCS"] }
    }
  }
}
```

A client MAY request an attestation by setting, on a tool call's arguments `_meta`:
`"org.0n1x/counterparty-attestation": { "subject": "<domain|address|listing-uri>" }`.

### The attestation object

Carried in `CallToolResult._meta["org.0n1x/counterparty-attestation"]`, and signed by
the *Signed Tool Outputs* envelope (so integrity + issuer identity are inherited, not
re-invented):

```json
{
  "subject": "rayban.cc",
  "subject_type": "merchant_domain",
  "verdict": "ABORT",                       // PROCEED | REVIEW | ABORT  (action, fail-closed)
  "facts": {                                // SIGNED OBSERVATIONS, not opinions
    "domain_age_days": 278,
    "entity_match": false,                  // domain ↔ claimed entity binding
    "tls_issued_to": "unknown",
    "price_observed_usd": 89.0,
    "price_vs_reference": "implausible_low",
    "sanctions_hit": false
  },
  "fact_basis": ["whois:2026-06-27", "ct-log", "live-fetch:2026-06-27"],
  "confidence": 0.97,
  "not_a_judgment": "These are observations 0n1x can re-derive; the agent decides.",
  "issued_at": 1782600000,
  "issuer": "did:web:onyx-actions.onrender.com"
}
```

- **`verdict` is an ACTION recommendation derived from `facts`, fail-closed** (absent
  data ⇒ never PROCEED). The `facts` are the signed substance; the verdict is a
  reproducible function of them, disclosed so any verifier recomputes it.
- **Sign facts, not judgments** (normative): every field in `facts` MUST be an
  observation the issuer can independently re-derive, with a `fact_basis` source+date.
  Subjective scores about the *agent* are out of scope (that is KYA/8126's lane).
- **On-chain mirror (OPTIONAL):** the attestation hash MAY be posted to the ERC-8004
  Validation Registry with `tag = "counterparty-fact"`, giving a neutral, append-only,
  third-party-readable record. The MCP `_meta` and the on-chain record share one hash.
- **AP2 interop (OPTIONAL):** the same object is losslessly expressible as a W3C
  Verifiable Credential attachable to an AP2 Cart Mandate, checked before the Payment
  Mandate fires.

### Verification

Detach → JCS-canonicalize → verify the Signed-Tool-Outputs Ed25519 signature →
optionally recompute `verdict` from `facts` → optionally confirm the on-chain hash.
A failed signature is *unverified data*, never a fatal session error.

## Rationale

- **Extensions Track, not Standards Track:** this is an additive semantic layer, not a
  core protocol change — exactly the shape SEP-2133 created the lane for.
- **Reverse-DNS namespace** makes 0n1x the *named owner* of the counterparty-attestation
  capability in the handshake — the standard seat, claimed before the RC.
- **Rides the signed-output envelope** rather than re-specifying signatures: one
  integrity primitive, two SEPs (envelope = who-produced-what; this = what-it-means).

## Prior art & differentiation (Fime FACT)

Fime's "FACT" (Framework for Agentic Commerce Trust, launched 2026-04-21) is the
nearest-positioned effort and the contrast sharpens this SEP's scope:

| | Fime FACT | This SEP (`org.0n1x/counterparty-attestation`) |
|---|---|---|
| **Spec** | Closed — no public spec/schema/API; sold as "trust-as-a-service" (quote-gated) | **Open** — published spec, reverse-DNS extension, anyone can emit |
| **Verifies** | The AGENT: intent-fidelity ("did the agent buy what the human asked"), policy/compliance | The COUNTERPARTY: is the merchant real, is the price plausible, signed facts |
| **Merchant reality** | None (Fime's own scope; merchant is a *beneficiary*, not a verified party) | **The entire point** |
| **Governance** | Wholly Fime-owned (markets "neutral" but is a single private vendor) | Open extension, neutral by construction (issuer earns nothing from what it grades) |
| **Cost** | Commercial, sales-gated | Free to implement; verify is free, signed verdict is the only paid surface |

FACT verifies the *agent's intent*; this SEP verifies the *counterparty's reality* —
complementary axes. The two together (agent-intent + counterparty-reality) cover the
full pre-pay trust surface; neither subsumes the other. This SEP deliberately occupies
the merchant/price-reality lane FACT's own materials state it does not address.

## Security considerations

Proves *who attested what facts about a counterparty, unmodified* — and, because facts
carry a re-derivable `fact_basis`, a verifier need not trust the issuer's word. Issuer
neutrality is the trust anchor: the issuer MUST earn nothing from the counterparties it
grades (enforced by design, the moat). Replay bounded by `issued_at` + staleness policy.

## Reference implementation

Live: `https://onyx-actions.onrender.com` — `onyx_merchant_fact_check` and the
verify-before-pay tools already emit signed counterparty facts (e.g. a live catch of a
278-day cloned `rayban.cc` vs the 29-year legitimate domain). Signing core ~170 lines;
independent verifier published alongside. This SEP standardizes the envelope key and the
capability handshake around the existing implementation.
