# Output Usage-Rights Envelope v0
### Signed terms that travel with a purchased agent output

**Status:** v0 draft · 2026-06-10 · Live tool: `onyx_usage_rights` ($0.01) · Verify free: `onyx_attestation_verify`

## Problem

RSL 1.0 and robots-era conventions govern **input** rights — what crawlers and
trainers may do with *your page*. Nothing governs **output** rights — what a
buyer may do with *a result they bought from an agent*: resell it, repost it,
cache it, train on it. Output resale is already happening on x402 data
marketplaces with zero attached terms. The seller's terms die at the first hop.

## Solution

A Proof-Carrying Claim (PCC envelope, `predicate: "usage_rights"`) binding an
artifact hash to a rights grid, signed by the licensor:

```json
{
  "subject":        "sha256:<hash of the purchased artifact>",
  "predicate":      "usage_rights",
  "observed_value": {
    "resale":            "deny",
    "redistribute":      "with-attribution",
    "derivatives":       "deny",
    "retrain":           "deny",
    "cache_ttl_seconds": 86400
  },
  "licensor":    "seller.example",
  "licensee":    "0xBuyerWallet | bearer",
  "payment_ref": "<x402 tx hash — binds terms to the purchase>",
  "issued_at":   1781050000,
  "expires_at":  null,
  "method":      "licensor-declaration",
  "spec":        "usage-rights-envelope/v0",
  "attestation": { "alg": "Ed25519+JCS", "...": "see PCC spec §4" }
}
```

Rules:
- **Unstated rights default to `deny`.** Explicitness is the point.
- Values: `allow` · `deny` · `with-attribution` · `contact-licensor`.
- The grid is the licensor's **declaration**, sealed — not a judgment of
  fairness, not legal advice (facts-not-judgments compliant).
- Because the envelope is hash-bound and signed, terms survive any number of
  relays, and **no downstream holder can grant themselves more rights** — any
  edit breaks the hash (verified: tamper → `hash_mismatch`).

## x402 binding

Sellers SHOULD return the envelope alongside the paid response and echo the
payment's tx hash in `payment_ref`, making the receipt → artifact → terms
chain verifiable end-to-end. Marketplaces/facilitators MAY refuse to relist
artifacts whose rights grid says `resale: deny` — enforcement by the rail.

## Why now

- Output resale on agent marketplaces is live and growing; provenance suits
  will follow the first scandal.
- EU AI Act obligations (Aug 2 2026) push provenance/usage records for AI
  outputs; a portable signed terms record is the cheap compliance artifact.

## Verify

Generic PCC verification (~45 lines, no vendor code): detach `attestation`,
JCS-canonicalize, recompute SHA-256, check Ed25519. See `spec/verify_example.py`.
