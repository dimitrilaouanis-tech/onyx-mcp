# The check ChatGPT didn't run: Onyx merchant-legitimacy teardown

**June 2026.** ChatGPT was caught recommending **cloned fake storefronts** —
sites impersonating real/defunct UK retailers (**Russell & Bromley**, **Dunelm**)
— that harvested shoppers' card details. The mechanism: a known brand goes
quiet (Russell & Bromley entered administration in Jan 2026), its official
presence lapses, and scammers register look-alike domains to fill the vacuum.
The model, trained/grounded on poisoned web content, surfaced the clones as
legitimate shopping sources.

## Why the payment rails missed it

Visa's own June 2026 threat write-up said it plainly:

> *"ACP and AP2 focus on payment integrity, not merchant legitimacy. An agent
> can complete a technically valid transaction with a fraudulent merchant, and
> nothing in the protocol layer flags the discrepancy."*

The card tokenizes. The protocol authorizes. The settlement clears. **Nobody
checks whether the merchant is who it claims to be.** That is a structural gap,
not a bug — and it sits one layer above every payment rail.

## What Onyx returns (signed, before the agent pays)

Onyx runs **published, objective checks** and signs the result (Ed25519, verify
offline, tamper → rejected). Bright line: Onyx attests *"this domain PASSED /
FAILED published checks"* — never *"this merchant is honest."* **Facts, not
judgments.**

Live, this session (real RDAP + TLS + fetch, signed):

| Domain | Brand claimed | Domain age | Verdict |
|---|---|---|---|
| `dunelm.com` (real retailer) | — | **9,723 days** (1999) | ✅ **PASS** |
| clone pattern `russell-bromley-outlet-sale.com` | Russell & Bromley | **19 days** | 🛑 **BLOCK** |

The clone's signed evidence and flags:
```
verdict: BLOCK
flags:  claims_brand_'Russell & Bromley'_on_19d_old_domain
        tls_cert_only_12d_old
        domain_only_19d_old
```

The single decisive fact: **a 19-day-old domain claiming a long-established
brand.** No payment protocol looks at that. Onyx signs it.

## Why this is durable (the neutrality moat)

Every funded player in the space (Mastercard, Visa, Coinbase, the agent banks)
either **moves the funds, sells the wallet, or grades its own GMV** — so they
*can't* be the neutral arbiter of merchant legitimacy. Onyx earns nothing from
any transaction it grades. That conflict-free posture is the one thing the
incumbents structurally cannot copy. a16z (Apr 2026): durable advantage belongs
to whoever can *"cryptographically certify output and absorb the liability when
it fails."*

## Where it plugs in

The signed legitimacy check belongs **at the payment chokepoint** — read by the
agent (or the x402/AP2 step) **before** funds move. A displayed badge
commoditizes; a check the agent can't transact without becomes infrastructure.

- Engine: `tools_pkg/merchant_fact_check.py` (signed raw observations).
- Verdict + demo: `onyx_scandal_teardown.py` (run it: `py onyx_scandal_teardown.py`).
- Free verification of any Onyx attestation: `/verify`.

*Run-it-yourself reproduction is the point: this is a dated, signed, falsifiable
artifact — not a slide.*
