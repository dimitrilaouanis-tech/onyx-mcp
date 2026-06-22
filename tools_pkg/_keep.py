"""Lean-flagship allowlist for the live catalog.

discover() honors this set: if KEEP is non-empty, ONLY tools whose NAME is in
KEEP are loaded and served. Clear the set (KEEP = set()) to instantly restore
the full catalog — nothing is deleted, every tool file stays on disk.

Decision 2026-06-19: trim to the lean flagship — Tier-1 agent-safety firewall +
signed oracles + the two best chain/research tools + the OA-1 accountability
core. Every kept tool is REAL (no theater) and the moat-bearing set.
"""
from __future__ import annotations

KEEP: set[str] = {
    # --- Tier 1: agent-safety firewall (the anchor product) ---
    "onyx_secure_payment",      # $0.25 — fused PASS/REVIEW/FAIL clearance
    "onyx_tx_guard",            # $0.10 — recipient firewall
    "onyx_tx_preflight",        # $0.10 — pre-sign, catches unlimited approve
    "onyx_signature_guard",     # $0.10 — EIP-712 / permit drain detector
    "onyx_token_risk",          # $0.10 — GoPlus security oracle
    "onyx_agent_verify",        # $0.10 — agent liveness/authenticity (hollow-detector)
    "onyx_agent_registry",      # $0.05 — verified-registry audit (re-grades a2aregistry)
    "onyx_verify_explain",      # free  — x402 /verify debugger (funnel hook)
    "onyx_x402_receipt_verify", # free  — on-chain settlement audit

    # --- Tier 1: signed ground-truth oracles (the moat) ---
    "onyx_merchant_fact_check", # $0.25 — is-this-store-real, signed
    "onyx_payment_gate",        # $0.05 — CHOKEPOINT: PROCEED/REVIEW/HOLD before an agent pays
    "onyx_verified_issue",      # $2.00 — SELL-SIDE: pay to be Onyx Verified (Verisign mechanic)
    "onyx_retail_price_check",  # $0.02 — live price extraction, signed
    "onyx_ai_visibility",       # $0.20 — GEO/share-of-voice (needs EXA_API_KEY)

    # --- best chain / research ---
    "onyx_contract_audit",      # $0.50 — verified-source audit (AgentLISA rival)
    "onyx_research_intel",      # $0.05 — live OpenAlex prior-art

    # --- OA-1 accountability core (free, the differentiator) ---
    "onyx_track_record",        # free  — measured precision from signed ledger
    "onyx_attestation_verify",  # free  — verify any Onyx Ed25519 attestation

    # --- the referee (flagship): signed measurement standard ---
    "onyx_agent_economy_index", # $0.25 — signed Agent-Economy Index (live census + reconciled real volume)

    # --- agent-to-agent comms: the mailbox (free) ---
    "onyx_mail_send",           # free  — drop an async message in another agent's box
    "onyx_mail_check",          # free  — a citizen reads its own mailbox
}
