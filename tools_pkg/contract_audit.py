"""onyx_contract_audit — AgentLISA's flagship, but x10: audit the DEPLOYED reality.

AgentLISA audits Solidity source in a vacuum and charges $0.50-$5. We do that
AND the thing a static audit structurally cannot: we check the contract AS
DEPLOYED on Base — is it an upgradeable proxy the owner can swap after the
audit? Is it already self-destructed? — fuse that with curated static vuln
detectors and an optional AI deep-pass, score it, and SIGN the verdict.

  Source        Blockscout verified source (free, no key)
  On-chain      proxy/upgradeability + self-destruct + verification status
  Static        curated high-signal detectors (tx.origin auth, delegatecall,
                selfdestruct, unchecked low-level call, unprotected init,
                owner mint/pause/blacklist, mutable fees, assembly, …)
  AI deep-pass  optional Claude (Sonnet 4.6) structured findings — only if
                ANTHROPIC_API_KEY is set; degrades gracefully without it
  Verdict       ALLOW / REVIEW / BLOCK + 0-100 risk score, Ed25519-signed

Why x10: a clean source audit that misses a secretly-upgradeable proxy is how
people get rugged AFTER the audit. We catch the deployed reality, and every
finding carries a verifiable onyx_attestation a pure-LLM audit can't produce.

Bright line: reads public verified source + public on-chain state. Makes no
claim about the legal identity of any deployer.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request

from . import _onyx_sign
from . import base_contract_verify as _bcv

NAME = "onyx_contract_audit"
PRICE_USDC = "0.50"
TIER = "metered"
DESCRIPTION = (
    "Full smart-contract security audit for any Base address — source + "
    "DEPLOYED reality + AI, SIGNED. Fetches verified source, runs curated "
    "static vuln detectors (tx.origin auth, delegatecall, selfdestruct, "
    "unchecked calls, unprotected init, owner mint/pause/blacklist, mutable "
    "fees), AND flags the live on-chain risks a static audit misses — "
    "upgradeable proxies (owner can swap logic post-audit) and self-destructed "
    "contracts. Optional Claude deep-pass for novel bugs. Returns ALLOW/REVIEW/"
    "BLOCK + 0-100 risk score, every finding Ed25519-signed. Cheaper than a "
    "manual audit, and unlike one it audits the contract as actually deployed."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "address": {
            "type": "string",
            "description": "Contract address on Base mainnet (0x... 20-byte hex).",
        },
        "deep": {
            "type": "boolean",
            "default": True,
            "description": "Run the optional AI deep-pass for novel/business-logic bugs (only fires if the server has an AI key configured; degrades gracefully otherwise).",
        },
    },
    "required": ["address"],
}

_MODEL = "claude-sonnet-4-6"
_SEV = {"critical": 30, "high": 20, "medium": 10, "low": 4}


class _D:
    __slots__ = ("title", "rx", "severity", "category", "why")

    def __init__(self, title, pattern, severity, category, why):
        self.title = title
        self.rx = re.compile(pattern, re.I)
        self.severity = severity
        self.category = category
        self.why = why


# Curated high-signal detectors — these catch the OWASP/SWC classes most real
# exploits use. Not a replacement for a full audit; the highest-leverage gates.
_DETECTORS = [
    _D("tx.origin used for authorization", r"\btx\.origin\b", "high", "access-control",
       "tx.origin auth is phishable — a malicious contract can relay a victim's call. Use msg.sender."),
    _D("delegatecall present", r"\bdelegatecall\b", "high", "code-injection",
       "delegatecall runs external code in this contract's storage context — a classic proxy/arbitrary-execution risk. Confirm the target is fixed and trusted."),
    _D("selfdestruct / suicide", r"\b(selfdestruct|suicide)\b", "high", "liveness",
       "The contract can be destroyed, taking funds/logic with it. Confirm it's gated and intended."),
    _D("unchecked low-level call", r"\.call\{[^}]*value", "medium", "reentrancy",
       "Low-level .call{value:} forwards all gas and can re-enter. Verify checks-effects-interactions + a reentrancy guard."),
    _D("unprotected initializer", r"function\s+initialize\s*\(", "high", "access-control",
       "An initialize() that isn't guarded by an initializer/onlyOwner modifier can be front-run and seized at deploy."),
    _D("owner mint authority", r"function\s+\w*mint\w*\s*\([^)]*\)[^{]*\bonly", "high", "tokenomics",
       "Owner can mint tokens — supply is not fixed. Dilution / rug risk unless ownership is renounced."),
    _D("pausable by owner", r"\bwhenNotPaused\b|function\s+pause\s*\(", "medium", "central-control",
       "Owner can pause transfers — funds can be frozen at will."),
    _D("blacklist mechanism", r"blacklist|_blocked|isBlocked|denylist", "medium", "central-control",
       "A blacklist lets the owner block specific addresses from transacting — honeypot-adjacent."),
    _D("mutable transfer fee", r"function\s+set\w*[Ff]ee\s*\(|_fee\s*=", "medium", "tokenomics",
       "Transfer fees can be changed by the owner — a hidden-fee / honeypot vector. Check the max-fee cap."),
    _D("inline assembly", r"\bassembly\s*\{", "low", "review",
       "Inline assembly bypasses Solidity safety checks — needs manual review of each block."),
    _D("ownership not renounced (transferOwnership)", r"\btransferOwnership\b", "low", "central-control",
       "Owner role is active and transferable — privileged functions remain under owner control."),
    _D("approve race (no SafeERC20)", r"function\s+approve\s*\(", "low", "erc20",
       "Raw approve() is subject to the approve-race; SafeERC20/increaseAllowance is safer (informational)."),
]


_AUDIT_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                    "category": {"type": "string"},
                    "detail": {"type": "string"},
                },
                "required": ["title", "severity", "category", "detail"],
                "additionalProperties": False,
            },
        },
        "overall": {"type": "string"},
    },
    "required": ["findings", "overall"],
    "additionalProperties": False,
}

_SYS = (
    "You are a senior smart-contract security auditor. Analyze the Solidity "
    "source for real, exploitable vulnerabilities: reentrancy, access-control "
    "gaps, integer/logic errors, unchecked external calls, oracle/price "
    "manipulation, business-logic flaws, and rug vectors (mint, fee, pause, "
    "blacklist). Report only genuine findings with concrete impact — no style "
    "nits, no false positives. Be precise and conservative."
)


def _llm_audit(source: str, name: str) -> list | None:
    """Optional Claude deep-pass. Returns findings list, or None if no key / failure."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        return None
    src = source[:50000]  # bound tokens (~15K) for cost/latency
    body = {
        "model": _MODEL,
        "max_tokens": 4096,
        "system": _SYS,
        "messages": [{
            "role": "user",
            "content": f"Audit Solidity contract '{name}'. Report exploitable findings as JSON.\n\n```solidity\n{src}\n```",
        }],
        "output_config": {"format": {"type": "json_schema", "schema": _AUDIT_SCHEMA}},
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode(),
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            resp = json.load(r)
        text = next((b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text"), "")
        data = json.loads(text)
        out = data.get("findings", [])
        return out if isinstance(out, list) else None
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, KeyError):
        return None


def run(address: str = "", deep: bool = True, **_: object) -> dict:
    address = (address or "").strip()
    if not (address.startswith("0x") and len(address) == 42):
        raise ValueError("address must be a 0x-prefixed 20-byte hex address")
    checked_at = int(time.time())

    d = _bcv._fetch(address)
    if d is None:
        return _onyx_sign.attest({
            "ok": True, "address": address.lower(), "checked_at": checked_at,
            "verified": False, "verdict": "BLOCK", "risk_score": 90, "ai_deep_pass": False,
            "findings": [{
                "title": "Contract source is UNVERIFIED", "severity": "high",
                "category": "transparency", "source": "onchain",
                "detail": "No verified source on Blockscout — the code cannot be audited. Treat as high risk.",
            }],
            "summary": "BLOCK: unverified contract — no source to audit.",
        }, tool=NAME)

    name = d.get("name") or "Unknown"
    src = d.get("source_code") or ""
    verified = bool(d.get("is_verified"))
    proxy = d.get("proxy_type")
    self_destructed = d.get("is_self_destructed")

    findings: list = []

    # --- static detectors (the part AgentLISA does) ---
    for det in _DETECTORS:
        if det.rx.search(src):
            findings.append({
                "title": det.title, "severity": det.severity,
                "category": det.category, "detail": det.why, "source": "static",
            })

    # --- DEPLOYED-REALITY flags (the x10 — what a static audit structurally misses) ---
    if proxy:
        findings.append({
            "title": "Upgradeable proxy — logic can change AFTER any audit",
            "severity": "high", "category": "upgradeability", "source": "onchain",
            "detail": f"proxy_type={proxy}. The owner can swap the implementation contract at any time; "
                      "a clean source audit does NOT bind future behavior. This is the #1 blind spot of source-only audits.",
        })
    if self_destructed:
        findings.append({
            "title": "Contract is SELF-DESTRUCTED on-chain",
            "severity": "critical", "category": "liveness", "source": "onchain",
            "detail": "This contract has been destroyed. Funds sent to it are unrecoverable. Do not interact.",
        })

    # --- optional AI deep-pass ---
    ai_used = False
    if deep and verified and src:
        ai = _llm_audit(src, name)
        if ai is not None:
            ai_used = True
            for f in ai:
                if isinstance(f, dict):
                    f["source"] = "ai"
                    findings.append(f)

    # --- score + verdict ---
    risk = min(99, sum(_SEV.get((f.get("severity") or "").lower(), 4) for f in findings))
    if not verified:
        risk = max(risk, 80)
    sev_counts = {s: sum(1 for f in findings if (f.get("severity") or "").lower() == s)
                  for s in ("critical", "high", "medium", "low")}
    verdict = "ALLOW" if risk < 25 else ("REVIEW" if risk < 60 else "BLOCK")
    # Severity floors — the "most secure" stance: a critical never passes, a high never auto-allows.
    if sev_counts["critical"] > 0:
        verdict, risk = "BLOCK", max(risk, 60)
    elif sev_counts["high"] > 0 and verdict == "ALLOW":
        verdict, risk = "REVIEW", max(risk, 25)

    return _onyx_sign.attest({
        "ok": True,
        "address": address.lower(),
        "name": name,
        "checked_at": checked_at,
        "checked_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(checked_at)),
        "network": "base",
        "verified": verified,
        "is_proxy": bool(proxy),
        "proxy_type": proxy,
        "self_destructed": bool(self_destructed),
        "compiler": d.get("compiler_version"),
        "source_size_bytes": len(src),
        "ai_deep_pass": ai_used,
        "static_detectors_run": len(_DETECTORS),
        "finding_count": len(findings),
        "severity_breakdown": sev_counts,
        "risk_score": risk,
        "verdict": verdict,
        "findings": findings or [{
            "title": "No high-signal issues detected", "severity": "low",
            "category": "clean", "source": "static",
            "detail": "Static detectors + on-chain checks found no elevated-risk patterns. Not a guarantee of safety.",
        }],
        "summary": (
            f"{verdict} (risk {risk}/100): {len(findings)} finding(s) — "
            f"{sev_counts['critical']} critical, {sev_counts['high']} high, "
            f"{sev_counts['medium']} medium. "
            + ("AI deep-pass ON. " if ai_used else "static + on-chain only. ")
            + ("UPGRADEABLE PROXY — audit doesn't bind future logic. " if proxy else "")
        ),
    }, tool=NAME)


run.__when_to_use__ = (
    "Before an agent (or its user) interacts with, swaps against, approves, or "
    "deploys capital into ANY Base contract. Use the verdict as a gate: BLOCK = "
    "abort, REVIEW = require human sign-off, ALLOW = proceed. Especially before "
    "trusting a third-party 'audited' contract — this catches the upgradeable-"
    "proxy and self-destruct realities a source-only audit certificate ignores."
)
run.__vs_alternatives__ = (
    "Source-only AI auditors (e.g. AgentLISA) analyze the code in isolation and "
    "miss that the DEPLOYED contract is an owner-upgradeable proxy or already "
    "self-destructed — the exact gaps that rug users after a clean audit. This "
    "fuses verified source + static detectors + an optional AI pass WITH live "
    "on-chain reality, returns a single ALLOW/REVIEW/BLOCK verdict, and "
    "Ed25519-signs it so the audit is provable, not a hallucinatable claim."
)
run.__example_request__ = {"address": "0x4200000000000000000000000000000000000006"}
run.__example_response__ = {
    "ok": True,
    "verdict": "REVIEW",
    "risk_score": 40,
    "is_proxy": True,
    "ai_deep_pass": True,
    "severity_breakdown": {"critical": 0, "high": 1, "medium": 1, "low": 2},
    "summary": "REVIEW (risk 40/100): 4 finding(s) — 0 critical, 1 high, 1 medium. AI deep-pass ON. UPGRADEABLE PROXY — audit doesn't bind future logic.",
}
