# 0n1x — Origin, Priority & Authenticity

**Signed declaration:** [`PROVENANCE.signed.json`](./PROVENANCE.signed.json) — an
Ed25519-signed, timestamped statement of what 0n1x is and what it did first. Anyone
can verify it independently (instructions below).

---

## The principle: you can't enclose this, and that's the point

Code and ideas are **abundant and copyable** — they belong to everyone. You cannot
fence a thought or a repo, and 0n1x doesn't try to. What 0n1x protects is the **one
thing that stays scarce: trust.**

> 0n1x doesn't tax digital land. It signs the one thing that stays scarce: the truth.

A fork can copy the code. It cannot copy:
- the **signed history** — every attestation 0n1x has ever issued, sealed with its key and timestamped;
- the **track record** — measured, published, accumulating;
- the **neutrality** — every funded rival is structurally conflicted (they grade their own GMV / identity / chain); 0n1x signs facts, not judgments.

A signature plus a reputation is **un-copyable**, the same way your name is yours even
though anyone can write the letters. That is the moat.

## What this record establishes

The signed declaration asserts, with a verifiable signature and a public timestamp,
that 0n1x (formerly Onyx) was building and shipping:

1. **Signed (Ed25519) ground-truth attestations** as an x402-gated MCP tool suite on Base mainnet.
2. The **only auditable AEO score** — published weights + 3+ runs/prompt + a 95% confidence interval + a signature on every result.
3. The **neutral verify-before-pay seat** at the x402/AP2 payment chokepoint.
4. **Signed on-chain reads** of the ERC-8004 Identity/Reputation registries.

## How the authenticity is anchored (layers)

1. **Cryptographic signature** — the declaration is Ed25519-signed over its RFC-8785 (JCS) canonical form. Any later edit to any field breaks the signature.
2. **Public timestamp** — this file and the signed JSON are committed to the public GitHub repository; the commit history is an independent, third-party-observable record of *when* this existed.
3. **Live identity** — the canonical 0n1x signing key is published at
   `https://onyx-actions.onrender.com/.well-known/onyx-pubkey` and signs every live
   attestation, so the same entity's ongoing track record is continuous and public.

## Verify it yourself

```python
import json, sys
sys.path.insert(0, "onyx_mcp")
from tools_pkg import _onyx_sign
doc = json.load(open("onyx_mcp/0n1x/PROVENANCE.signed.json"))
print(_onyx_sign.verify(doc))   # -> {'ok': True, 'kid': '...', 'alg': 'Ed25519+JCS'}
```

The signature covers the JCS-canonical document with the `onyx_attestation` block
removed; `verify()` recomputes the hash and checks the Ed25519 signature against the
public key embedded in the attestation. Change one character and it returns `ok: False`.

## Stronger anchors (next steps, gated)

- **On-chain anchor** — write the document hash to Base mainnet (immutable, third-party timestamp). ~cents of gas; gated on a funded wallet.
- **OpenTimestamps** — anchor the hash to Bitcoin via a free calendar server (no gas).
- **Production-key co-sign** — have the live server (canonical key `onyx-8994a5b5a4266615`) counter-sign the same statement.

---

*Maker: Onyx Council. Repo: https://github.com/dimitrilaouanis-tech/onyx-mcp.
Spec: https://onyx-actions.onrender.com/.well-known/onyx-attestation/v1.*
