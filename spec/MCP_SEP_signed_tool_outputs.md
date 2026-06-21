# SEP: Signed Tool Outputs (Proof-Carrying Tool Results)

- **Status:** Draft (prepared for filing as an SEP issue at modelcontextprotocol/modelcontextprotocol)
- **Type:** Standards Track — protocol extension
- **Relates to:** SEP-1766 (tool digest pinning — which reserved "signatures, provenance for future phases"; this SEP is that phase)
- **Author:** Onyx Protocol (reference implementation live)
- **Created:** 2026-06-10

## Abstract

MCP secures *which tool* runs (SEP-1766 digests) but not *what the tool returned*.
A tool result relayed from server → client → model → another agent carries no
integrity or provenance. This SEP defines an OPTIONAL, backwards-compatible
envelope by which a server attaches a detached signature to any tool result, so
any downstream consumer — including agents two hops away — can verify, offline
and in microseconds, that the result is exactly what the named issuer produced.

## Motivation

1. **Cross-agent relay.** Tool outputs increasingly become *inputs to other
   agents* (A2A, x402 data purchases). Today a relayed result is
   indistinguishable from a hallucinated or tampered one.
2. **Paid results.** When tool calls are paid (x402, marketplace MCP servers),
   buyers need proof the artifact came unmodified from the seller.
3. **Audit.** Enterprises need an audit trail binding a model's action to the
   exact tool evidence it acted on.

## Specification

A server MAY include a `signature` field in any `CallToolResult`:

```json
{
  "content": [{ "type": "text", "text": "{...result json...}" }],
  "_meta": {
    "io.modelcontextprotocol/signature": {
      "alg": "Ed25519+JCS",
      "kid": "issuer-1b69b1d26518057c",
      "public_key": "<base64url raw 32-byte key>",
      "payload_hash": "sha256:<hex of JCS-canonical signed body>",
      "signed_at": 1781050001,
      "verify_pubkey_at": "https://<server-host>/.well-known/pubkey",
      "sig": "<base64url Ed25519 over the canonical bytes>"
    }
  }
}
```

- **Canonicalization:** RFC 8785 (JCS). The signed body is the result content
  with the signature block removed. (Identical construction to the W3C
  Data Integrity `eddsa-jcs-2022` cryptosuite; a result + signature is
  losslessly expressible as a VC 2.0 with DataIntegrityProof.)
- **Algorithms:** `Ed25519+JCS` REQUIRED baseline; `ML-DSA-65+JCS`
  pre-registered for post-quantum. Unknown `alg` → treat as unsigned.
- **Verification:** detach block → JCS-canonicalize → recompute SHA-256 →
  verify Ed25519. Verifiers MUST treat hash or signature failure as
  *unverified data*, not as an error fatal to the session.
- **Key discovery:** servers publishing signatures MUST serve their active
  keys at `/.well-known/pubkey` (JWKS-compatible). Clients MAY pin keys.
- **Backwards compatibility:** the block rides in `_meta`; clients that do not
  understand it ignore it. No negotiation required. A client MAY advertise
  `capabilities.signedResults: true` to request signing where available.

## Rationale

- `_meta` placement = zero breaking change, mirrors how SEP-1766 carries digests.
- JCS over JSON-LD canonicalization: no context resolution, no network, ~µs.
- Detached signature (not JWS-wrapping the content): result stays readable to
  models and existing clients unchanged.

## Security considerations

Proves *who produced what, unmodified* — not that the output is true. Issuer
trust composes with server identity (registry entries, ERC-8004, signed
AgentCards). Replay is bounded by `signed_at` + verifier staleness policy.
Canonicalization mismatches MUST reject (no lenient re-parse).

## Reference implementation

Live since May 2026: `https://onyx-actions.onrender.com` — every tool result
carries this envelope; an independent 45-line verifier (no vendor code) is
published alongside the spec. Signing core is ~170 lines of Python.
