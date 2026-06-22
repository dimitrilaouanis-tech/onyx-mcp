"""Refresh the Onyx Agent-Economy Index CARD.

Runs the signed onyx_agent_economy_index tool (which re-pulls the LIVE Bazaar
census every call), embeds the current published-source figures + the latest
skeptic/news headlines, and writes TWO always-current artifacts:

  agent_economy_card.json  — the full Ed25519-SIGNED machine card (the truth)
  agent_economy_card.md    — the human dashboard, "last updated" stamped

Re-run anytime (or on a schedule) to refresh. The live half (census /
concentration) updates automatically on every run; the volume / self-cycling /
decline figures + NEWS update whenever this file's NEWS list is refreshed from
a research pass.

Usage:  py refresh_index_card.py [max_pages]   (default full sweep)
"""
from __future__ import annotations

import json
import sys
import time

from tools_pkg import agent_economy_index as aei
from tools_pkg import _onyx_sign

import os
# Write to the served .well-known dir so /index + /index.json serve the latest.
os.makedirs(".well-known", exist_ok=True)
OUT_JSON = ".well-known/agent-economy-index.json"
OUT_MD = ".well-known/agent-economy-index.md"

# --- latest NEWS / skeptic headlines (refresh from research passes) ---
NEWS = [
    {"date": "2026-03-11", "who": "Noah Levine, a16z crypto",
     "headline": "Real agent-payment volume ~$1.6M after wash filter, not $24M",
     "quote": "The gap tells you how early-stage even the measurement infrastructure is.",
     "url": "https://cointelegraph.com/news/ai-agent-payment-volume-closer-to-1-6m-says-a16z"},
    {"date": "2026-03", "who": "Lucas (@OnchainLu), Artemis",
     "headline": "48% of txns / 81% of volume is self-cycling",
     "quote": "Most of the x402 numbers circulating are noise.",
     "url": "https://www.cryptopolitan.com/x402-agentic-ai-commerce-growth/"},
    {"date": "2026-04-02", "who": "OKX Ventures",
     "headline": "x402 transactions crater 92% from Dec-2025 peak; revenue -97%",
     "quote": "731K->57K txns/day; protocol revenue $1.02M -> $35K.",
     "url": "https://blockchain.news/news/okx-ventures-ai-agent-economy-x402-transactions-drop-92-percent"},
    {"date": "2026-04-17", "who": "CryptoSlate",
     "headline": "76% of the 'agent economy' is just bots shuffling stablecoins",
     "quote": "Staggering flows, but most of it is bots.",
     "url": "https://cryptoslate.com/staggering-28-trillion-is-flowing-through-cryptos-agent-economy-but-76-of-it-is-just-stablecoins/"},
    {"date": "2026-06-03", "who": "Chainalysis",
     "headline": "100M+ cumulative agentic payments on Base; $1+ txns now 95% of volume",
     "quote": "Shift away from sub-cent meme-mint toward substantive payments.",
     "url": "https://www.chainalysis.com/blog/x402-agentic-payments-adoption/"},
]


def fmt_usd(n):
    if n is None:
        return "n/a"
    if n >= 1_000_000:
        return f"${n/1_000_000:.2f}M"
    if n >= 1_000:
        return f"${n/1_000:.0f}K"
    return f"${n:,.0f}"


def build_md(card):
    c = card["live_census"]
    rv = card["real_volume_30d"]
    sc = card["self_cycling_share"]
    dc = card["decline"]
    att = card.get("onyx_attestation", {})
    lines = []
    lines.append("# Onyx Signed Agent-Economy Index — Live Card")
    lines.append("")
    lines.append(f"> **Last updated:** {card['as_of']}  ·  signed Ed25519 (`{att.get('kid','?')}`)  ·  verify: {card.get('verify_pubkey_at','')}")
    lines.append("")
    lines.append("## The number")
    lines.append(f"- **Real agent-payment volume (30d):** {fmt_usd(rv['low_usd'])}–{fmt_usd(rv['high_usd'])}")
    lines.append(f"- **Headline (raw, unfiltered):** {fmt_usd(card['headline_volume_30d_usd'])}")
    lines.append(f"- **Inflation multiple:** {card['inflation_multiple']}×")
    lines.append(f"- **Self-cycling:** {sc['of_transactions_pct']}% of txns / {sc['of_volume_pct']}% of volume ({sc['source']})")
    lines.append(f"- **Trend:** {dc['txns_from_dec2025_peak_pct']}% txns from Dec-2025 peak; {dc['revenue_pct']}% revenue ({dc['source']})")
    lines.append("")
    lines.append("## Live census (pulled this refresh)")
    lines.append(f"- Advertised resources: **{c['advertised_resources']:,}**  ·  scanned this run: {c['scanned']:,} ({c['pages']} pages)")
    lines.append(f"- Real unique operators: **{c['unique_operators']:,}**")
    lines.append(f"- Top-3 operator concentration: **{c['top3_operator_share_pct']}%**  ·  top-10: {c['top10_operator_share_pct']}%")
    lines.append(f"- Stale (>90d) in sample: {c['stale_pct']}%")
    lines.append(f"- Networks: {', '.join(f'{k} ({v})' for k,v in c['networks'].items())}")
    lines.append("")
    lines.append("## Published sources (reconciled)")
    lines.append("| Source | Metric | Value | As of |")
    lines.append("|---|---|---:|---|")
    for s in card["published_sources"]:
        lines.append(f"| {s['source']} | {s['metric']} | {fmt_usd(s['value_usd'])} | {s['as_of']} |")
    lines.append("")
    lines.append("## Latest news / on-record skeptics")
    for n in NEWS:
        lines.append(f"- **{n['date']} — {n['who']}:** {n['headline']}  ·  *\"{n['quote']}\"*  [src]({n['url']})")
    lines.append("")
    lines.append(f"*Filter method: `{card['filter_method_version']}`. Scope: {card['scope_note']}*")
    lines.append("")
    lines.append("*Onyx — the neutral signed referee. We earn nothing from what we grade.*")
    return "\n".join(lines)


def main():
    max_pages = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    print(f"refreshing Index Card (max_pages={max_pages}) ...")
    card = aei.run(max_pages=max_pages)
    # Do NOT mutate `card` after signing — the signature covers it as-is.
    # News rides alongside in the markdown + a sidecar, not inside the signed object.

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(card, f, indent=1)
    with open(".well-known/agent-economy-index-news.json", "w", encoding="utf-8") as f:
        json.dump({"as_of": card["as_of"], "news": NEWS}, f, indent=1)
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write(build_md(card))

    chk = _onyx_sign.is_onyx_signed(card)
    print(f"  signature: {chk}")
    print(f"  wrote {OUT_JSON} + {OUT_MD}")
    print(f"  real volume: {fmt_usd(card['real_volume_30d']['low_usd'])}-{fmt_usd(card['real_volume_30d']['high_usd'])}"
          f" | headline {fmt_usd(card['headline_volume_30d_usd'])} | {card['inflation_multiple']}x"
          f" | operators {card['live_census']['unique_operators']} | top3 {card['live_census']['top3_operator_share_pct']}%")


if __name__ == "__main__":
    main()
