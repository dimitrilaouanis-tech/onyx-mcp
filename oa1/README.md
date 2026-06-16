# OA-1 — Onyx Attestation (reference SDK)

**Make any service's output a verifiable claim, then bind what actually happened to it.**

MCP lets agents *act*. A2A lets them *talk*. x402 lets them *pay*. ERC-8004 says *who* they are.
OA-1 is the missing layer: **proof of what a service claimed, and how it turned out.** One file,
one dependency (`cryptography`), no account, offline verification.

Full spec (CC0): https://onyx-actions.onrender.com/.well-known/onyx-attestation/v1

## 60-second integration

```python
from oa1 import sign, verify, claim_id, bind_outcome

# 1. Sign anything you return. (Mint a key once: oa1.generate_key() -> store as a secret.)
result = sign({"verdict": "BLOCK", "risk_score": 100}, tool="my_security_tool")
#   result["onyx_attestation"] = {alg, kid, public_key, observed_hash, sig, ...}

# 2. Anyone verifies it offline — no network, no trust in you, just math.
verify(result)        # {"ok": True, "kid": "onyx-..."}

# 3. The signed hash is a stable claim id. Bind a real outcome to it later.
cid = claim_id(result)                         # "sha256:..."
bind_outcome(result, "drained", detail="confirmed loss")   # only binds if the sig verifies
```

That's the whole protocol: **sign the claim, verify offline, bind the outcome.**

## Why it matters

- **Self-contained.** Every envelope carries its own public key. Verification needs no registry and no call back to the issuer.
- **Content-addressed.** The claim's id *is* the hash of the claim. No id server.
- **Issuer-neutral.** Bring your own keypair and you are a first-class OA-1 issuer — your `kid` identifies you. The `onyx_attestation` field name is the shared protocol slot, nothing more.
- **Tamper-evident outcomes.** An outcome can only attach to a claim whose signature verifies, so a track record built from OA-1 outcomes can't be poisoned with claims you never made.
- **Interoperable.** This SDK is byte-for-byte compatible with the Onyx production signer: a claim signed by either verifies with the other. (See `example.py`.)

## The envelope

```json
{
  "your": "payload", "stays": "untouched",
  "onyx_attestation": {
    "alg": "Ed25519+JCS",
    "kid": "<issuer>-<first16 hex of sha256(pubkey)>",
    "public_key": "<base64url raw 32-byte Ed25519 public key>",
    "tool": "<what produced this>",
    "observed_hash": "sha256:<hash of JCS payload w/o this field> = the claim id",
    "signed_at": 1750000000,
    "spec": "https://onyx-actions.onrender.com/.well-known/onyx-attestation/v1",
    "sig": "<base64url Ed25519 signature over the same canonical bytes>"
  }
}
```

Verify = strip `onyx_attestation`, JCS-canonicalize the rest (RFC-8785: sorted keys, compact,
UTF-8, no ascii-escaping), recompute sha256 (must equal `observed_hash`), check `sig` with
`public_key`. Four steps, done in `verify()`.

## JavaScript / TypeScript (`oa1.js`)

Most agents run on JS, so OA-1 ships a Node sibling with the **same API and
zero dependencies** (Node's built-in `crypto` — no npm install):

```js
const { sign, verify, claimId, bindOutcome, generateKey } = require('./oa1');

const result = sign({ verdict: 'BLOCK', risk_score: 100 }, { tool: 'my_tool' });
verify(result);   // { ok: true, kid: 'onyx-...' }
claimId(result);  // 'sha256:...'
```

CLI: `node oa1.js envelope.json` verifies a file.

**Cross-language interop is proven both ways:** a claim signed by `oa1.js`
verifies in `oa1.py` (and the Onyx production signer), and vice-versa —
byte-identical JCS canonicalization. Run `node example.js` to see it live.

## Install

No package manager needed — copy one file into your project:
- **Python:** `oa1.py` (`pip install cryptography`) → `python example.py`
- **JavaScript:** `oa1.js` (no deps, Node ≥18) → `node example.js`

Both are also publishable as-is (Python module / npm `oa1`).

## License

`oa1.py`, `oa1.js`, and the examples: MIT. Spec text: CC0. Implement freely.
