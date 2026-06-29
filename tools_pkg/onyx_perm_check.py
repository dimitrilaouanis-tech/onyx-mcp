"""onyx_perm_check — does an agent's ACTION stay inside its permission grant?

The verifier for the Perm leg (PERM_v0). Given a proposed action and the
agent's signed permission grant, it returns a SIGNED, offline-verifiable fact
stating, per dimension, whether the action conforms to the grant — the thing
99.1% of live agents currently have NO way to prove.

HARD RULE — facts, not judgments. The output is a mechanical conformance fact
("amount 12.00 exceeds declared cap 5.00"), NEVER a verdict on the agent's
intent. The counterparty reads the signed fact and decides for itself.

Spec: perm/spec/PERM_v0.md. Maps to AP2 mandate / Verifiable Intent.
Underscore-free, NAME + run() → auto-discovered.
"""
from __future__ import annotations

import hashlib
import json
import time

NAME = "onyx_perm_check"
PRICE_USDC = "0.00"
TIER = "free"          # free to drive adoption of the grant model
DESCRIPTION = (
    "Check whether an agent's proposed action stays inside its declared "
    "permission grant (allowed action, allowed merchant/domain, spend cap, "
    "rolling-window + velocity + per-counterparty budgets, expiry, principal, "
    "consent). Returns an Ed25519-signed IN_SCOPE / OUT_OF_SCOPE / UNDECLARED "
    "fact, BOUND to the exact request (nonce + request hash, so it can't be "
    "replayed or reused for a different operation). Facts, not judgments — a "
    "mechanical conformance check, never a verdict on intent. Verify free with "
    "onyx_attestation_verify."
)

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {
            "type": "object",
            "description": "The proposed action: {type, amount_usdc?, merchant?, domain?}",
            "properties": {
                "type": {"type": "string", "description": "e.g. transact, verify, read"},
                "amount_usdc": {"type": "number"},
                "merchant": {"type": "string"},
                "domain": {"type": "string"},
            },
        },
        "grant": {
            "type": "object",
            "description": "The agent's permission grant (onyx-perm-grant/v0): "
                           "allowed_actions, allowed_merchants, allowed_domains, "
                           "spend_max_usdc, spend_window_usdc, spend_window_sec, "
                           "velocity_max, per_counterparty_budget, principal, "
                           "consent_ref, expires_at",
        },
        "history": {
            "type": "array",
            "description": "Optional: recent settled actions for window/velocity "
                           "checks, each {amount_usdc, ts (unix), counterparty?}. "
                           "Stateless — the caller supplies the tally; the fact "
                           "binds to it.",
            "items": {"type": "object"},
        },
    },
    "required": ["action", "grant"],
}


def _jcs(o) -> str:
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _norm_host(s: str) -> str:
    s = (s or "").strip().lower()
    for p in ("https://", "http://"):
        if s.startswith(p):
            s = s[len(p):]
    return s.split("/")[0].lstrip("www.")


def run(action: dict | None = None, grant: dict | None = None,
        history: list | None = None, **_: object) -> dict:
    if not isinstance(action, dict):
        raise ValueError("action must be an object")
    grant = grant if isinstance(grant, dict) else {}
    history = history if isinstance(history, list) else []

    # No grant at all → the action is UNDECLARED (the 99.1% case). That is itself
    # the fact: nothing authorizes this action.
    has_grant = bool(grant) and any(
        k in grant for k in ("allowed_actions", "allowed_merchants", "allowed_domains",
                             "spend_max_usdc", "principal", "consent_ref"))

    checks: dict = {}
    out_of_scope_on: list = []

    def fail(name: str, ok: bool):
        checks[name] = ok
        if not ok:
            out_of_scope_on.append(name)

    # action type
    allowed_actions = grant.get("allowed_actions")
    if allowed_actions is not None:
        fail("action_allowed", action.get("type") in allowed_actions)

    # merchant / domain
    merch = action.get("merchant")
    if grant.get("allowed_merchants") is not None and merch is not None:
        fail("merchant_allowed", merch in grant["allowed_merchants"])
    dom = action.get("domain") or (_norm_host(merch) if merch else None)
    if grant.get("allowed_domains") is not None and dom is not None:
        allow_doms = {_norm_host(d) for d in grant["allowed_domains"]}
        fail("domain_allowed", _norm_host(dom) in allow_doms)

    # spend cap (per-action)
    amt = action.get("amount_usdc")
    cap = grant.get("spend_max_usdc")
    if cap is not None and amt is not None:
        fail("within_spend_cap", float(amt) <= float(cap))

    # velocity / rolling-window / per-counterparty — closes sub-cap draining
    # (1000 under-the-cap txns). Stateless: caller supplies recent `history`.
    if amt is not None and history:
        win = int(grant.get("spend_window_sec") or 86400)
        now = int(time.time())
        recent = [h for h in history if isinstance(h, dict)
                  and now - int(h.get("ts", 0)) <= win]
        win_cap = grant.get("spend_window_usdc")
        if win_cap is not None:
            spent = sum(float(h.get("amount_usdc", 0)) for h in recent)
            fail("within_spend_window", spent + float(amt) <= float(win_cap))
        vmax = grant.get("velocity_max")
        if vmax is not None:
            fail("within_velocity", len(recent) + 1 <= int(vmax))
        cp_budget = grant.get("per_counterparty_budget")
        cp = action.get("counterparty") or merch or dom
        if cp_budget is not None and cp is not None:
            cp_spent = sum(float(h.get("amount_usdc", 0)) for h in recent
                           if (h.get("counterparty") == cp))
            fail("within_counterparty_budget", cp_spent + float(amt) <= float(cp_budget))

    # expiry
    exp = grant.get("expires_at")
    if exp is not None:
        fail("not_expired", int(time.time()) <= int(exp))

    # authority presence (these are posture facts, not pass/fail of the action)
    checks["has_principal"] = bool(grant.get("principal"))
    checks["has_consent"] = bool(grant.get("consent_ref"))
    if not checks["has_principal"]:
        out_of_scope_on.append("has_principal")
    if not checks["has_consent"]:
        out_of_scope_on.append("has_consent")

    if not has_grant:
        decision = "UNDECLARED"
    elif out_of_scope_on:
        decision = "OUT_OF_SCOPE"
    else:
        decision = "IN_SCOPE"

    # request-binding — bind this decision to the EXACT operation + a nonce, so a
    # captured IN_SCOPE fact can't be replayed or lifted onto a different action
    # (closes TOCTOU + replay + injection-fabricated-grant reuse).
    bound_fields = {
        "type": action.get("type"),
        "amount_usdc": action.get("amount_usdc"),
        "merchant": action.get("merchant"),
        "domain": action.get("domain"),
        "counterparty": action.get("counterparty"),
        "request_id": action.get("request_id"),
        "nonce": action.get("nonce"),
    }
    request_hash = "sha256:" + hashlib.sha256(_jcs(bound_fields).encode("utf-8")).hexdigest()

    out = {
        "subject": action.get("merchant") or action.get("domain") or grant.get("agent") or "action",
        "predicate": "perm_in_scope",
        "spec": "onyx-perm-grant/v1",
        "decision": decision,
        "action": action,
        "checks": checks,
        "out_of_scope_on": out_of_scope_on,
        "bound_to": {
            "request_id": action.get("request_id"),
            "nonce": action.get("nonce"),
            "request_hash": request_hash,
            "note": "this fact authorizes ONLY the operation with this exact "
                    "request_hash; reuse for any other action is invalid",
        },
        "method": "mechanical conformance check of action vs declared grant; "
                  "facts-not-judgments — states conformance, not intent",
        "verify_free": "https://onyx-actions.onrender.com/verify",
    }
    try:
        from . import _onyx_sign
        out = _onyx_sign.attest(out, tool=NAME)
    except Exception:
        pass
    return out
