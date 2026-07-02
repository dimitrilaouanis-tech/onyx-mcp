# 0n1x Merchant-Fact Schema — EAS on Base

The land-grab move: the first **merchant/commerce-fact attestation schema** on
Ethereum Attestation Service (Base mainnet). Tokenless, composable, consumable by
any agent pre-purchase — the open counterweight to card-rail-proprietary merchant
trust (Mastercard Merchant Trust Services) and escrow facilitators (Trustap).

## The schema (v1)

```
string domain,string factType,string factJson,bytes32 evidenceHash,uint64 observedAt,uint16 specVersion
```

| Field | Meaning |
|---|---|
| `domain` | The merchant domain the fact is about, lowercase, no scheme (`example.com`) |
| `factType` | Namespaced fact kind: `domain_age_days` · `tls_valid` · `whois_created` · `price_observed` · `storefront_similarity` · `payment_rails_seen` · `contact_verified` … |
| `factJson` | The fact value as canonical JSON (`{"days":278}`, `{"price":"29.90","currency":"EUR","sku":"..."}`) |
| `evidenceHash` | keccak256 of the raw evidence bundle (headers, body hash, screenshots manifest) — the bundle itself is served/archived off-chain |
| `observedAt` | Unix seconds of the observation |
| `specVersion` | Fact-spec version (1) — semantics of factType/factJson frozen per version |

**Hard rule honored: facts, not judgments.** No PROCEED/HOLD verdicts on-chain —
`_merchant_signal.py` composes verdicts *from* these facts off-chain and can cite
attestation UIDs as its evidence. Anyone can recompute their own judgment from the
same signed facts. That's the neutrality moat in schema form.

- **Revocable: true** — a fact superseded or observed in error is revoked, never edited.
- **Resolver: 0x0** — no gatekeeping contract; the schema is open. Trust comes from
  WHO attests (our attester address + earned track record), not from write-permission.
- **Recipient**: unused (0x0) in v1 — facts are about domains, not addresses.

## Contracts (Base mainnet — OP-stack predeploys)

- SchemaRegistry: `0x4200000000000000000000000000000000000020`
- EAS:            `0x4200000000000000000000000000000000000021`
- Explorer: https://base.easscan.org

## Two lanes, one schema

1. **Offchain attestations (LIVE NOW, zero gas)** — EIP-712-signed EAS offchain
   attestations over this schema, produced by `offchain_attest.py`. Verifiable by
   anyone with the attester address. This starts the signed corpus TODAY.
   ⚠️ easscan offchain-verify compatibility should be re-confirmed against the
   deployed EAS version before publicizing "view it on easscan".
2. **Onchain registration + attestations (one gas gate)** — `register_schema.py`
   registers the schema (one-time, ~cents on Base). Onchain attests then anchor
   high-value facts. GATED: needs a funded key + explicit user go (eyes-open rule).

## Operational notes

- Schema UID = `keccak256(abi.encodePacked(schemaString, resolver, revocable))` —
  deterministic; known before registration and printed by the dry-run.
- Attester key = the 0n1x signer wallet. NEVER the admin key, NEVER printed.
- Every attestation we publish also lands in our own signed ledger (event store) —
  EAS is the public anchor, not the primary store.
