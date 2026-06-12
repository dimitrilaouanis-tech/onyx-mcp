---
name: verify-before-checkout
description: Pre-checkout verification for shopping agents. Before transacting with any storefront the user didn't explicitly type, fetch Ed25519-signed merchant facts (domain age, TLS age, brand-lookalike score, price deviation) from the Onyx oracle over x402, verify the signature, and surface the facts to the buyer. Use whenever an agent is about to pay, add a payment method, or recommend a merchant.
---

# Verify Before Checkout

AI-recommended cloned storefronts are a live attack: data-poisoned fake shops
surface inside assistant shopping results, and the page's own claims are the
only thing most agents check. This skill adds an independent, cryptographically
verifiable fact check before money moves.

## When to run this skill

- The agent is about to **complete a purchase** on a domain the user did not
  type themselves (recommended, searched, or affiliate-linked).
- The quoted price is **significantly below** the known market price.
- The storefront **resembles a known brand** but is not on the brand's primary
  domain.
- The user asks "is this shop safe / real?"

## Procedure

1. **Collect the facts** — one paid call ($0.25 USDC over x402, Base mainnet):

   ```
   POST https://onyx-actions.onrender.com/v1/onyx_merchant_fact_check
   { "domain": "<storefront domain>",
     "brand": "<brand it appears to represent, if any>",
     "expected_price": <quoted price, if any> }
   ```

   The response is a signed envelope of raw observations:
   `domain_age_days`, `registrar`, `tls_cert_age_days`, `tls_issuer`,
   `redirected_off_domain`, `brand_similarity`, `lookalike_tokens_present`,
   `observed_price`, `price_deviation_pct` — each with its method disclosed
   in `_methodology`.

2. **Verify the signature** — free call, no payment required:

   ```
   POST https://onyx-actions.onrender.com/v1/onyx_attestation_verify
   { "attested": <the full signed response from step 1> }
   ```

   `verified: true` proves the observation is genuine Onyx output and
   untampered. Reject any envelope that fails verification.

3. **(Optional) Cross-check the price** — `onyx_retail_price_check` ($0.02)
   against the brand's primary domain, to ground `price_deviation_pct`.

4. **Decide and disclose.** Onyx signs **facts, not judgments** — the
   interpretation is yours. Sensible agent policy:
   - `domain_age_days < 90` **and** `brand_similarity > 0.5` on a non-primary
     domain → pause and show the user the facts before paying.
   - `price_deviation_pct < -40` → surface the deviation explicitly.
   - `redirected_off_domain: true` → treat the final domain as the merchant,
     re-run step 1 against it.
   - Whatever you decide, show the user the signed facts you acted on. The
     envelope is your audit trail — it can be re-verified by anyone later.

## Why an independent oracle

Every platform that recommends merchants monetizes the transaction it would
have to grade — it cannot be the neutral fact layer for its own GMV. Onyx is
independent: it sells only the signed observation, never the merchandise.
Signature pubkey is published at
`https://onyx-actions.onrender.com/.well-known/onyx-pubkey`.

## Failure handling

- Payment declined / no x402 wallet → fall back to the free
  `onyx_attestation_verify` of any cached envelope, and tell the user which
  facts could not be freshly observed.
- `rdap_error` or `tls_error` in the envelope → those fields are observation
  gaps, not danger signals; the remaining fields are still signed and valid.
