# Onyx — Pre-Payment Verification Quickstart

*The signed check an AI agent runs **before** it pays a merchant. Wire it into one client agent in ~20 minutes.*

---

## What it does

One call, before your agent transacts, returns whether a merchant/store is real — as **signed facts**, plus a hard **PROCEED / REVIEW / HOLD** decision. Every response is **Ed25519-signed** and independently verifiable offline (no need to trust Onyx — verify the signature yourself).

## The endpoint

```
GET https://onyx-actions.onrender.com/api/check?url=<STORE_URL>
```
No API key for the pilot. Optional: `&expected_price=<n>` to flag too-good-to-be-true pricing.

## The response — exactly the fields your client agents specified

```jsonc
{
  "domain": "shop.example.com",
  "verdict": "LOOKS ESTABLISHED",          // LOOKS ESTABLISHED | BE CAREFUL | HIGH RISK
  "score": 100,                            // 0–100 trust score
  "securityStatus": { "https": true, "reachable": true, "no_offdomain_redirect": true },
  "signatureDetails": { "alg": "Ed25519+JCS", "kid": "onyx-…", "public_key": "…", "verify_at": "…/verify" },
  "businessCategory": "retail/ecommerce",
  "agenticReadinessScore": 65,             // 0–100, how agent-consumable the merchant is
  "onyx_attestation": { "...": "Ed25519 signature over the whole response" }
}
```

## Drop-in (Python) — copy `onyx_precheck.py` next to your agent

```python
from onyx_precheck import onyx_precheck

r = onyx_precheck("https://shop.example.com")     # or the merchant your agent is about to pay
if r["decision"] == "HOLD":
    abort_payment(reasons=r["reasons"])           # serious red flags — don't pay
elif r["decision"] == "REVIEW":
    flag_for_human(r)                             # caution — surface to the user
else:
    proceed_to_pay()                              # clean
```

## Drop-in (JS/TypeScript)

```js
const onyxPrecheck = async (url) => {
  const r = await fetch(`https://onyx-actions.onrender.com/api/check?url=${encodeURIComponent(url)}`);
  const d = await r.json();
  const decision = { ok: "PROCEED", caution: "REVIEW", danger: "HOLD" }[d.band] ?? "REVIEW";
  return { ...d, decision };
};

const r = await onyxPrecheck("https://shop.example.com");
if (r.decision === "HOLD") abortPayment(r.red_flags);
```

## Verifying the signature yourself (zero trust in Onyx)

Every response is signed over its RFC-8785 (JCS) canonical form with Ed25519. To verify:
1. Take the response, remove the `onyx_attestation` block.
2. JCS-canonicalize the rest, SHA-256 it → must equal `onyx_attestation.observed_hash`.
3. Verify `onyx_attestation.sig` against that canonical form using the public key at
   `https://onyx-actions.onrender.com/.well-known/onyx-pubkey`.

A 45-line reference verifier (no Onyx dependency) is at `spec/verify_example.py`, or just
`POST` any response to `https://onyx-actions.onrender.com/verify` for a free verdict
(`genuine_onyx: true` = signed by Onyx and unmodified).

## Pricing

- **First call: free** (done in the pilot — johnlewis.com came back clean + signed).
- **Then: $0.05 USDC per call over x402 on Base.** Volume pricing for your client agents.

## Bright line

Onyx attests **observable facts** (domain age, TLS, reachability, redirect, price), method disclosed per field. It does **not** claim a merchant is "honest" or "a scam" — `HOLD` means the *facts* warrant a stop; your agent's policy decides. The signature proves the observation is genuine Onyx output, untampered — not a vouch for the merchant.

---

**Wire-in path:** drop `onyx_precheck.py` in → call it before payment → branch on `decision`. ~20 minutes to a first live check. Questions: reply to this thread or hit `/verify` to confirm any result.
