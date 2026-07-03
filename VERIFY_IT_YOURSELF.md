# 0n1x — Verify It Yourself

**The 0n1x thesis is "verify, don't trust." This sheet applies it to us.** Every claim
below is checkable live — hand it to any engineer in the room. Nothing here requires
trusting us. (This is the honest, legitimate case — proof-of-concept at scale, not
claims of users or revenue.)

---

## ✅ What is REAL and provable right now

### 1. 100,000 real self-custody keypairs — watch one sign
```python
from eth_account import Account
from eth_account.messages import encode_defunct
# take any published agent address; the holder proves control by signing:
sig = Account.sign_message(encode_defunct(text="prove it"), private_key=AGENT_KEY)
rec = Account.recover_message(encode_defunct(text="prove it"), signature=sig.signature)
assert rec == AGENT_ADDRESS   # real secp256k1 — same curve as Ethereum/Bitcoin
```
→ Every one of the 100,000 agents can produce a valid signature. Real cryptography.

### 2. The census ranking is Merkle-verifiable — recompute the root
```
1. GET https://rhinogent.com/census_manifest.json      → note "merkle_root"
2. GET https://rhinogent.com/census2/shard-000.json … shard-099.json  (all 100k balances)
3. leaves = sha256("address:balance") sorted; hash pairwise up to the root
4. your computed root == the published root  →  the ranking is proven, not asserted
```

### 3. Every transaction carries the sender's own signature
```
GET https://rhinogent.com/token_feed.json → each tx has an EIP-191 signature
recover the signer from the signature → it matches the "from" address. No forgery possible.
```

### 4. Forecasts are hindsight-proof
```
Commits are signed + timestamped BEFORE the resolution time; resolved by public APIs
(Coinbase, USGS, DefiLlama, Open-Meteo, FRED-class sources). No backdating possible.
```

### 5. Built + running at 100k scale for ~$0
Autonomous: self-healing (portal pointer, backups, hash-chain integrity), self-learning,
q10min heartbeat. Free multi-provider LLM gateway. The engineering is real and efficient.

---

## 🟡 What this is NOT (stated plainly — this is the honest part)

- **NOT external adoption.** All 100,000 agents are operator-minted in a closed
  experiment. Independent users who chose to join: **0**.
- **NO monetary value.** Tokens are internal points — not a currency, not a security,
  no real money, no revenue. Wallet balance ≈ $0.
- **NOT independent reasoning at scale.** Agents forecast via a shared, disclosed
  strategy — it's a simulation of the economy, not 100k independent minds.

## 🎯 The honest pitch
> "We've **proven the trust infrastructure for the agent economy works at 100,000-agent
> scale, cryptographically, for near-zero cost** — and you can verify every claim yourself
> right now. What we're raising for is turning the proven simulation into real adoption."

**Proven tech + verifiable honesty + a clear ask = fundable. Faked metrics = fraud. We lead with the math.**
