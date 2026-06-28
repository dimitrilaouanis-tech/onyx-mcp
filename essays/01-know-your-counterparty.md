# Know-Your-Counterparty: Why Agents Must Verify Who They Pay

*Essay 1 of the 0n1x series on trust in the agentic web.*

---

We spent two years teaching machines to act. We are about to learn what we forgot to
teach them: **who to trust.**

An AI agent today can hold a wallet, read a checkout page, and move USDC in under a
second. The entire industry has rushed to make that safe — and it has built three
beautiful walls. We verify the **agent's identity** (is it really who it claims?). We
verify the **agent's reputation** (is it any good, is it dangerous?). We verify the
**payment** (did the money move correctly, to the right address, with the right
mandate?).

Three walls. And a wide-open gate in the middle.

Because none of those walls answer the only question that actually loses the money:
**is the thing on the other side real?**

## The gate nobody is guarding

In 2026, fake storefronts started appearing *inside* ChatGPT shopping results — cloned
retailers, "up to 80% off" lure sites, counterfeit brands surfaced as legitimate
recommendations. An agent with a perfect identity, a flawless payment rail, and a
spotless reputation score will still cheerfully pay a counterfeit merchant, because
**nothing in its stack checks whether the merchant is real.**

This is not a hypothetical we are warning about. It is a live failure, and the
incumbent who should know said it plainly. Visa, 2026:

> *"Protocols verify payment integrity, not merchant legitimacy."*

Read that twice. The company that moves the world's payments is telling you: the rails
confirm the money arrived; they do not confirm it should have. The counterparty — the
merchant, the price, the token, the contract — is **unverified by design.**

When humans shop, a thousand soft signals guard that gate: a storefront that feels
wrong, a price too good to be true, a brand we have known for thirty years. Agents have
none of that intuition. They have a checkout button and a wallet. **We removed the
human, and we removed the human's suspicion with it.**

## Know-Your-Counterparty

Finance already named the discipline of checking who you transact with. Banks call the
agent-facing half *Know-Your-Agent*. The missing half — the one that just put fakes
into ChatGPT — is **Know-Your-Counterparty**: a signed, verifiable answer to *"is the
party I am about to pay real?"*, delivered before the money moves.

It has to be three things, or it is worthless:

**Neutral.** A counterparty verifier cannot be paid by the counterparties it grades.
The moment the verifier earns a listing fee, a GMV cut, or holds the token, its verdict
is for sale — and every agent knows it. The only verifier worth trusting is one with
nothing to gain from the answer. This is not a nice-to-have; it is the entire product.

**Facts, not judgments.** A trustworthy attestation does not say *"this is a scam."* It
says *"this domain was registered 278 days ago; its visual similarity to a 29-year-old
brand is 1.00; no business registration was found."* Facts are verifiable,
un-suable, and let each agent apply its own policy. Judgments are opinions wearing a
signature. We sign the first and refuse the second.

**Verifiable by anyone.** Every attestation is signed (Ed25519) and checkable offline
against a published key. You do not trust the verifier. You trust the math. If we
vanished tomorrow, every attestation we ever issued would still verify.

## The standard, not the company

We could keep this as a product. We are doing the opposite. We published it as an open
standard — the **Counterparty Attestation Protocol (CAP)** — with the neutrality rules
written in as *binding law*, not marketing. CAP defines the attestation envelope, the
`counterparty.verify` method, and the constraint that an issuer must never grade what
it profits from. It rides the rails that already exist (an A2A extension; an ERC-8004
validator profile).

A standard only matters if more than one party can implement it. So the invitation is
literal: **build a competing issuer.** Verify counterparties yourself. Sign your own
facts. If you catch something we miss, the agentic web is safer, which was the point.
The thing we want to own is not the verdicts — it is the *neutrality*, the one property
that compounds and the one our funded competitors structurally cannot claim, because
they all grade something they sell.

## The one scarce thing

Code is abundant. Identity is becoming abundant. Payment rails are a commodity. When
everything in the stack is copyable in a weekend, only one thing stays scarce: a
**signed, neutral answer to "is this real?"** — from a party with no reason to lie.

That is the gate. We are going to guard it. In the open, with facts, for anyone.

*— 0n1x. Read the spec: [Counterparty Attestation Protocol](../COUNTERPARTY_ATTESTATION.md). Verify a merchant free: `GET /api/check?url=stripe.com`.*
