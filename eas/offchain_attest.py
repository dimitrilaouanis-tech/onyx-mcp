"""0n1x merchant-fact attestations — EAS OFFCHAIN lane (zero gas, live today).

Produces an EIP-712-signed EAS offchain attestation over the merchant-fact
schema. No transaction, no funding — the signature IS the artifact. Anyone can
verify it against the attester address; the same payload can later be anchored
onchain via EAS.attest() once the registrar wallet is funded.

    py eas/offchain_attest.py --domain example.com --fact-type domain_age_days \
        --fact-json "{\"days\":278}" --evidence-file evidence.json

Attester key from env EAS_ATTESTER_KEY (falls back to ONYX_FACT_KEY). Never
printed, never written. Output: attestation JSON on stdout (safe to publish).

⚠️ easscan.org offchain-verify compatibility should be re-confirmed against the
deployed EAS version before advertising "verify on easscan" — our own /verify
path is the primary consumer either way.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import time

from eth_abi import encode as abi_encode
from eth_account import Account
from eth_account.messages import encode_typed_data
from web3 import Web3

CHAIN_ID = 8453  # Base mainnet
EAS = "0x4200000000000000000000000000000000000021"
SCHEMA = ("string domain,string factType,string factJson,"
          "bytes32 evidenceHash,uint64 observedAt,uint16 specVersion")
RESOLVER = "0x0000000000000000000000000000000000000000"
REVOCABLE = True
ZERO32 = "0x" + "00" * 32
ZERO_ADDR = "0x0000000000000000000000000000000000000000"


def schema_uid() -> str:
    h = Web3.keccak(SCHEMA.encode() + bytes.fromhex(RESOLVER[2:]) + (b"\x01" if REVOCABLE else b"\x00"))
    return "0x" + h.hex().replace("0x", "")


def encode_data(domain: str, fact_type: str, fact_json: str,
                evidence_hash: bytes, observed_at: int) -> bytes:
    """ABI-encode the attestation data exactly per the schema field order."""
    return abi_encode(
        ["string", "string", "string", "bytes32", "uint64", "uint16"],
        [domain, fact_type, fact_json, evidence_hash, observed_at, 1],
    )


def attest(domain: str, fact_type: str, fact_json: str, evidence: bytes, key: str) -> dict:
    # Canonical-ize inputs; facts not judgments — factType/factJson carry data only.
    domain = domain.lower().strip().removeprefix("https://").removeprefix("http://").strip("/")
    json.loads(fact_json)  # must be valid JSON
    observed_at = int(time.time())
    evidence_hash = Web3.keccak(evidence)
    data = encode_data(domain, fact_type, fact_json, evidence_hash, observed_at)
    salt = "0x" + secrets.token_bytes(32).hex()

    typed = {
        "domain": {"name": "EAS Attestation", "version": "1.2.0",
                   "chainId": CHAIN_ID, "verifyingContract": EAS},
        "primaryType": "Attest",
        "types": {
            "Attest": [
                {"name": "version", "type": "uint16"},
                {"name": "schema", "type": "bytes32"},
                {"name": "recipient", "type": "address"},
                {"name": "time", "type": "uint64"},
                {"name": "expirationTime", "type": "uint64"},
                {"name": "revocable", "type": "bool"},
                {"name": "refUID", "type": "bytes32"},
                {"name": "data", "type": "bytes"},
                {"name": "salt", "type": "bytes32"},
            ],
        },
        "message": {
            "version": 2,
            "schema": schema_uid(),
            "recipient": ZERO_ADDR,
            "time": observed_at,
            "expirationTime": 0,
            "revocable": REVOCABLE,
            "refUID": ZERO32,
            "data": "0x" + data.hex(),
            "salt": salt,
        },
    }
    acct = Account.from_key(key)
    signed = Account.sign_message(encode_typed_data(full_message=typed), private_key=key)
    sig_hex = signed.signature.hex()
    if not sig_hex.startswith("0x"):
        sig_hex = "0x" + sig_hex
    return {
        "sig_kind": "eas-offchain-v2",
        "attester": acct.address,
        "schema_uid": schema_uid(),
        "schema": SCHEMA,
        "message": typed["message"],
        "signature": sig_hex,
        "fact": {"domain": domain, "factType": fact_type, "factJson": fact_json,
                 "evidenceHash": "0x" + evidence_hash.hex().replace("0x", ""),
                 "observedAt": observed_at, "specVersion": 1},
    }


def verify(att: dict) -> bool:
    """Recover the signer of an attestation produced by attest()."""
    typed = {
        "domain": {"name": "EAS Attestation", "version": "1.2.0",
                   "chainId": CHAIN_ID, "verifyingContract": EAS},
        "primaryType": "Attest",
        "types": {"Attest": [
            {"name": "version", "type": "uint16"},
            {"name": "schema", "type": "bytes32"},
            {"name": "recipient", "type": "address"},
            {"name": "time", "type": "uint64"},
            {"name": "expirationTime", "type": "uint64"},
            {"name": "revocable", "type": "bool"},
            {"name": "refUID", "type": "bytes32"},
            {"name": "data", "type": "bytes"},
            {"name": "salt", "type": "bytes32"},
        ]},
        "message": att["message"],
    }
    rec = Account.recover_message(encode_typed_data(full_message=typed),
                                  signature=att["signature"])
    return rec.lower() == att["attester"].lower()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", required=True)
    ap.add_argument("--fact-type", required=True)
    ap.add_argument("--fact-json", required=True)
    ap.add_argument("--evidence-file", help="raw evidence bundle to hash")
    args = ap.parse_args()

    key = os.environ.get("EAS_ATTESTER_KEY") or os.environ.get("ONYX_FACT_KEY") or ""
    if not key:
        print("set EAS_ATTESTER_KEY (or ONYX_FACT_KEY)", file=sys.stderr)
        return 1
    evidence = open(args.evidence_file, "rb").read() if args.evidence_file else b""
    att = attest(args.domain, args.fact_type, args.fact_json, evidence, key)
    assert verify(att), "self-verify failed"
    print(json.dumps(att, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
