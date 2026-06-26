"""Onyx Fact Index — the public, aggregate, signed precision record.

Surface 3b of FACT_LAYER_SPEC: a published, dated record of how many real-world
facts/verdicts Onyx has signed and how often they held up (precision), built
directly on the existing outcome ledger (`_ledger.stats()`) — NO parallel data
source. Distinct from `/verified/{host}` (per-merchant badge in `_verified.py`);
this is the ecosystem-wide aggregate.

Honest by design: it publishes the real count, including when the count is small.
The record only becomes an asset as real signed facts accrue — that is the point,
and the page says so plainly rather than seeding a vanity number.

Underscore-prefixed → NOT auto-discovered as a paid tool. Wired by server_http.py:
    from tools_pkg import _fact_index; _fact_index.register(app)
"""
from __future__ import annotations

import time

from . import _ledger

# Fact classes the layer signs (mapped from the tools that emit them).
_FACT_TOOLS = {
    "onyx_merchant_fact_check": "merchant",
    "onyx_retail_price_check": "price",
    "onyx_geo_verify": "geo",
    "onyx_review_truth": "reputation",
    "onyx_payment_gate": "clear_to_pay",
    "onyx_tx_guard": "tx_safety",
    "onyx_approval_guard": "approval_safety",
    "onyx_token_risk": "token_risk",
    "onyx_contract_audit": "contract_safety",
}

_METHODOLOGY = {
    "merchant": "domain age (RDAP) + live TLS age + off-domain redirect + brand-similarity + price deviation",
    "price": "page extraction with source disclosed; independent retailer compare on re-check",
    "geo": "multi-vantage fetch; repeat from 2nd vantage on re-check",
    "reputation": "live web sentiment + recurring pros/cons with sources cited",
    "clear_to_pay": "PROCEED/REVIEW/HOLD bundling merchant + price facts, signed evidence",
    "tx_safety": "on-chain transaction simulation + heuristics vs ground-truth outcome",
    "token_risk": "token contract + liquidity + holder heuristics vs realized outcome",
    "contract_safety": "bytecode/source audit heuristics vs realized outcome",
}


def build_index() -> dict:
    """Compute the public fact-index payload from the live outcome ledger."""
    s = _ledger.stats()
    rows = _ledger._entries()

    by_class: dict[str, int] = {}
    onchain = 0
    for r in rows:
        cls = _FACT_TOOLS.get(r.get("tool"), "other")
        by_class[cls] = by_class.get(cls, 0) + 1
        if r.get("tx_hash"):
            onchain += 1

    total = s.get("total_outcomes", 0)
    resolved = s.get("resolved", 0)
    precision = s.get("block_precision")  # of BLOCK verdicts, fraction that were real

    return {
        "name": "Onyx Fact Index",
        "issuer": "Onyx",
        "spec": "onyx-fact-layer/v0 (surface 3b)",
        "what": (
            "A public, append-only, signed record of real-world facts/verdicts Onyx has "
            "signed and how often they held up on independent re-check. Each entry is "
            "Ed25519-signed (JCS-canonical); verify any one at /verify."
        ),
        "neutrality": (
            "Onyx signs observable FACTS with the method disclosed per field — never "
            "judgments, never its own GMV, never a badge money can buy. The conflicted "
            "incumbents (card networks, agent-scorers) structurally cannot occupy this seat."
        ),
        "as_of": int(time.time()),
        "record": {
            "signed_records_total": total,
            "resolved_outcomes": resolved,
            "block_precision": precision,
            "precision_note": (
                None if (resolved and resolved >= 20)
                else "insufficient n to publish a stable precision rate yet — the record "
                     "becomes an asset as real signed facts accrue (see on-chain below)."
            ),
            "value_intercepted_usdc": s.get("value_intercepted"),
            "value_intercepted_usdc_live": s.get("value_intercepted_live"),
            "by_fact_class": by_class,
            "by_tool": s.get("by_tool", {}),
            "onchain_attestations": onchain,
            "last_signed_at": s.get("last", 0),
        },
        "methodology": _METHODOLOGY,
        "verify": {
            "how": [
                "Take an entry's payload (everything minus its signature).",
                "JCS-canonicalize, verify the Ed25519 signature against the key at /verify.",
                "If tx_hash present, check feedbackHash == keccak256(JCS payload) on the "
                "ERC-8004 Reputation Registry 0x8004BAa17C55a88189AE136b182e5fdA19dE9b63 (Base 8453).",
                "Re-run the disclosed method yourself and compare — the signature proves the "
                "observation is ours and untampered; your re-check proves whether it is true.",
            ],
            "verify_endpoint": "/verify",
            "per_merchant_badge": "/verified/{domain}",
        },
        "why_this_wins": (
            "Every rival either scores the agent (taken, conflicted, mostly dormant) or "
            "profits from the GMV it would grade. Onyx is the only neutral party publishing "
            "a signed, re-checkable record of merchant/price/real-world facts — the seat "
            "Visa's own TAP spec disclaims and the 2026 fake-storefront scandal proved empty."
        ),
    }


def register(app) -> None:
    """Attach GET /fact-index to the FastAPI app returned by build_asgi()."""
    from fastapi.responses import JSONResponse, HTMLResponse

    @app.get("/fact-index", include_in_schema=False)
    def fact_index(format: str = "json"):
        data = build_index()
        if format == "html":
            r = data["record"]
            rows = "".join(
                f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in r["by_fact_class"].items()
            )
            prec = r["block_precision"]
            prec_txt = f"{prec:.1%}" if isinstance(prec, (int, float)) else "n/a (small n)"
            html = f"""<!doctype html><meta charset=utf-8>
<title>Onyx Fact Index</title>
<style>body{{font:15px/1.6 system-ui,sans-serif;max-width:720px;margin:40px auto;padding:0 16px;color:#111}}
h1{{font-size:22px}} table{{border-collapse:collapse;margin:12px 0}} td{{border:1px solid #ddd;padding:4px 10px}}
.k{{color:#666}} code{{background:#f4f4f4;padding:1px 4px;border-radius:3px}}</style>
<h1>Onyx Fact Index</h1>
<p>{data['what']}</p>
<p class=k><b>Neutral by construction:</b> {data['neutrality']}</p>
<h2>Record</h2>
<p>Signed records: <b>{r['signed_records_total']}</b> &middot; resolved outcomes:
<b>{r['resolved_outcomes']}</b> &middot; block precision: <b>{prec_txt}</b> &middot;
on-chain attestations: <b>{r['onchain_attestations']}</b></p>
<p class=k>{r['precision_note'] or 'precision published above.'}</p>
<table><tr><td><b>fact class</b></td><td><b>signed</b></td></tr>{rows}</table>
<h2>Verify any entry (no trust required)</h2>
<p>See <code>/verify</code> for the key. {data['why_this_wins']}</p>"""
            return HTMLResponse(html)
        return JSONResponse(data)
