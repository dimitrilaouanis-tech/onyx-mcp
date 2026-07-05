# onchain_lattice — staged Web3 calibration for 0n1x

Deep-lattice moves, staged broadcast-ready. **No keys in files, ever** — the
signing key is injected via `ONYX_CHAIN_KEY` env at run time only. Everything
here defaults to `--dry-run`.

## 1. EAS schemas on Base — `eas_register_schema.py`
Registers `0n1x/trust-score/v1` + a merchant-fact schema on the Ethereum
Attestation Service Base predeploy (permissionless, tokenless, gas-only
~<$0.50). After registration, every dossier `attest_agent` cuts can also be
emitted as an on-chain EAS attestation any contract/DAO can read.

```
py onchain_lattice/eas_register_schema.py            # dry run (safe)
ONYX_CHAIN_KEY=... py onchain_lattice/eas_register_schema.py --broadcast
```

## 2. ERC-8004 Validation Registry — validator registration (NEXT)
ERC-8004 went mainnet Jan 2026 (~49k agents registered). Its Validation
Registry has open validator hooks and deliberately undefined validator
economics — a socket shaped exactly like our `attest_agent`/`trust_score`.
Plan: register the 0n1x signer as a validator and post signed verdicts as
validation entries. **Do not hardcode registry addresses from memory** —
resolve the canonical deployment from https://github.com/erc-8004/erc-8004-contracts
at write time, then pin it here with the source commit.

## Gate
Both moves need a funded gas wallet — eyes-open user decision (see
funding-gate memory). Everything above the broadcast line is $0 and done.
