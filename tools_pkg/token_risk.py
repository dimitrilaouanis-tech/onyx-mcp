"""Token security ground-truth oracle — paid x402 MCP tool.

Before an autonomous agent buys an ERC-20, it needs to know one thing the
seller will never tell it: is this contract a trap? Honeypot, confiscatory
sell-tax, a mint function that dilutes you to zero, an owner who can pause
your transfers or claw back ownership. Agents that skip this lose the whole
position — and an agent that DID screen needs to PROVE it screened, at the
price/time it acted, if the trade is ever questioned.

This returns ONE signed observation —

    "the on-chain security facts for THIS token on THIS chain, as actually
     read from the GoPlus security oracle right now, plus a transparent
     risk tally the caller can recompute from the same facts."

Bright line: we SIGN FACTS, not judgments. Every flag is an observed
on-chain property (is_honeypot, sell_tax, is_mintable, lp_locked…). The
risk_score is a deterministic, fully-itemized sum of those facts — the
caller gets the raw factors and can re-derive the number. We make no
subjective claim and no claim about persons or personhood.

Source: GoPlus Token Security API (gopluslabs.io) — free, no key. We
observe, structure, timestamp, and Ed25519-sign it so the result is
tamper-evident and citable in a dispute. The signature is the product.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from . import _onyx_sign

NAME = "onyx_token_risk"
PRICE_USDC = "0.10"
TIER = "metered"
DESCRIPTION = (
    "Signed token-security oracle. Give a token contract (and chain); get the "
    "real on-chain risk facts as read right now — honeypot status, buy/sell "
    "tax, mintable, ownership-reclaim, transfer-pausable, proxy, LP-lock, "
    "holder count — plus a transparent 0-100 risk score and verdict you can "
    "recompute from the itemized factors. Ed25519-signed + timestamped so an "
    "agent can PROVE it screened a token before buying. Use before any "
    "agent swaps into or quotes an ERC-20 it didn't issue."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "contract": {
            "type": "string",
            "description": "Token contract address (0x… 20-byte hex) to screen.",
        },
        "chain": {
            "type": "string",
            "description": (
                "Chain the token lives on. Name ('base','ethereum','bsc',"
                "'polygon','arbitrum','optimism','avalanche') or numeric chain "
                "id. Default 'base'."
            ),
            "default": "base",
        },
    },
    "required": ["contract"],
}

_UA = "onyx-truth/1.0 (+https://onyx-actions.onrender.com)"
_TIMEOUT = 18.0

# GoPlus supported chains: name -> chain id
_CHAINS = {
    "ethereum": "1", "eth": "1", "1": "1",
    "bsc": "56", "bnb": "56", "56": "56",
    "polygon": "137", "matic": "137", "137": "137",
    "base": "8453", "8453": "8453",
    "arbitrum": "42161", "arb": "42161", "42161": "42161",
    "optimism": "10", "op": "10", "10": "10",
    "avalanche": "43114", "avax": "43114", "43114": "43114",
    "zksync": "324", "324": "324",
    "linea": "59144", "59144": "59144",
}

# Each tuple: (goplus_field, "1" means-dangerous?, weight, human label)
# We score only on clearly-observed dangerous on-chain properties.
_RISK_RULES = [
    ("is_honeypot", "1", 60, "honeypot — sells are blocked or fail"),
    ("cannot_sell_all", "1", 30, "cannot sell entire balance"),
    ("transfer_pausable", "1", 20, "owner can pause all transfers"),
    ("is_mintable", "1", 18, "supply is mintable (dilution risk)"),
    ("can_take_back_ownership", "1", 18, "ownership can be reclaimed"),
    ("hidden_owner", "1", 18, "hidden owner present"),
    ("selfdestruct", "1", 25, "contract can self-destruct"),
    ("owner_change_balance", "1", 25, "owner can change balances"),
    ("is_blacklisted", "1", 12, "blacklist function present"),
    ("is_whitelisted", "1", 6, "whitelist function present"),
    ("trading_cooldown", "1", 8, "trading cooldown enforced"),
    ("is_anti_whale", "1", 4, "anti-whale max-tx limit"),
    ("external_call", "1", 6, "external call risk in transfer"),
    ("gas_abuse", "1", 10, "gas-abuse (token drains gas)"),
]


def _resolve_chain(chain: str) -> str:
    key = (chain or "base").strip().lower()
    if key not in _CHAINS:
        raise ValueError(
            f"unsupported chain '{chain}'. Supported: "
            + ", ".join(sorted({k for k in _CHAINS if not k.isdigit()}))
        )
    return _CHAINS[key]


def _fetch(chain_id: str, contract: str) -> dict:
    url = (
        f"https://api.gopluslabs.io/api/v1/token_security/{chain_id}"
        f"?contract_addresses={contract}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read())


def _pct(v: object) -> float | None:
    """GoPlus tax fields are decimal strings like '0.05' (=5%)."""
    if v is None or v == "":
        return None
    try:
        return round(float(v) * 100, 2)
    except (TypeError, ValueError):
        return None


def _flag(v: object) -> str | None:
    """Normalise GoPlus '0'/'1'/'' tri-state to bool-ish, keep None if absent."""
    if v in ("1", 1):
        return "1"
    if v in ("0", 0):
        return "0"
    return None


def run(contract: str = "", chain: str = "base", **_: object) -> dict:
    contract = (contract or "").strip()
    if not contract:
        raise ValueError("contract is required")
    if not (contract.lower().startswith("0x") and len(contract) == 42):
        raise ValueError("contract must be a 0x-prefixed 20-byte hex address")

    chain_id = _resolve_chain(chain)
    observed_at = int(time.time())

    try:
        body = _fetch(chain_id, contract)
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": "goplus_http_error", "http_status": e.code,
                "contract": contract, "chain_id": chain_id, "observed_at": observed_at}
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        return {"ok": False, "error": "fetch_failed", "detail": str(e)[:200],
                "contract": contract, "chain_id": chain_id, "observed_at": observed_at}

    if str(body.get("code")) != "1":
        return {"ok": False, "error": "goplus_error", "detail": str(body.get("message"))[:200],
                "contract": contract, "chain_id": chain_id, "observed_at": observed_at}

    result_map = body.get("result") or {}
    info = result_map.get(contract.lower()) or (next(iter(result_map.values()), None))
    if not info:
        # Address not found / not a recognised token on this chain — say so, don't guess.
        return _onyx_sign.attest({
            "ok": True, "contract": contract, "chain_id": chain_id, "observed_at": observed_at,
            "found": False, "confidence": "none",
            "note": "GoPlus has no security record for this contract on this chain. "
                    "It may not be a token, may be unverified, or wrong chain. We return "
                    "found=False rather than guess.",
            "vantage": "onyx-observer",
        }, tool=NAME)

    # ---- structured observed facts ----
    facts = {
        "token_name": info.get("token_name") or None,
        "token_symbol": info.get("token_symbol") or None,
        "is_open_source": _flag(info.get("is_open_source")),
        "is_proxy": _flag(info.get("is_proxy")),
        "is_honeypot": _flag(info.get("is_honeypot")),
        "buy_tax_pct": _pct(info.get("buy_tax")),
        "sell_tax_pct": _pct(info.get("sell_tax")),
        "is_mintable": _flag(info.get("is_mintable")),
        "can_take_back_ownership": _flag(info.get("can_take_back_ownership")),
        "owner_change_balance": _flag(info.get("owner_change_balance")),
        "hidden_owner": _flag(info.get("hidden_owner")),
        "selfdestruct": _flag(info.get("selfdestruct")),
        "transfer_pausable": _flag(info.get("transfer_pausable")),
        "is_blacklisted": _flag(info.get("is_blacklisted")),
        "trading_cooldown": _flag(info.get("trading_cooldown")),
        "is_in_dex": _flag(info.get("is_in_dex")),
        "holder_count": _int(info.get("holder_count")),
        "lp_holder_count": _int(info.get("lp_holder_count")),
        "owner_address": info.get("owner_address") or None,
        "creator_address": info.get("creator_address") or None,
    }

    # ---- transparent, recomputable risk tally (facts in -> score out) ----
    risk_factors = []
    score = 0
    for field, danger_val, weight, label in _RISK_RULES:
        if _flag(info.get(field)) == danger_val:
            score += weight
            risk_factors.append({"factor": field, "weight": weight, "detail": label})

    # taxes are graded numerically (observed, not a judgment)
    for side in ("buy", "sell"):
        tax = _pct(info.get(f"{side}_tax"))
        if tax is not None and tax >= 10:
            w = min(30, int(tax))  # 1 pt per % up to 30
            score += w
            risk_factors.append({"factor": f"{side}_tax",
                                 "weight": w, "detail": f"{side} tax {tax}%"})

    # unverified source is a real, observed risk signal
    if facts["is_open_source"] == "0":
        score += 15
        risk_factors.append({"factor": "is_open_source",
                             "weight": 15, "detail": "contract source NOT verified"})

    score = min(100, score)
    verdict = (
        "critical" if score >= 60 else
        "high_risk" if score >= 30 else
        "caution" if score >= 12 else
        "safe"
    )

    result = {
        "ok": True,
        "found": True,
        "contract": contract,
        "chain_id": chain_id,
        "observed_at": observed_at,
        "observed_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(observed_at)),
        "facts": facts,
        "risk_score": score,
        "risk_score_max": 100,
        "verdict": verdict,
        "risk_factors": sorted(risk_factors, key=lambda x: -x["weight"]),
        "scoring_note": "risk_score = sum(risk_factors[].weight), capped at 100. "
                        "Every factor is an observed on-chain property; recompute it yourself.",
        "source": "gopluslabs.io token_security",
        "vantage": "onyx-observer",
    }
    return _onyx_sign.attest(result, tool=NAME)


def _int(v: object) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


run.__when_to_use__ = (
    "Before an agent swaps into, quotes, or recommends an ERC-20 it did not "
    "issue — screen for honeypot, confiscatory tax, mint/ownership traps. Also "
    "to produce a signed, timestamped record proving the token was screened at "
    "decision time, citable if the trade is later disputed."
)
run.__vs_alternatives__ = (
    "Raw GoPlus/Etherscan calls return unsigned JSON the agent must trust and "
    "can't later prove it saw. Generic 'is this a scam' tools return an opaque "
    "rating. This returns itemized observed facts + a transparent recomputable "
    "score, Ed25519-signed and timestamped — tamper-evident and dispute-grade."
)
run.__example_request__ = {"contract": "0x4200000000000000000000000000000000000006", "chain": "base"}
run.__example_response__ = {
    "ok": True,
    "found": True,
    "verdict": "safe",
    "risk_score": 0,
    "facts": {"token_symbol": "WETH", "is_honeypot": "0", "sell_tax_pct": 0.0, "is_open_source": "1"},
    "risk_factors": [],
}
