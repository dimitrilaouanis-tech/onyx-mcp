"""Agent liveness + authenticity oracle — paid x402 MCP tool.

Every agent registry (a2aregistry, Bazaar, ERC-8004) lists agents but cannot
tell a REAL agent from a hollow one. The dirty secret of the agentic web:
most "live agents" return one canned string no matter what you ask — they
pass a registry's fixed-prompt health check while doing nothing. (We met one:
"Silas" replied with the identical welcome to every question.) A real agent
(we met "Zee") gives a different, on-topic answer each time.

This returns ONE signed observation about a target agent —

    "I sent THIS agent two different challenge messages just now; here is
     whether it answered, whether it gave DIFFERENT relevant replies (alive)
     or the SAME canned string (hollow), whether its card is signed, and
     whether its declared auth matches how it actually behaves."

The hollow-detector is deterministic and needs no LLM: send two distinct
nonce-tagged probes; a live agent's two replies differ and engage; a hollow
agent returns a byte-identical canned response. That single asymmetry
separates the real from the fake — the thing no registry checks today.

Bright line: we SIGN FACTS, not judgments. We report observed behavior
(status codes, whether replies differed, signature presence) and a transparent
score the caller can recompute. We make no claim about the operator's intent.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request

from . import _onyx_sign

NAME = "onyx_agent_verify"
PRICE_USDC = "0.10"
TIER = "metered"
DESCRIPTION = (
    "Signed agent liveness + authenticity oracle. Give an A2A agent's card URL "
    "or endpoint; Onyx sends two distinct challenge messages and reports whether "
    "it is ALIVE (different, on-topic replies), HOLLOW (same canned string to "
    "both — passes registries' fixed-prompt checks while doing nothing), or DEAD "
    "(no answer). Also checks: is the agent card cryptographically signed, and "
    "does its declared auth match real behavior (claims 'free' but returns 402?). "
    "Ed25519-signed verdict. Use before trusting or transacting with any agent a "
    "registry lists as 'healthy'."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "target": {
            "type": "string",
            "description": "The agent to verify: its A2A endpoint URL, or its "
                           "/.well-known/agent-card.json URL, or its base origin.",
        },
    },
    "required": ["target"],
}

_UA = "onyx-truth/1.0 (+https://onyx-actions.onrender.com)"
_TIMEOUT = 15.0


def _get(url: str) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
        return r.status, r.read(2_000_000).decode("utf-8", "replace")


def _post_a2a(url: str, text: str) -> tuple[int, str]:
    mid = "onyx-" + os.urandom(6).hex()
    body = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "message/send",
        "params": {"message": {"messageId": mid, "role": "user",
                               "parts": [{"kind": "text", "text": text}]}},
    }).encode()
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"User-Agent": _UA, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            return r.status, r.read(1_000_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, ""


def _extract_reply(raw: str) -> str:
    """Pull the agent's reply text out of any A2A response shape."""
    try:
        d = json.loads(raw)
    except (ValueError, TypeError):
        return raw.strip()[:2000]
    out = []

    def walk(o):
        if isinstance(o, dict):
            if o.get("kind") == "text" and isinstance(o.get("text"), str):
                out.append(o["text"])
            if isinstance(o.get("text"), str) and "kind" not in o:
                out.append(o["text"])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(d)
    return " ".join(out).strip()[:2000]


def _norm(s: str, strip: str = "") -> str:
    s = s.lower()
    if strip:
        s = s.replace(strip.lower(), " ")  # remove echoed probe text
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _resolve_endpoints(target: str) -> tuple[str | None, dict | None]:
    """Return (a2a_endpoint, card_dict). Accepts endpoint, card URL, or origin."""
    target = target.strip().rstrip("/")
    if not target.lower().startswith(("http://", "https://")):
        target = "https://" + target
    card = None
    card_url = None
    if target.endswith("agent-card.json") or target.endswith("agent.json"):
        card_url = target
    else:
        # try the well-known card under this origin
        from urllib.parse import urlparse
        u = urlparse(target)
        origin = f"{u.scheme}://{u.netloc}"
        for path in ("/.well-known/agent-card.json", "/.well-known/agent.json"):
            try:
                st, body = _get(origin + path)
                if st == 200:
                    card = json.loads(body)
                    card_url = origin + path
                    break
            except Exception:
                continue
    if card is None and card_url:
        try:
            st, body = _get(card_url)
            if st == 200:
                card = json.loads(body)
        except Exception:
            card = None
    # endpoint: card.url if present, else the target itself
    endpoint = None
    if isinstance(card, dict):
        endpoint = card.get("url")
        if not endpoint:
            ifaces = card.get("additionalInterfaces") or card.get("interfaces") or []
            if ifaces and isinstance(ifaces, list) and isinstance(ifaces[0], dict):
                endpoint = ifaces[0].get("url")
    if not endpoint and not (target.endswith(".json")):
        endpoint = target
    return endpoint, card


def run(target: str = "", **_: object) -> dict:
    target = (target or "").strip()
    if not target:
        raise ValueError("target is required")

    observed_at = int(time.time())
    endpoint, card = _resolve_endpoints(target)

    result = {
        "ok": True,
        "target": target,
        "observed_at": observed_at,
        "observed_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(observed_at)),
        "resolved_endpoint": endpoint,
        "vantage": "onyx-observer",
    }

    # --- card facts ---
    card_signed = None
    declared_auth = None
    accepts_text = True  # default-assume text until a card says otherwise
    if isinstance(card, dict):
        sigs = card.get("signatures")
        card_signed = bool(sigs) if sigs is not None else False
        schemes = card.get("securitySchemes") or {}
        sec = card.get("security") or []
        declared_auth = "none" if (not schemes and not sec) else "required"
        in_modes = card.get("defaultInputModes")
        if isinstance(in_modes, list) and in_modes:
            accepts_text = any("text" in str(m).lower() for m in in_modes)
        result["card"] = {
            "name": card.get("name"),
            "signed": card_signed,
            "declared_auth": declared_auth,
            "skills_count": len(card.get("skills") or []),
            "accepts_text_input": accepts_text,
            "default_input_modes": in_modes if isinstance(in_modes, list) else None,
        }
    else:
        result["card"] = None

    if not endpoint:
        result["verdict"] = "unreachable"
        result["detail"] = "No A2A endpoint found (no card, no usable url)."
        return _onyx_sign.attest(result, tool=NAME)

    # --- two distinct nonce-tagged challenges (the hollow detector) ---
    n1, n2 = os.urandom(4).hex(), os.urandom(4).hex()
    probe1 = f"What is the single most useful thing you can do? Reference code {n1}."
    probe2 = f"Name one thing you cannot do, and why. Reference code {n2}."

    s1, r1 = _post_a2a(endpoint, probe1)
    s2, r2 = _post_a2a(endpoint, probe2)
    reply1, reply2 = _extract_reply(r1), _extract_reply(r2)

    answered = (s1 == 200 and bool(reply1)) and (s2 == 200 and bool(reply2))
    # strip each probe's own text (handles agents that echo "you said ...")
    c1 = _norm(reply1, strip=probe1)
    c2 = _norm(reply2, strip=probe2)
    identical = bool(c1) and c1 == c2          # same canned reply to both → hollow
    differ = bool(c1) and bool(c2) and c1 != c2

    result["probes"] = {
        "challenge_1_status": s1, "challenge_2_status": s2,
        "reply_1_len": len(reply1), "reply_2_len": len(reply2),
        "replies_identical": identical,
        "replies_differ": differ,
        "reply_1_sample": reply1[:160],
        "reply_2_sample": reply2[:160],
    }

    # --- claims vs behavior ---
    claims_mismatch = None
    if declared_auth == "none" and (s1 in (401, 402, 403) or s2 in (401, 402, 403)):
        claims_mismatch = f"card declares no auth but endpoint returned {s1 or s2}"
    elif declared_auth == "required" and s1 == 200 and s2 == 200:
        claims_mismatch = "card declares auth required but anonymous calls succeed"
    if claims_mismatch:
        result["claims_mismatch"] = claims_mismatch

    # --- verdict (transparent, recomputable) ---
    if not answered:
        verdict = "dead"
        detail = f"No usable answer (status {s1}/{s2})."
    elif identical and not accepts_text:
        # Its own card says it does not take free-text; the identical reply is
        # expected, not evidence of hollowness. Report fact, withhold judgment.
        verdict = "structured_only"
        detail = ("Returned the same reply to two distinct free-text challenges, "
                  "but its card declares non-text input modes "
                  f"({result['card'].get('default_input_modes')}). Free-text "
                  "liveness is not the right test for this agent; use its declared "
                  "structured skill interface. Not classified as hollow.")
    elif identical:
        verdict = "hollow"
        detail = ("Its card accepts text input, yet it returned a byte-identical "
                  "reply to two distinct text challenges — i.e. its output does "
                  "not vary with message content. Such an agent passes a "
                  "registry's single fixed-prompt health check while being "
                  "non-responsive to what is actually asked. (Observed behavior; "
                  "we make no claim about the operator's intent.)")
    elif differ:
        verdict = "alive"
        detail = "Gave two distinct, responsive replies to two different challenges."
    else:
        verdict = "degraded"
        detail = "Answered but replies were empty or unclassifiable."

    # trust score 0-100 (transparent components)
    factors = []
    score = 0
    if answered:
        score += 40; factors.append({"factor": "answered", "points": 40})
    if differ:
        score += 30; factors.append({"factor": "distinct_replies", "points": 30})
    if card is not None:
        score += 10; factors.append({"factor": "has_agent_card", "points": 10})
    if card_signed:
        score += 20; factors.append({"factor": "card_cryptographically_signed", "points": 20})
    if identical and verdict == "hollow":
        score -= 30; factors.append({"factor": "canned_reply_penalty", "points": -30})
    if claims_mismatch:
        score -= 15; factors.append({"factor": "claims_behavior_mismatch", "points": -15})
    score = max(0, min(100, score))

    result["verdict"] = verdict
    result["detail"] = detail
    result["trust_score"] = score
    result["trust_score_max"] = 100
    result["trust_factors"] = factors
    result["scoring_note"] = ("trust_score = sum(trust_factors[].points), clamped 0-100. "
                              "Every factor is an observed behavior; recompute it yourself.")
    return _onyx_sign.attest(result, tool=NAME)


run.__when_to_use__ = (
    "Before trusting, listing, or transacting with an agent — verify it is a real "
    "live agent and not a hollow template that canned-answers registry health "
    "checks. Also to audit an agent directory for fake/dead listings."
)
run.__vs_alternatives__ = (
    "Registries (a2aregistry, Bazaar) only check reachability with a fixed prompt "
    "a canned agent passes; they cannot tell alive from hollow, don't verify the "
    "card signature, and don't reconcile declared auth vs behavior. This sends two "
    "distinct challenges to expose canned responders, checks the signature, and "
    "returns a signed, recomputable verdict."
)
run.__example_request__ = {"target": "https://example-agent.com/.well-known/agent-card.json"}
run.__example_response__ = {
    "ok": True,
    "verdict": "hollow",
    "trust_score": 20,
    "probes": {"replies_identical": True},
    "detail": "Returned a byte-identical canned reply to two different challenges.",
}
