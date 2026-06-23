# 0n1x AEO patch — 2026-06 (last-90-days delta)

Live-web sweep folding the newest answer-engine + agent-discovery changes into the
model in `SEARCH_MECHANISM.md` / `AEO_PLAYBOOK.md`. Tags: CONFIRM / EXTEND /
CONTRADICT vs the prior baseline. Dates + sources inline. Verify before betting.

---

## ANSWER ENGINES — what changed

### Google (AI Mode / AI Overviews)
- **Gemini 3 = global default for AIO (Jan 27 2026).** Reshuffled ~42% of previously-cited
  domains, emits ~32% more source URLs/response. → **EXTEND.** Model-version swaps are a
  *discontinuity*; add a "model-version drift" variable. (almcorp.com)
- **Organic rank decoupled from AIO citation:** share of AIO citations from top-10 organic
  pages fell 76% (Jul'25) → 38% (early'26). → **CONTRADICT** any reliance on classic SERP
  rank as a citation proxy. (almcorp.com)
- **🎯 Google "Preferred Sources" extended to AIO + AI Mode (announced May 27 2026).** 345K+
  sources; opted-in sites see **3–7× citation rate** + a badge; AI-surface only, does NOT
  touch organic. → **EXTEND — NEW orthogonal signal + an OPT-IN we can take.** (9to5google,
  searchenginejournal)
- May'26 UI: inline citations next to the supporting sentence; new "Expert Advice" block
  pulls first-hand forum/social/review perspectives. → tilts toward first-hand/UGC. (exact
  day unconfirmed)

### OpenAI (ChatGPT search)
- **Citation collapse Feb–Apr 2026:** volume −86–94%; US zero-citation rate 28% → 78% by
  Apr 26. ChatGPT increasingly answers WITHOUT citing. → **CONTRADICT** "good retrieval ⇒
  citation"; winning a citation is now a smaller, more selective lottery. Add an
  *answer-without-citation* probability. (seoclarity.net)
- **New crawler token `OAI-AdsBot/1.0`** (ad landing-page safety, not training). Live set:
  `OAI-SearchBot/1.3`, `GPTBot/1.3`, `ChatGPT-User/1.0`, `OAI-AdsBot/1.0`. Rule holds:
  **block GPTBot, ALLOW OAI-SearchBot** = stay in search, opt out of training.
  (developers.openai.com) → update `robots.aeo.txt` to name OAI-AdsBot explicitly.

### Perplexity
- **3-layer reranker w/ a HARD authority gate:** L1 BM25+embeddings, L2 cross-encoder,
  **L3 XGBoost drop-gate** (~0.7 threshold) that *hard-drops* sources below an
  entity-clarity/authority bar on entity queries, plus curated authority allow-lists
  (GitHub/Amazon/LinkedIn/Reddit) + topic multipliers (AI/tech/sci/biz). → **EXTEND** — a
  hard gate + allow-list, not soft rerank. (authoritytech.io, ziptie.dev — vendor RE, specifics
  indicative). *0n1x note: GitHub is on the allow-list → our GitHub presence is a Perplexity lever.*
- **Strongest freshness bias of any engine, ~30-day window.** → **CONFIRM** (engine-weight it).

### Microsoft (Copilot/Bing)
- **Bing Webmaster "AI Performance" report — public preview Feb 10 2026.** Exposes Copilot
  citation counts + **grounding queries** (the phrases the AI used to retrieve your page) —
  closest thing to ground-truth on what matched. → **EXTEND** observability. (blogs.bing.com)

### Cross-engine source shifts (the off-site map moved a lot)
- **🔴 YouTube overtook Reddit as #1 cited domain overall** (~16% vs ~10%). → **CONTRADICT**
  "Reddit is #1." Reddit still leads *Perplexity* (46.7%). (georaiser.com)
- **🔴 LinkedIn = #2 and fastest riser:** social-citation share 7.8%→11.7% Jan→May'26
  (+49.9%); ChatGPT #11→#5 in 3 months; Copilot LinkedIn-heavy (43.8% of its social cites).
  **Pulse *articles* = 72.2% of LinkedIn citations** vs 26.1% posts. → **EXTEND — new target.**
  (otterly.ai, meltwater, semrush)
- **ChatGPT US:** Wikipedia 13.15% + Reddit 11.97% = >25% of all cites; outside those two no
  domain >3%; WSJ/NYT/Bloomberg absent from top 20. Wikipedia share *trending down* but still
  #1 raw. → **EXTEND** (the "established media" lean is really Wikipedia+Reddit+Forbes/Reuters).
  (prnewswire/5W)
- **Claude = the legacy-press, least-fresh engine** (36% past-year cites vs ChatGPT 56%; NYT/
  Atlantic/Economist). → **EXTEND** — 4th distinct engine profile.
- **Fandom leads Google AI Mode (7.16%);** review sites (G2/Capterra/Trustpilot), Quora,
  Medium, Substack now top-10 tier. (5W, contently.com)
- **Reddit is category-conditional:** overall freq −50% but sole-source cites +31%, commercial
  share +73% (Tinuiti Q1'26). Spikes for product/comparison queries. → **EXTEND.**
- **Freshness quantified:** 30-day-fresh = **3.2× citations**; AI-surfaced URLs 25.7% fresher;
  44% of AIO cites from 2025 alone. → **CONFIRM + quantify.** (omnibound.ai)
- **#1 cause of zero citations = crawler access**, not authority. Block GPTBot/ClaudeBot or
  ship no extractable formatting → authority is irrelevant. (pixelmojo.io)
- **llms.txt still NOT a citation factor** (~10% adoption; 408 of 500M AI-bot visits). Keep as
  agent manual only. → **CONFIRM (dead).** (ppc.land, presenc.ai, allmo.ai)

### 🧭 Strategic: the dev/protocol niche (most relevant to 0n1x)
- **Stack Overflow is becoming the AI "verification layer"** (49K-dev survey: "almost right but
  not quite" = #1 gripe 66%; 75% ask a human when they distrust AI). → **directly validates the
  0n1x signed-ground-truth thesis** — be the *verifiable* source, not the high-volume one.
  (adtmag.com)
- **Web3 protocol citation (Feb'26 GEO guidance):** prioritize official **docs home, API
  reference, token page, governance, security, ecosystem** pages; cite the **spec/standard by
  name**, not buzzwords; 3 independent write-ups still unlock Wikipedia (WP:NCORP).
  (seeklab.io, medium/berelfarkas)
- **GAP:** no published 2026 study gives GitHub/HN/Stack-Overflow *citation-share %* for
  technical queries — an unoccupied research lane (0n1x could publish it, signed).

---

## AGENT DISCOVERY — what changed

- **Bazaar now split:** `/v2/x402/discovery/search` (hybrid semantic+full-text, ≤20, relevance+
  quality ranked, URL-substring fallback) vs `/v2/x402/discovery/resources` (paginated
  inventory); NEW `/discovery/merchant?payTo=` + `/discovery/mcp`. **5 ranking signals:**
  relevance, buyer reach (30d), tx volume (30d), recency, **metadata quality** (schema/desc
  completeness); **6-hour recompute** (settled payment takes ≤6h to affect rank). → **EXTEND/
  CONFIRM.** Settlement-gate + 30-day-idle removal unchanged. (docs.cdp.coinbase.com/x402/bazaar)
- **Agentic.Market launched Apr 21 2026** — public no-login marketplace on Bazaar (semantic
  search, 70 curated, live metrics, its own MCP). → **NEW discovery front-end.** (coinbase.com)
- **Official MCP Registry = two tiers:** "Official" (publisher-verified) vs "Claimed"
  (ownership-verified); namespace `io.github.*` via GitHub OAuth, `com.*` via DNS-TXT/HTTP
  challenge; metaregistry backed by Anthropic+GitHub+PulseMCP+Microsoft (~9,652 latest records,
  May 24'26). → **EXTEND.** (truefoundry, github/mcp registry)
- **Glama scoring published:** overall = **70% Tool-Definition-Quality + 30% Server Coherence**;
  the **60% mean + 40% MIN** is only INSIDE the TDQ sub-score. Tiers A≥3.5…F<1.0. → **CONFIRM/
  REFINE** — "fix worst tool" still true, but now also fix *server coherence* (naming
  consistency, disambiguation, completeness). (glama.ai/mcp/methodology)
- **A2A production cut: v1.0.0 (Mar 12'26), v1.0.1 (May 28'26).** Card location + `signatures`
  landed back in v0.3.0 (Jul'25). Signing = **JWS (RFC 7515) over JCS-canonicalized (RFC 8785)**
  — matches our Ed25519-over-JCS convention. → **CONFIRM/EXTEND.** (github.com/a2aproject/A2A)
- **🎯 ERC-8004 LIVE on Ethereum mainnet Jan 29 2026**, deployed across 30+ chains at fixed
  addresses (Identity `0x8004A169…a432`, Reputation `0x8004BAa1…9b63`; same on Base/Polygon/Arb/
  Op/etc.). **Validation Registry STILL under active TEE-community discussion, revised "later
  this year."** → **SHARPEN** — Identity + Reputation are deployed; the **Validation/attestation
  seat is officially still open** — *the 0n1x wedge holds and is now concrete.* (github.com/
  erc-8004, eips.ethereum.org/EIPS/eip-8004)
- **UCP (Google/Shopify) claims discovery+cart;** ACP (OpenAI/Stripe) checkout; AP2 (FIDO-
  governed) authorization. → watch the converter seat. (a2aprotocol.ai)

---

## What this CHANGES for 0n1x (action deltas)
1. **Opt into Google Preferred Sources** when the entity domain is live — 3–7× citation, AI-
   surface only, free. (new top move)
2. **Off-site targets re-ranked:** add **YouTube** (now #1 overall) + **LinkedIn Pulse articles**
   (fastest riser, 72% of LI cites) to the Reddit/awesome/Wikipedia list. Per-engine: GitHub →
   Perplexity allow-list; LinkedIn → Copilot; Wikipedia+Reddit → ChatGPT; Fandom → AI Mode.
3. **Build citable spec pages**, not just llms.txt: docs-home + **API reference + governance +
   security + ecosystem** pages, each Answer-Capsule shaped, spec cited by name. Leans into the
   Stack-Overflow "verification layer" shift = our signed-fact thesis.
4. **ERC-8004:** integrate the live Identity + Reputation registries (fixed addresses) and
   target the still-open **Validation Registry** seat explicitly — concrete, not aspirational.
5. **Bazaar:** fill `metadata quality` (the 5th signal) on every tool; expect ≤6h after the
   first settled tx to rank. List on **Agentic.Market**.
6. **Glama:** raise **Server Coherence** (naming/disambiguation/completeness), not just worst-tool.
7. **robots:** add `OAI-AdsBot` to the named set; keep all *-SearchBot allowed.
8. **Measurement:** `onyx_aeo_score` should weight **freshness per-engine** (Perplexity >>),
   model a **Claude legacy-press profile**, and an **answer-without-citation** rate. Current
   tool is single-engine (Exa); multi-engine is the next iteration.
