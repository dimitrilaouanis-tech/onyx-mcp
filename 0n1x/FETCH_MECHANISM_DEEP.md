# How agents fetch & retrieve — FULL DEPTH, analyzed, with the hammer

The deep version of `FETCH_MECHANISM.md`. Four parallel primary-source dives:
crawler internals, extraction/parsing internals, per-engine RAG internals, and
agent-side wire protocols. Every claim tagged **[DOC]** (vendor-documented /
sworn testimony) · **[MEASURED]** (third-party study w/ data) · **[RE]**
(reverse-engineered / inferred). Contested numbers carry a confidence flag.
Each section ends in the **HAMMER** = the concrete 0n1x lever. Sweep date 2026-06.

> The one fact that governs everything: **the purpose-built AI crawlers (GPTBot,
> OAI-SearchBot, ClaudeBot, PerplexityBot) execute ZERO JavaScript and run on tight
> ~1–5s fetch timeouts. Google AI Overviews / Gemini and Bing/Copilot have NO
> dedicated AI crawler — they ride Googlebot / bingbot, which DO render.** Raw-HTML
> vs rendered is the master split.

---

# PART A — Crawler fetch internals

## A1. Exact identities (live tokens — most blogs are stale)
- Versions live now: **GPTBot/1.3, OAI-SearchBot/1.3** (not 1.0/1.1), Googlebot **2.1**,
  bingbot **2.0**. [DOC]
- IP-range JSONs (verify membership, not UA+ASN — spoofers share Azure AS8075): [DOC]
  `openai.com/gptbot.json` (21 prefixes, Azure), `…/searchbot.json` (35),
  `…/chatgpt-user.json` (~251, rotated), **OAI-AdsBot has NO IP JSON + no robots
  compliance statement**; `claude.com/crawling/bots.json` (one /22 + 19 GCP /32);
  `perplexity.ai/perplexitybot.json` (8, AWS AS16509); Google
  `developers.google.com/static/crawling/ipranges/common-crawlers.json` (path moved
  in 2026 from `/static/search/apis/ipranges/`).
- Purpose split is per-token: `GPTBot`=train, `OAI-SearchBot`=ChatGPT-search index,
  `ChatGPT-User`=live user fetch, `OAI-AdsBot`=ad-LP safety (non-training). Same
  train/search/user triad for Claude and Perplexity. `Google-Extended` = a robots
  TOKEN only (no crawler; Gemini-training control; does NOT affect AI Overviews). [DOC]
- **Web Bot Auth (the spoofer-proof primitive):** ChatGPT-User/agent requests are
  signed via **RFC 9421 HTTP Message Signatures (Ed25519)** — headers `Signature-Agent`,
  `Signature-Input`, `Signature`; key dir at
  `chatgpt.com/.well-known/http-message-signatures-directory`. W3C-final May 2026. [DOC]

**HAMMER:** allow every `*-SearchBot`/`*-User`/Googlebot/bingbot; opt out of *training*
only via train tokens; verify bot identity by **IP-JSON membership or Web Bot Auth
signature**, never UA+ASN. (Our `robots.aeo.txt` already does the allow side; add
OAI-AdsBot — done.)

## A2. The JS-render cliff — the master kill-step [MEASURED]
- **Vercel × MERJ (Dec 2024):** every major AI crawler executes **0% JS** —
  **569M GPTBot fetches, 0% executed**, even when it downloads `.js`. Googlebot/
  bingbot render (evergreen headless Chromium/Edge); GPTBot/OAI-SearchBot/ClaudeBot/
  PerplexityBot do **not**.
- **GSQI / Glenn Gabe (Aug 2025) controlled test:** ChatGPT, Perplexity, Claude all
  **categorically failed** to read fully client-rendered URLs (ChatGPT: "can't read JS";
  Perplexity: "Access Denied"; Claude: "no visible content").
- **Crucial nuance:** the cliff is **client-side hydration**, not "JS on the page."
  Content in the **initial HTML byte stream** (incl. raw JSON, React Server Components)
  IS ingested; an empty `<div id="root">` SPA shell is invisible.
- Vendor deltas [RE]: prerender → +750% AI visibility; pages with FCP <0.4s averaged
  **6.7 ChatGPT citations vs 2.1** for slower pages.

**HAMMER:** the 0n1x entity + spec pages MUST be **SSR/SSG/static HTML**. Test =
`curl` the URL; whatever is NOT in that raw HTML does not exist to ChatGPT/Perplexity/
Claude. This single choice gates existence. (Our `0N1X_LAND.md` + `0n1x.jsonld` are
static — keep them that way; never ship the entity page as a hydrated SPA.)

## A3. The fetch stack + robots parsing (the silent-death rules)
- Google [DOC]: HTTP/1.1+2 (opt out via **421**), conditional GET (`If-Modified-Since`/
  `ETag`→**304**), gzip/deflate/**br**. robots parser (RFC 9309, open-sourced):
  **longest-path match; equal-length tie → least-restrictive (Allow wins)**, NOT
  "Disallow wins"; `*` and `$` supported; **UA case-insensitive, path case-sensitive**;
  **parse cap = 500 KiB (512,000 bytes) — everything past it silently ignored.**
- Google robots error rule [DOC]: 4xx≠429 → **fail-OPEN**; 5xx/timeout → **12h
  fail-CLOSED → 30-day cached → then fail-open**; **429 = rate-limit, NOT "no file."**
- AI crawlers are sloppy [MEASURED]: GPTBot **34.8% 404 + 14.4% redirect**, ClaudeBot
  34.2% 404 (vs Googlebot 8.2%/1.5%) — weak frontier, weak/no conditional-GET. Tight
  ~1–5s timeouts.
- **Crawl-delay honored only by Bing + Anthropic**; Google/Apple/Perplexity ignore it →
  **429 + CDN rate-limiting is the only real lever.** [DOC/RE]
- ⚠️ **Perplexity-User explicitly ignores robots.txt** ("user requested the fetch");
  Cloudflare (Aug 2025) caught **stealth undeclared Perplexity crawling** off official
  IPs across ASNs and de-listed it as a Verified Bot. ChatGPT-User, by contrast, saw
  `Disallow` and **stopped** (fail-closed correctly). [MEASURED]

**HAMMER:** keep `robots.txt` < 500 KiB with Disallows EARLY; serve honest `ETag`/
`Last-Modified` + gzip/br; never return 5xx on robots (12h fail-closed = invisibility
window); for the rename use **301 (permanent), not 302/307** so authority transfers;
audit the WAF/bot-manager — many block GPTBot/ClaudeBot by default (403 = dropped).

---

# PART B — Extraction & parsing internals

## B1. Boilerplate removal — the scorers that keep or drop you [DOC]
- **Mozilla Readability.js** (reference reader): class/id weight **±25**; tag base scores
  (`DIV +5`, `PRE/TD/BLOCKQUOTE +3`, `OL/UL/LI/FORM −3`, `H1–H6/TH −5`); paragraph
  score = base +1, **+1 per comma**, +length-quantile; **nodes with innerText <25 chars
  skipped**; final score × **(1 − linkDensity)**; `CHAR_THRESHOLD=500`.
- **Trafilatura** = de-facto 2026 default for RAG + LLM-corpus curation. Cascade XPath →
  readability-lxml → jusText. Benchmarks: trafilatura **F1 0.958**, readability_js 0.947,
  raw html-text 0.665. High-recall/lower-precision.
- 2026 frontier: **MinerU-HTML** (Qwen3-SLM sequence-labeler distilled to XPath; only
  0.4% pages need live inference). And: **only 39% of pages produce identical output
  across extractors** (arXiv 2602.19548) — extraction is lossy + nondeterministic.
- **Failure modes that drop YOUR content:** JS/SPA shells (B/A2); **link-density killing
  link-heavy prose** (a paragraph of links gets dropped — *removing one comma* can flip
  it); **<25-char paragraphs hard-skipped**; **tables mangled/dropped** (jusText removes
  tables wholesale).

**HAMMER:** clean semantic HTML; main content **link-sparse**, paragraphs **>25 chars**
with real commas; real `<table>`/`<ul>`/`<h2>` not `<div>` soup; don't bury the
definitional sentence among links. Answer-capsule shape already satisfies the Readability
scorer — keep capsules prose-dense, not link-dense.

## B2. Does schema/JSON-LD actually lift AI citations? Mostly NO [DOC]
- **Ahrefs (1,885 schema pages vs 4,000 controls, Mar 2026):** AI Overviews **−4.6%**,
  AI Mode +2.4%, ChatGPT +2.2% (≈ noise). *"Adding schema didn't boost citations on any
  platform."*
- **Otterly (Dec'25–Mar'26):** of 7 platforms **only Gemini retrieved the JSON-LD**; a
  fact placed ONLY in FAQ schema was retrieved by **no** platform. FAQ rich results
  fully retired **May 7 2026** (markup still parsed, no SERP feature).
- **So JSON-LD's real job is ENTITY DISAMBIGUATION, not ranking/answers** — and only via
  the knowledge-graph path. Google entity-linking: string → candidate (surface-form
  dict from Wikipedia/Wikidata aliases) → disambiguation → **MID (`/m/`,`/g/`)**;
  Freebase→Wikidata migration means the **Wikidata Q-item carries the mapping**.
  `sameAs` = the explicit reconciliation hint (NOT a guaranteed binding); **`@id`** =
  node id. The **Wikidata Q-item is the load-bearing asset, not the on-page markup.**

**HAMMER:** keep `0n1x.jsonld` (Organization + `alternateName:"Onyx"` + `sameAs[]`) — but
understand it buys *disambiguation* (0n1x==Onyx), not citations. **The citation lever is
the Wikidata Q-item + real third-party mentions, not more schema.** Put JSON-LD in **raw
server HTML** (non-rendering bots never see hydrated JSON-LD).

## B3. Structure → citation, and dedup → collapse [DOC]
- Why structured blocks win: **Dense X Retrieval (EMNLP'24)** — an atomic self-contained
  proposition (table row+header, Q&A pair) embeds as a tight vector; a multi-idea
  paragraph embeds as a **smeared centroid**. Quantified **+12 Recall@5**. Chunkers
  (LangChain Recursive/MarkdownHeader) split on `\n\n`/headings → lists/Q&A/rows land on
  clean boundaries; prose gets cut mid-sentence. **Provenance correction:** the "4.2×
  tables" figure is **folklore [RE]**; the defensible primary is **Princeton GEO
  (SIGKDD'24): +41% quotations / +32% stats / +30% cite-sources / +28% fluency.**
- **Dedup collapses you to ONE representative per cluster** [DOC]: Google **SimHash**
  (64-bit, Hamming ≤3, 8B pages); LLM corpora **MinHash-LSH** (FineWeb 5-gram, 112 hashes,
  14×8 bands, ~0.75; per-snapshot beat global). Bing (Dec'25): "LLMs group near-duplicate
  URLs into one cluster, choose one page to represent the set" — **non-chosen members
  don't appear in AI answers at all.** `rel=canonical` is a **HINT Google can override**;
  **no first-seen primitive** → a scraper copy with more links/cleaner URL/faster load can
  be chosen canonical over the original. AI-paraphrased scrapes evade SimHash.

**HAMMER:** be the canonical — one clean fast URL, internal links pointing to it,
`rel=canonical` everywhere, 301 the old Onyx URLs. Ship facts as **atomic blocks**
(Q&A, tables, propositions) for the +12-Recall embedding win. Stat-Quote-Cite per the
GEO +41/32/30 levers. Watch for paraphrased scrapes outranking us.

## B4. The markdown surface (where it IS going) [DOC]
- Serving markdown to bots is real at infra scale: **Cloudflare "Markdown for Agents"**
  (`Accept: text/markdown` → on-the-fly convert, ~80% token cut), **Mintlify** auto-emits
  `/llms.txt` + `/llms-full.txt` + a **`.md` per page**, Claude Code WebFetch sends
  `Accept: "text/markdown, */*"`.
- **llms.txt is DEAD as a consumed index** [DOC/MEASURED]: Mueller "no AI service uses
  it / they don't even check"; **Limy.AI: 408 of 515,382,577 LLM-bot events hit
  /llms.txt (0.00008%)**; Ahrefs: 97% of llms.txt files got zero requests. BUT the
  per-URL **`.md` files it points to ARE fetched.** Correct headers for a `.md` mirror:
  `Content-Type: text/markdown`, `Vary: Accept`, `X-Robots-Tag: noindex`.

**HAMMER:** keep `llms.txt` only as the agent manual (don't expect citations). The real
win is a **per-page `.md` mirror** with `Accept: text/markdown` content-negotiation for
the entity + spec pages.

---

# PART C — Per-engine RAG internals (so we hammer each engine's actual graph)

> All four are **hybrid retrieval → multi-stage rerank → grounded synthesis**, NOT pure
> vector RAG. Differentiators: who owns the index + the fan-out planner.

## C1. Perplexity [DOC]
Own index on **Vespa** (>200B URLs, >400 PB, HNSW), **hybrid BM25+dense at doc AND
chunk level**; ML model predicts per-URL recrawl cadence; p50 358ms. Embeddings
`pplx-embed` (Qwen3, 0.6B/4B) — *production use unconfirmed*. Reranker (documented shape):
**fast lexical+embedding → cross-encoder final**. The famous **"L3 drop-threshold 0.7" +
XGBoost entity-gate is [RE] from a single leak Search Engine Land itself flagged
unverified** — treat the *behavior* (hard authority gate + discard-and-re-query) as real,
the exact 0.7 as unproven. **Sonar** = Llama-3.3-70B synthesizer bound by retrieved
evidence. Strongest freshness bias; curated authority allow-list incl. **GitHub**.

**HAMMER for Perplexity:** GitHub presence is a direct lever (it's allow-listed); freshness
matters most here (<30d); strong entity clarity to survive the authority gate.

## C2. ChatGPT search [RE-heavy] — structurally **Bing-shaped**
Hybrid: **Bing named provider + own OAI-SearchBot index**. **[MEASURED] 87% of SearchGPT
citations are in Bing's top-20** (vs 56% Google) → **Bing SERP rank is the dominant
retrieval lever.** [RE] pipeline: classifier ("Sonic") → planner fan-out ~2.4 queries
(up to 3 recursive rounds) → cross-encoder rerank (`ret-rr-skysight-v3`,
`use_freshness_scoring_profile`) → ~128-tok chunks → final 3–5 pages → ~5–6K-token
context. **Abstention** governed upstream by `no_search_prob` (~0.2) — explains the 2026
zero-citation surge. OAI-SearchBot doesn't run JS.

**HAMMER for ChatGPT:** rank in **Bing** (IndexNow push, bingbot-friendly) — it's 87% of
the battle; Wikipedia + Reddit are its top external sources.

## C3. Google AI Overviews / AI Mode [DOC — sworn DOJ testimony]
**The under-appreciated fact: AI Overviews ground via FastSearch (RankEmbed signals), a
deliberately faster/lower-quality retriever — NOT the blue-link ranking.** Pipeline =
inverted-index candidate gen → **RankEmbed/RankEmbedBERT** dense rerank (trained on
**70-day** click+query logs → freshness is **retraining-bounded**, not real-time) →
Gemini synthesis. **Query fan-out:** one question → "a multitude" of sub-queries
(Deep Search = "hundreds"; standard ~28 in a sim [RE]); merge algo undisclosed. Gemini
grounding API exposes `webSearchQueries` / `groundingChunks` / `groundingSupports` +
`confidenceScores`. Fandom over-indexes here. ScaNN-in-AI-Mode = **unconfirmed, don't
assert.**

**HAMMER for Google:** classic Googlebot indexability (it renders, so SSR less critical
here, but still safest) + entity strength in the **Knowledge Graph (Wikidata Q-item)** so
RankEmbed/FastSearch resolve 0n1x cleanly; structured feeds beat web freshness.

## C4. Bing / Copilot [DOC]
Own everything: **TwinBERT** (cached doc embeddings, ~20ms), **MEB** (135B-param binary
sparse model, 720GB, **retrained daily**, models *negative* intent, 100% of queries),
ANN = **DiskANN/Vamana** (1B vectors/64GB, <5ms@95%; L=50 R=128 α=1.2) + **SPANN** +
DistributedANN (50B-vector single graph). **Prometheus/Orchestrator** iteratively
generates internal Bing queries. **IndexNow** push → content appears "within minutes"
(Google has NOT adopted). The "128k words/turn" figure is rumor.

**HAMMER for Bing/Copilot:** adopt **IndexNow** (minutes-fresh) — cheapest fast-index win
and it flows straight into ChatGPT (C2). LinkedIn is Copilot's heaviest social source.

## C5. Cross-engine constants (the shared math we exploit) [DOC]
RRF **k=60** (consensus-across-lists beats single-list top rank). MMR **λ=0.5** default
(keep distinct pages → multiple 0n1x angles survive). Freshness decay: ES gauss/exp,
decay 0.5 → half-life = scale (Google QDF bursts on query demand). **Lost-in-the-middle**
(Liu 2023): U-curve, mid-context accuracy drops ~20–30pp → **reranker order decides which
source is cited** → rank #1 or last, not middle. Cross-encoder rerank is the single
highest-leverage stage across engines.

**HAMMER:** diverse angles per page (survive MMR); be the consensus answer across many
phrasings (RRF k=60 rewards appearing in multiple sub-query lists — feeds Google fan-out
+ ChatGPT recursive rounds); freshness to ride QDF.

---

# PART D — Agent-side fetch wire protocols (so other AGENTS find/transact 0n1x first)

## D1. The loop [DOC]
Model is stateless; a **harness** does every fetch out-of-band and feeds bytes back.
Anthropic: `tool_use`(input=native object) → `tool_result` in a `user` msg (no `tool`
role). OpenAI: `tool_calls`(arguments=JSON string) → `role:"tool"` msg. Fetched content =
**untrusted DATA, not instructions** (indirect-injection seam — matches our hard rule).

## D2. MCP [SPEC'D+LIVE 2025-11-25]
Transport = stdio + **Streamable HTTP** (HTTP+SSE deprecated 2025-03-26). Single endpoint;
POST every JSON-RPC msg w/ `Accept: application/json, text/event-stream`; notifications →
**202**; session via **`Mcp-Session-Id`** header; `MCP-Protocol-Version` header post-init.
`initialize`→`notifications/initialized`→`tools/list`→`tools/call` (`CallToolResult` =
content[]+isError+structuredContent). Registry `server.json` reverse-DNS name, namespace
verify via **GitHub OAuth (`io.github.*`)** or **DNS-TXT `v=MCPv1; k=ed25519; p=…`**.
⚠️ **2026-07-28 RC removes initialize/session entirely** (stateless redesign) — watch it.

**HAMMER:** publish `server.json` under verified `io.github.dimitrilaouanis-tech/...`
(fans out to Smithery/Glama/PulseMCP); full `inputSchema`+`outputSchema`+`title` on every
tool (Glama = 70% tool-def-quality + 30% server-coherence).

## D3. x402 [v1 LIVE] — the byte-level handshake
402 body `accepts[]`: `{scheme:"exact", network, maxAmountRequired, payTo, asset,
resource, mimeType, maxTimeoutSeconds, extra:{name,version}}`. Client returns base64
**`X-PAYMENT`** = `{scheme,network,payload:{signature, authorization:{from,to,value,
validAfter,validBefore,nonce}}}` — `authorization` = exactly **EIP-3009
transferWithAuthorization** args, EIP-712 signed against the **token's own** domain
(USDC Base: name "USD Coin", version "2", chainId 8453, `0x833589…2913`). Facilitator
`/verify`→`{isValid,payer}`, `/settle`→`{success,transaction,network}`; success returns
**`X-PAYMENT-RESPONSE`**. Bazaar `/v2/x402/discovery/{search,resources}` ranks on
**relevance + (buyer reach, tx volume, recency, metadata quality)**; **zero-settlement =
never surfaced.**

**HAMMER:** clean correct 402 (right asset/network/amount); **one real settled tx
(`onyx_selfpay.py`) lights buyer-reach + tx-volume + recency** → ≤6h recompute → ranked.
Highest single discovery unlock.

## D4. A2A [SPEC'D v0.3/v1.0] — signed card
Card at **`/.well-known/agent-card.json`** (renamed from agent.json). `skills[]{id,name,
description,tags[],examples[]}`, `capabilities`, **`signatures[]`** = detached **JWS
(RFC 7515)** over `BASE64URL(protected) + "." + BASE64URL(JCS(card − signatures))`
(JCS = RFC 8785); key via `kid`@`jku`. **Spec proves the card is signed by its CLAIMED
key — NOT by a vetted/neutral party.** That gap = the 0n1x neutrality wedge.

**HAMMER:** ship a signed `agent-card.json` with exact-match `tags`
(`verify-before-pay`,`agent-trust`,`signed-facts`,`attestation`) — most rival cards are
unsigned; and position 0n1x as the *neutral verifier* the JWS spec deliberately doesn't
provide.

## D5. ERC-8004 [DRAFT EIP / contracts LIVE] — the concrete wedge
Live singletons, **same address 31+ chains** (verified on Base mainnet): Identity
`0x8004A169…a432`, Reputation `0x8004BAa1…9b63`. v1.x = **ERC-721** (agent = NFT,
`tokenId==agentId`, `tokenURI`→registration JSON→A2A card). Reads: `tokenURI`,
`ownerOf`, `getAgentWallet`; **no native `resolveByAddress`** (index `Registered`
events). Reputation: `giveFeedback(agentId, int128 value, decimals, tags, feedbackURI,
feedbackHash)` — **facts as signed fixed-point, "permissionless write, filter on read"**
(= sign-facts-not-judgments). **Validation Registry = the open seat:** `validationRequest`/
`validationResponse(uint8 0-100, responseURI, responseHash, tag)` are SPEC'D; **validator
selection, staking/slashing, disputes = OPEN** ("under active discussion"). A signed event
bus with no economic security yet.

**HAMMER:** (1) ship a **read tool** `onyx_erc8004_lookup` (`eth_call` the singletons —
no funds, real today) = 0n1x as the reader/verifier; (2) publish the **0n1x signed
validation-attestation format** fitting `validationResponse` and occupy the empty
Validation seat before it closes; (3) reputation `giveFeedback` is literally our
signed-fact model on-chain.

---

# PART E — The hammer map (ranked by leverage)

1. **SSR/static HTML** for entity+spec pages — without it 0n1x doesn't exist to ChatGPT/
   Perplexity/Claude (0% JS, 569M-fetch proof). *Master gate.*
2. **Rank in Bing (IndexNow)** — 87% of ChatGPT citations + minutes-fresh; Google hasn't
   adopted, so it's a pure ChatGPT/Copilot lever.
3. **Wikidata Q-item** (+`sameAs`) — the entity asset that feeds Google FastSearch/
   RankEmbed + ChatGPT/Claude entity resolution. Schema markup alone does NOT cite.
4. **One settled x402 tx** — lights Bazaar buyer-reach/volume/recency; zero-settlement =
   invisible. `onyx_selfpay.py` armed.
5. **301 the rename + clean robots (<500KiB, no 5xx) + WAF audit** — silent-death fixes.
6. **Atomic answer-capsules (Q&A/tables/propositions) + Stat-Quote-Cite** — +12 Recall
   embedding + GEO +41/32/30 citation levers; survive Readability + chunkers.
7. **Per-page `.md` mirror** (`Accept: text/markdown`, `Vary`, `noindex`) — the live
   markdown surface; llms.txt index itself is dead.
8. **Off-site by engine:** GitHub→Perplexity (allow-list), LinkedIn→Copilot, Wikipedia+
   Reddit→ChatGPT, YouTube/Fandom→AI Mode.
9. **Signed agent-card + server.json (verified namespace)** — A2A/MCP discovery; neutrality
   wedge the JWS spec leaves open.
10. **ERC-8004 read tool + validation-attestation format** — occupy the still-open
    Validation seat; reputation `giveFeedback` = our signed facts on-chain.

Master takeaway: stages **A2 (JS cliff), C2/C4 (Bing owns ChatGPT), C3 (FastSearch not
blue-links), B2 (Wikidata not schema), D3 (settled-tx gate)** are where most players
silently lose before ranking starts. Win those five and 0n1x is structurally first.
