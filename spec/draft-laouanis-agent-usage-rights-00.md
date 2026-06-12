---
title: "The Usage-Rights Envelope: Signed Output Terms for Agent-to-Agent Commerce"
abbrev: "Agent Usage Rights"
docname: draft-laouanis-agent-usage-rights-00
category: info
submissiontype: IETF
ipr: trust200902
area: "Applications and Real-Time"
workgroup: "Individual Submission (target: WIMSE / dispatch)"
keyword: [ai-agents, usage-rights, attestation, x402, provenance]
author:
  - fullname: Dimitri Laouanis
    organization: Onyx Protocol
    email: dimitrilaouanis@gmail.com
normative:
  RFC8785:
  RFC8032:
informative:
---

# Abstract

When an autonomous agent purchases an output from another agent (over
HTTP-native payment protocols such as x402, or task protocols such as A2A),
no machine-readable record exists of what the buyer may do with that output:
resell it, redistribute it, cache it, derive from it, or use it as model
training data. Input-side rights are addressed by robots.txt-era conventions
and RSL 1.0; the output side of the transaction is unspecified. This document
defines the Usage-Rights Envelope: a small, digitally signed JSON object,
bound to the purchased artifact by cryptographic hash, that declares the
licensor's terms and travels with the artifact across any number of relays.
Verification is offline and issuer-agnostic: Ed25519 over the JCS (RFC 8785)
canonical form. A reference implementation is publicly deployed.

# Introduction

## The missing half of an agent transaction

Payment protocols for autonomous agents settle the *payment* (x402, AP2);
task protocols settle the *exchange* (A2A Task/Artifact). Neither encodes
the post-delivery rights of the buyer. As agent-to-agent resale of purchased
outputs is already observable on public x402 marketplaces, every output that
changes hands without attached terms is a future dispute: the seller's terms
die at the first hop.

## Design goals

1. **Hash-bound:** terms attach to the exact bytes they license; any
   alteration of the artifact orphans the envelope.
2. **Offline-verifiable:** any third party verifies with ~40 lines of code
   and no contact with the issuer.
3. **Relay-proof:** because the envelope is signed, no downstream holder can
   grant themselves broader rights (verified failure mode: any edit produces
   a hash mismatch).
4. **Declaration, not judgment:** the envelope attests what the licensor
   DECLARED at issue time. It is not legal advice and carries no fairness
   judgment.

# The Usage-Rights Envelope

## Structure

~~~json
{
  "subject":        "sha256:<hex of JCS-canonical artifact>",
  "predicate":      "usage_rights",
  "observed_value": {
    "resale":            "deny",
    "redistribute":      "with-attribution",
    "derivatives":       "with-attribution",
    "retrain":           "deny",
    "cache_ttl_seconds": 3600
  },
  "licensor":    "seller.example",
  "licensee":    "bearer",
  "payment_ref": "<payment tx hash or receipt id>",
  "issued_at":   1781050000,
  "expires_at":  null,
  "method":      "licensor-declaration",
  "spec":        "usage-rights-envelope/v0",
  "attestation": {
    "alg": "Ed25519+JCS",
    "kid": "<key id>",
    "public_key": "<base64url raw 32 bytes>",
    "observed_hash": "sha256:<hex>",
    "sig": "<base64url Ed25519 signature>"
  }
}
~~~

## Rights vocabulary (v0)

| Key | Values | Meaning |
|-----|--------|---------|
| resale | allow / deny / with-attribution / contact-licensor | Sell the raw output onward |
| redistribute | (same) | Pass the raw output to third parties |
| derivatives | (same) | Produce derived work |
| retrain | (same) | Use as model-training data |
| cache_ttl_seconds | integer | Maximum retention of a raw copy |

Unstated rights default to **deny**. Unknown keys MUST be ignored.

## Signature

The signature covers the JCS (RFC 8785) canonical form of the envelope with
the `attestation` member removed, using Ed25519 (RFC 8032). This profile is
byte-compatible with the W3C Data Integrity `eddsa-jcs-2022` cryptosuite,
permitting verification by existing Verifiable Credential tooling.

## Transport bindings

* **HTTP / x402:** the seller returns the envelope in an `X-Onyx-Rights`
  response header (base64url of the compact JSON) alongside payment receipt
  headers, echoing the payment reference in `payment_ref`.
* **A2A:** the envelope is carried in `Artifact.metadata` under the key
  `usage_rights` (data-only extension).
* **Server default policy:** an issuer publishes its signed default grid at
  `/.well-known/rights.json`.

# Security Considerations

The envelope proves *what the licensor declared*, not that the declaration
is legally sufficient in any jurisdiction. Key compromise allows forged
declarations until the key is rotated; issuers SHOULD publish keys at a
stable `.well-known` location so rotation is observable. The envelope does
not prevent a malicious buyer from violating terms; it makes the terms
portable, provable, and non-repudiable, which is the prerequisite for any
downstream enforcement (marketplace delisting, reputation systems, courts).

# IANA Considerations

This document has no IANA actions in -00. A future revision may register
the `X-Onyx-Rights` header field name (or a vendor-neutral successor) in
the HTTP Field Name Registry.

# Reference Implementation

A live, publicly verifiable implementation (issuer, per-response stamping,
free verification endpoint, and signed policy card) is deployed at
`https://onyx-actions.onrender.com` (spec mirror:
`github.com/dimitrilaouanis-tech/onyx-mcp/blob/main/spec/USAGE_RIGHTS_v0.md`),
including an independent 45-line verifier with no vendor imports.

--- back

# Acknowledgments

Thanks to the x402, A2A, and RSL communities, whose work defines the
adjacent layers this document deliberately rides rather than replaces.
