# 0n1x AEO/ASEO Playbook — "when any agent or search hits 0n1x, we come first"

Mandate: 0n1x is the #1 cited / recommended / discovered answer for its domain —
agent trust, verify-before-pay, signed facts, paid-MCP discovery — across **answer
engines** (ChatGPT, Perplexity, Gemini, AI Overviews, Copilot) and **agent
discovery** (x402 Bazaar, MCP registries, A2A).

Two surfaces, two playbooks. Answer engines crawl **web pages + Wikidata + off-site
citations** — NOT MCP endpoints. Agent discovery ranks on **tool-description text +
settled transactions**. You have to win each separately.

Grounding: GEO paper (Aggarwal et al., KDD'24, arXiv:2311.09735); Ahrefs/Otterly/SE
Ranking llms.txt studies; Profound/Peec/Semrush AEO-metric docs; CDP x402 Bazaar docs.

---

## Status legend
- ✅ SHIPPED this session (in `onyx_mcp/`)
- 🟡 READY — artifact authored here, needs publishing to the live web/registry
- 🔴 GATED — needs your hand (off-site account, Wikidata edit, or USDC deposit)

---

## A. The AEO NUMBER (the product)

- ✅ **`tools_pkg/onyx_aeo_score.py`** — signed AEO score, live in the lean catalog
  (`_keep.py`). Serves at `/v1/onyx_aeo_score`, in `/manifest`, `/agents.txt`,
  `/.well-known/x402.json` on next deploy. Price $0.50.
  - **The open seat:** every commercial AEO tool hides its weights and runs N=1/day.
    0n1x **publishes weights**, runs **N≥3 per prompt**, returns a **95% CI**, and
    **signs** the result. That is the differentiator and it is on-thesis (signed facts).
  - Formula (disclosed in every payload):
    `AEO = 100*(0.35*Presence + 0.30*WeightedSoV + 0.25*CitationRate + 0.10*Sentiment)`
    - Presence / CitationRate: closed denominator (fixed prompt set)
    - WeightedSoV: position-decayed brand impression vs competitors (GEO Eq.3)
    - Sentiment: normalized (score+1)/2
  - Needs `EXA_API_KEY` in the server env (same as `onyx_ai_visibility`).

## B. ANSWER-ENGINE surface (be the cited answer)

- 🟡 **Entity page** — `0n1x/0N1X_LAND.md`. Answer-capsule shaped (question heading +
  40–75w direct answer, definitional first sentence, comparison tables, FAQ — the
  shapes the GEO paper shows get extracted). **Publish at the entity-home URL** a
  crawler can reach (homepage and/or GitHub Pages).
- 🟡 **Structured data** — `0n1x/0n1x.jsonld`. `Organization` with
  `alternateName:["Onyx",...]` + `sameAs[]` — **this is the rename bridge** that tells
  the knowledge graph 0n1x == Onyx. Plus `SoftwareApplication`, `DefinedTermSet`,
  `FAQPage`. Drop in the page `<head>` as `<script type="application/ld+json">`.
- 🟡 **robots policy** — `0n1x/robots.aeo.txt`. ALLOW every `*-SearchBot`/`Googlebot`
  /`PerplexityBot` (these drive citations); training opt-out left as an explicit
  commented choice. Merge into the live `robots.txt`. **Biggest self-inflicted AEO
  mistake is blocking a search bot — don't.**
- 🔴 **Wikidata Q-item for 0n1x** — cheapest door into Gemini/AI Overviews (they read
  Google's Knowledge Graph; no Q-ID = invisible). No notability bar. Set P31 (instance
  of: protocol/software), P856 (official site), P571 (inception), **alias "Onyx"**,
  every statement citing a public source. Write the QID back into `0n1x.jsonld` `sameAs`.
- 🔴 **"0n1x, formerly known as Onyx" transition note** — publish that exact phrase
  (transition page + one press/blog item) and update third-party records (GitHub repo
  description, Smithery, PyPI, Crunchbase/LinkedIn if any) to the new name. **Mismatched
  facts across sources = engines skip the entity.** Ship the rename everywhere close
  together. Clean execution typically recovers in 4–8 weeks; Perplexity (live crawl)
  rewards fresh content fastest (<30 days = ~3.2× citations).

## C. OFF-SITE citations (the dominant ranking input)

Brand *mentions* predict AI citation far more than backlinks. Engines recommend what
**others** say, and each engine has its own citation graph (only ~11% overlap
ChatGPT↔Perplexity). Win them separately:

- 🔴 **Awesome-list PRs** — add 0n1x to `awesome-mcp-servers`, `awesome-x402`,
  `awesome-agents`. Lowest-bar, hits both live-retrieval and training corpus.
- 🔴 **Reddit answer-in-thread** — r/AI_Agents, r/mcp, r/LocalLLaMA: answer an existing
  "how do agents verify each other / trust before pay" thread, naming 0n1x as one
  option (consensus, not spam). Reddit ≈ 40% of AI consumer citations; top source for
  Perplexity + AI Overviews.
- 🔴 **Get INTO an existing "best agent-trust / x402 tools" listicle** — outreach the
  author; don't only write your own. Coverage breadth drives the ChatGPT multiplier.
- 🔴 **3 independent DR-70+ articles** → unlocks Wikipedia (press releases don't count).
  Wikipedia is the #1 ChatGPT/Claude source — a permanent trust node.

## D. AGENT-DISCOVERY surface (be found first by other agents)

- 🔴 **One real settled x402 transaction** — the single highest discovery unlock. The
  CDP Facilitator catalogs the endpoint the **first time it settles a real payment**;
  `/discovery/search` excludes zero-settlement endpoints; 30 days idle → removed.
  `onyx_selfpay.py` is already ARMED — needs ~0.002 USDC deposited to the buyer wallet
  on Base mainnet to fire (see memory: "Onyx Self-Pay ARMED").
- ✅/🟡 **Exact target phrases in tool descriptions** — `onyx_aeo_score` description
  carries "AEO score / answer-engine visibility / signed". Sweep the rest of the kept
  catalog so "verify before pay", "agent trust", "signed facts", "attestation" appear
  **verbatim** (Bazaar/registry search is hybrid embedding + full-text).
- 🔴 **`server.json` → official MCP Registry** (verified namespace
  `io.github.<org>/...`) → fans out to Smithery/Glama/PulseMCP. Then trigger Glama
  "Sync Server". Glama scores 60% mean + 40% MIN tool quality → **fix your worst tool**.
- 🟡 **Signed `/.well-known/agent-card.json`** with `skills[].tags =
  ["verify-before-pay","agent-trust","signed-facts","attestation"]` + a populated JWS
  `signature` (most competitor cards are unsigned — verifiable moat).

---

## Myths to NOT spend on (confirmed dead for answer-engine visibility)
- **llms.txt as a citation play** — Ahrefs (97% of 137k domains: zero bot requests),
  Otterly (0.1% of bot visits), SE Ranking (no measurable effect). Keep `llms.txt`
  only as the **agent operating manual**, not an AEO lever.
- **Dead schema rich-results** — HowTo, Sitelinks `SearchAction`, and the FAQPage rich
  *result* (markup removed). The FAQ *content* still helps extraction; the markup won't
  win a rich result. Keep FAQ content, don't expect SERP features from it.
- **Sparse/empty schema** — under-filled JSON-LD correlates *worse* than none. Fill
  every field or drop the type.
- **Keyword stuffing** — GEO study: −8.7%. Authentic phrasing beats stuffed queries.

---

## Recommended order of operations
1. Deploy (AEO tool goes live in catalog) + confirm `EXA_API_KEY` set.
2. Merge `robots.aeo.txt` into live `robots.txt` (prevents self-inflicted invisibility).
3. Publish `0N1X_LAND.md` + embed `0n1x.jsonld` at the entity-home URL.
4. Create the Wikidata Q-item with the "Onyx" alias; write QID into `sameAs`.
5. Ship the "formerly Onyx" rename across GitHub/Smithery/PyPI descriptions same week.
6. Fire `onyx_selfpay.py` (one settled tx) to unlock Bazaar discovery.
7. Awesome-list PRs + one Reddit answer-in-thread + push for one listicle inclusion.
8. Re-measure with `onyx_aeo_score` (brand "0n1x", aliases ["Onyx"]) weekly; track the
   number climbing with a 95% CI you can publish — proof the rename took hold.
