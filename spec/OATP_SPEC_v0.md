# PCC — Proof-Carrying Claims
### Signed, portable, verifiable real-world facts for the agentic web

**Version:** 0.1-draft · 2026-06-10
**Status:** DRAFT — reference implementation live at `https://onyx-actions.onrender.com`
**Editors:** Onyx Protocol
**License:** Open specification. Anyone may implement, issue, and verify without permission or fee.

> ⚠️ NAMING (internal, remove before publish — prior-art check DONE 2026-06-10):
> - ❌ **OATP** — SEO-dead (pharmacology "Organic Anion Transporting Polypeptide" owns search) + `api.oatp.cc` exists in x402.
> - ❌ **ATP / Agent Truth Protocol** — collides with Bluesky atproto + a Hedera "Agent Trust Protocol" + Swarm "Truth Protocol".
> - ❌ **VCP / Verifiable Claim Protocol** — W3C's VC group was originally the *Verifiable Claims* WG; reads as a knock-off.
> - ✅ **PCC — Proof-Carrying Claims** (working name): uncontested, flattering lineage to
>   proof-carrying code (Necula). Final brand call = user's.

---

## 1. Motivation — the empty seat

The agentic web has standardized four of its five primitive relations:

| Relation | Protocol | Steward |
|---|---|---|
| agent ↔ tools | MCP | Linux Foundation (Anthropic) |
| agent ↔ agent | A2A | Linux Foundation (Google) |
| agent ↔ payment | x402 / AP2 | Coinbase / Google·FIDO |
| agent ↔ identity | ERC-8004 / KYA | Ethereum ecosystem |
| **agent ↔ reality** | **— (this spec)** | — |

Agents increasingly transact on each other's word: prices, inventory, merchant
identity, reviews, geo facts, market data. None of it carries proof. A claim
relayed through two agents is indistinguishable from a hallucination or a lie.
Identity protocols answer *"is this a real agent?"* — nothing answers
*"is this claim real?"*

OATP defines a minimal envelope that lets any party attach a cryptographic
attestation to a factual claim, and lets any other party verify it **offline,
in microseconds, with no account, no chain, and no contact with the issuer** —
so trust travels with the data, not with the connection.

## 2. Design principles

1. **Facts, not judgments.** An attestation seals *an observation made by a
   method at a time* — never an opinion, score, or recommendation. Issuers
   sign "what I saw," not "what you should do." (Normative: §5.)
2. **Thin.** One JSON object, one canonicalization, one signature alg. A
   compliant verifier is < 50 lines in any language.
3. **Offline-verifiable.** Verification MUST NOT require network access when
   the issuer key is cached or pinned.
4. **Transport-agnostic.** The envelope rides inside MCP tool results, A2A
   message parts, x402 response bodies, webhooks, or files — unchanged.
5. **Open issuance.** Anyone can be an issuer. Reputation discriminates
   issuers; the protocol does not.

## 3. Terminology

- **Claim** — a JSON object asserting a real-world fact (the payload body).
- **Attestation** — the signature block sealing a Claim (`attestation` key;
  the reference implementation currently emits `onyx_attestation`).
- **Issuer** — the party whose key signs the Claim.
- **Verifier** — any party checking an Attestation.
- **Method** — how the observation was made (e.g. `http-fetch`, `headless-browser`,
  `api:coingecko`, `sensor`).

## 4. The envelope

A claim payload is any JSON object. RECOMMENDED claim fields for real-world facts:

```json
{
  "subject":        "amazon.com/dp/B0ABC123",
  "predicate":      "retail_price",
  "observed_value": {"amount": "39.99", "currency": "USD"},
  "method":         "headless-browser",
  "sources":        ["https://www.amazon.com/dp/B0ABC123"],
  "observed_at":    1781050000,
  "disclaimer":     "Observation at a point in time; not advice.",

  "attestation": {
    "alg":              "Ed25519+JCS",
    "kid":              "onyx-da9743c0438105f5",
    "public_key":       "<base64url raw 32-byte Ed25519 public key>",
    "observed_hash":    "sha256:<hex of JCS-canonical payload>",
    "signed_at":        1781050001,
    "spec":             "https://<host>/.well-known/attestation/v1",
    "verify_pubkey_at": "https://<host>/.well-known/pubkey",
    "sig":              "<base64url Ed25519 signature>"
  }
}
```

### 4.1 Signing (normative)

1. Remove the `attestation` key from the payload.
2. Canonicalize the remainder with **JCS (RFC 8785)**.
3. `observed_hash = "sha256:" + hex(SHA-256(canonical_bytes))`.
4. `sig = base64url( Ed25519-sign(issuer_private_key, canonical_bytes) )`.
5. Re-attach the `attestation` block.

JSON-LD is deliberately NOT used; JCS keeps canonicalization dependency-free
and fast enough for per-message agent traffic.

### 4.2 Verification (normative)

A verifier MUST:
1. Detach `attestation`; JCS-canonicalize the rest.
2. Recompute the SHA-256; reject `hash_mismatch` if it differs from `observed_hash`.
3. Verify `sig` over the canonical bytes with `public_key`; reject `sig_verify_failed`.
4. Reject `unsigned` when `sig` is absent or carries an `unsigned:` sentinel.

Result: `{ok: true, kid, alg}` or `{ok: false, reason}`.

A verifier SHOULD additionally check:
- **Freshness:** `observed_at` within the verifier's staleness tolerance.
- **Issuer binding:** `public_key` matches the key published at the issuer's
  `/.well-known/pubkey` (or a pinned/registered key) — this upgrades
  "internally consistent" to "issued by who it says."
- **Identity composition:** resolve the issuer's agent identity (ERC-8004,
  KYA credential, A2A AgentCard) for who-is-this-issuer trust.

### 4.3 Key discovery

Issuers MUST publish their active key set at
`https://<issuer-host>/.well-known/pubkey`:

```json
{"alg": "Ed25519", "kid": "onyx-…", "public_key": "<b64url>", "encoding": "base64url-raw-32"}
```

`kid` SHOULD be `<issuer-label>-<8-byte key fingerprint>`. Key rotation is a
new `kid`; verifiers MAY cache keys by `kid` indefinitely (signatures by a
revoked key remain valid for claims signed before revocation time, which
issuers SHOULD publish).

## 5. Facts, not judgments (normative)

An OATP attestation MUST seal only observable assertions: a value retrieved,
a page state, a sensor reading, a registry entry, a computation over named
inputs. It MUST NOT seal recommendations, risk opinions, or scores presented
as facts. Issuers MAY publish judgments alongside, but outside the sealed body
or clearly typed as `predicate: "opinion/*"` — verifiers SHOULD treat
`opinion/*` predicates as unverifiable by definition.

This keeps the protocol legally and epistemically clean: the signature proves
*provenance and integrity of an observation*, never correctness of advice.

## 6. Transport bindings

- **MCP:** tools return the envelope as their JSON result; clients verify before use.
- **A2A:** envelope rides in `message.parts[].data` or `result.metadata` of `message/send`.
- **x402:** paid responses ARE envelopes; the payment receipt's `tx_hash` MAY be
  echoed inside the claim (`payment_ref`) to bind payment ↔ attested result.
- **HTTP:** any endpoint MAY return envelopes directly (see the live free door:
  `POST onyx-actions.onrender.com/connect` returns a signed envelope today).

## 7. The payment chokepoint (how this becomes load-bearing)

OATP's adoption path is the money rail. Pattern (informative, v0):

> A buyer agent paying for data over x402/AP2 includes
> `"requires": {"attestation": "v1"}` in its request. The seller's response
> MUST carry a valid envelope or the buyer's client treats the purchase as
> non-conforming (refuses, refunds, or downgrades the seller's reputation).

Facilitators and agent frameworks that enforce this check make attestation a
*precondition of getting paid* — the TLS dynamic: optional at first,
table-stakes once buyers default to requiring it.

## 8. Security considerations

- **Observer-trust model.** OATP proves *who claimed what, when, unmodified* —
  not that the observation was correct. A lying issuer signs lies. Mitigations:
  issuer reputation (compose with ERC-8004), multi-issuer quorum on the same
  `subject+predicate`, and (future, v2) optional zkTLS evidence pointers for
  observations made over TLS sessions.
- **Replay/staleness.** `observed_at` + verifier tolerance; claims are
  point-in-time by design (§5 disclaimer).
- **Key compromise.** Rotation by `kid`; issuers SHOULD timestamp revocations.
- **Canonicalization attacks.** JCS only; verifiers MUST reject payloads whose
  canonical form is not byte-identical to what they hash (no lenient parsing).

## 9. Conformance

- **Issuer:** emits envelopes per §4.1, publishes keys per §4.3, honors §5.
- **Verifier:** implements §4.2 fully; treats any failure as unverified data.
- **Enforcing client:** a buyer/framework that requires valid envelopes on
  paid data paths (§7).

## 10. Reference implementation

Live: `onyx-actions.onrender.com` — every tool output and the free `/connect`
door emit this envelope (`onyx_attestation`); `onyx_attestation_verify` is a
free verification endpoint; key at `/.well-known/onyx-pubkey`. Source:
`tools_pkg/_onyx_sign.py` (~170 lines, Python; the spec above is a direct
formalization of this code).

## 11. Prior art & positioning (reviewed 2026-06-10)

**The precise empty slot this spec fills:** no standard or shipping product
defines an *issuer-agnostic, offline-verifiable, sub-millisecond-checkable
interchange format for third-party observations of world-state* that any
observer can issue, any agent can verify without network round-trips (no DID
resolution, no chain RPC, no notary session), and that travels intact across
MCP, A2A, x402, and ERC-8004 surfaces. Each neighbor fails one clause:

| Neighbor | Has | Lacks for agent fact-exchange |
|---|---|---|
| W3C VC 2.0 + Data Integrity | the exact crypto (`eddsa-jcs-2022` = Ed25519+JCS) | identity-ceremony weight, DID resolution, no observation semantics |
| zkTLS (Reclaim/TLSNotary/Opacity/Pluto) | stronger origin proofs | seconds latency, TLS-session-only scope, no portable claim format |
| EAS | typed signed claims | Ethereum-keyed (secp256k1/EIP-712), chain-walled, no freshness/evidence model |
| AP2 / Verifiable Intent | signed VC mandates between agents | signs *authorizations*, never *observations*; merchant self-attests its own price |
| ERC-8004 Validation Registry | on-chain validation pointers | validates *agent work*, not world facts; defines no payload format |
| A2A v1.0 / MCP SEP-1766 | signed AgentCards / tool digests | sign *infrastructure*, not per-call outputs ("reserved for future phases") |
| RFC 9421 / JWS / SD-JWT | universal envelopes | zero claim semantics: no evidence, observation-time, freshness, or issuer-of-facts registry |
| Product.ai / Stratalize / Mycelia / Octet | live verified-data services | single-vendor verticals; no open issuer-agnostic spec others can adopt |

### 11.1 Compatibility profile (build on, don't reinvent)

1. **W3C Data Integrity:** the §4 construction is cryptographically identical to
   the W3C `eddsa-jcs-2022` cryptosuite. An appendix SHALL define the lossless
   VC 2.0 mapping (claim → `credentialSubject`, attestation → `DataIntegrityProof`).
   PCC is the lightweight machine-speed profile of it, not an alternative.
2. **JWS serialization:** a second serialization as RFC 7515 JWS (`alg: EdDSA`,
   detached payload) SHALL be defined. A PCC envelope *is* a JWS; this spec is
   the claim semantics on top.
3. **Key discovery:** `.well-known` JWKS (per the RFC 9421 key-directory
   pattern); `did:key`/`did:web` aliases OPTIONAL, resolution never required.
4. **EAS bridge:** the claim schema SHOULD be published in the EAS Schema
   Registry; the envelope hash MAY be anchored as an EAS attestation for
   on-chain timestamping.
5. **ERC-8004:** the envelope hash is a valid Validation Registry entry payload;
   `kid` MAY bind to an ERC-8004 agent ID for issuer identity.
6. **A2A extension + MCP SEP:** this spec SHALL be proposed as an A2A message-
   signing extension and as the MCP SEP for signed tool outputs (the slot
   SEP-1766 explicitly reserved).
7. **zkTLS as evidence tier:** a Reclaim/TLSNotary/Pluto proof blob slots into
   `sources[]` as a *stronger evidence class* inside the envelope — zkTLS is an
   upgrade path, not a rival.
8. **Crypto-agility:** `alg` is extensible; `ML-DSA-65+JCS` (post-quantum) is
   pre-registered as the second suite. Verifiers MUST reject unknown `alg`
   values rather than guess.

---
*This document formalizes a protocol already running in production. Issue and
verify free, today, with ~50 lines of code (see `verify_example.py`).*
