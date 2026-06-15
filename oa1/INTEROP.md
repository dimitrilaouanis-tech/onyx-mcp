# OA-1 interop: how it composes with the rest of the accountability stack

OA-1 is deliberately *one layer*. It does not do identity, enforcement, or
payment — it makes a claim **verifiable offline** and lets a real **outcome** be
bound back to it. That means it sits *underneath* or *beside* projects that
already do the other layers, and strengthens them rather than competing.

## OA-1 ⟂ the neighbors

| Project / standard | What it owns | Where OA-1 adds value |
|---|---|---|
| **ERC-8004** | on-chain agent identity + reputation registry | OA-1 says whether a given *claim* an agent made turned out true; ERC-8004 says *who* the agent is. Reputation = identity + a track record; OA-1 supplies the measured track record. |
| **Agent Passport System (APS)** | delegation that can only narrow, gateway enforcement, signed receipts per action | APS receipts are signed in-house. Wrapping a receipt in an OA-1 envelope makes it verifiable by *anyone* with one file and no APS dependency, and lets the *outcome* of the enforced action be bound back to the receipt — turning "we denied this" into "here is the measured rate at which our denials were correct." |
| **AR-1 (Onyx Action Receipt)** | payment → side-effect evidence | sibling spec, shared keys; AR-1 proves an action *happened*, OA-1 scores a *claim* against reality. |
| **A2A** | agent-to-agent messaging | embed an OA-1 envelope in a task artifact → cross-agent claims become verifiable, not conversational. |

## The composition that matters: enforcement + outcome

An enforcement layer (APS, a boundary gate, any allow/deny service) emits a
decision. Today that decision is a dead end — signed, then forgotten. With OA-1:

```
1. enforce        -> {decision: "deny", reason: "...", ...}
2. sign (OA-1)    -> oa1.sign(decision, tool="aps_gateway", issuer="aps")
                     # now anyone verifies it offline; the signed hash is its id
3. act
4. bind outcome   -> oa1.bind_outcome(decision, "blocked_real_exploit")
                     # only attaches because the signature verifies
5. publish rate   -> "of N denials, X% bound to a confirmed-bad outcome"
```

Step 5 is the thing no enforcement layer has yet: a **measured** record of how
often its decisions were right, that a third party can audit because every
decision is a verifiable claim and every outcome is bound to one.

OA-1 is issuer-neutral by design (`oa1/oa1.py`, MIT). Any project can adopt it
with its own keypair — the `kid` identifies the issuer, the envelope is shared.
A claim signed by one OA-1 issuer verifies with every other OA-1 verifier.

Spec (CC0): https://onyx-actions.onrender.com/.well-known/onyx-attestation/v1
