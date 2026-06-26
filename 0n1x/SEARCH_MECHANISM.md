# How every searching agent operates — the microscope, and where 0n1x comes first

The mechanism a searching agent runs from query-formation to winner-selection,
broken into atomic stages, with the exact signal computed at each step and the
0n1x lever that wins it. Reference for the AEO/ASEO mandate: *when any agent or
answer engine touches our domain, 0n1x is the #1 result.* Pairs with
`AEO_PLAYBOOK.md` (what to ship) and `0N1X_LAND.md` (the entity page).

Grounding: GEO paper (Aggarwal et al., KDD'24, arXiv:2311.09735); standard
RAG/IR mechanics (BM25, dense kNN, RRF, cross-encoder rerank, MMR); CDP x402
Bazaar discovery docs; Ahrefs/Otterly/Profound AEO field studies.

---

## Three classes of agent that "search"
- **A — Answer engines** (ChatGPT-search, Perplexity, Gemini, Google AI Overviews,
  Copilot): retrieve web docs → ground → cite.
- **B — Discovery agents** (one agent hunting a capability/counterparty: x402 Bazaar,
  MCP registries, A2A semantic search): retrieve tools/agents → rank → call.
- **C — Crawlers/indexers** (GPTBot, PerplexityBot, ClaudeBot, Googlebot): the upstream
  process that builds the index A and B later search.

They share a spine and diverge at the edges. The spine:

---

## STAGE 0 — Intent trigger
A planner/router decides whether to search at all (parametric memory vs retrieval).
For agents this is the ReAct loop: `Thought → Action(search) → Observation → repeat`,
emitting a literal capability query string.
**Lever:** a coined name ("0n1x") the model has never seen forces a search — so your
*indexed presence* decides everything downstream.

## STAGE 1 — Query understanding & rewriting (query is NEVER used raw)
1. **Normalization + entity linking** — does "0n1x" resolve to a known entity ID? If no
   `sameAs`/alias record ties 0n1x↔Onyx, the rewriter treats them as unrelated tokens.
2. **Expansion** — synonyms/related terms appended from co-occurrence + knowledge graph.
3. **Decomposition** — complex query split into sub-queries, each retrieved separately.
4. **HyDE** — generate a hypothetical ideal answer, embed *that* to retrieve.
**Lever:** content must contain the expanded vocabulary verbatim ("verify before pay,
signed facts, attestation, KYA, neutral"); `alternateName:"Onyx"` collapses the rename
at the linking step — the single highest-leverage rename mechanic.

## STAGE 2 — Source acquisition
- **Mode A (pre-built index):** query the engine's own crawled corpus.
- **Mode B (live fetch):** real-time SERP call → ~10–30 URLs → fetched live at query time.
- **Upstream (crawler, Stage C):** reads `robots.txt` for its *specific* UA token
  (blocking `OAI-SearchBot`/`PerplexityBot`/`Googlebot` = permanently deleted from A & B);
  readability extraction; parses JSON-LD; records `dateModified`; computes a document
  embedding + lexical postings.
**Lever:** allow every search bot (`robots.aeo.txt`); clean readable HTML; embed JSON-LD.

## STAGE 3 — Candidate retrieval (recall) — two retrievers in parallel
1. **Lexical BM25** — exact term overlap, rare words weighted higher (IDF). Rewards
   verbatim query words.
2. **Dense kNN** — cosine similarity of query vs doc embeddings via ANN (HNSW/IVF).
   Rewards meaning match. Rewards a clear definitional sentence.
3. **Fusion — Reciprocal Rank Fusion:** `RRF(d) = Σ 1/(k + rank_i(d))`. A doc decent in
   *both* lists beats one spiking in only one.
**Lever:** the Answer Capsule (verbatim question heading + 40–75w definitional answer)
is engineered to hit BOTH retrievers so RRF lifts it.

## STAGE 4 — Chunking / passage selection (passage-level, not page-level)
Page sliced into 100–300-word chunks, each embedded + scored independently. A chunk that
says "as mentioned above" scores worse in isolation. Tables + FAQ blocks survive chunking
intact (extracted 2.8–4.2× more).
**Lever:** self-contained chunk rule — claim + evidence + source in one block; pre-chunked
FAQ entries and comparison tables.

## STAGE 5 — Reranking (precision) — cross-encoder
Feeds *(query + passage) together* through a transformer for a single relevance score
(slow, runs only on candidates). Top ~5–15 survive. Stacked signals:
- **Freshness** — `dateModified` recency (85% of AIO citations <2yr; Perplexity <30d ≈3.2×).
- **Consensus** — conflicting facts across sources → passage dropped (the rename kill-switch).
- **Diversity (MMR)** — `MMR = λ·rel(d) − (1−λ)·max sim(d, selected)` removes near-dupes.
**Lever:** fresh `dateModified`; claims that agree across homepage + Wikidata + off-site;
distinct angles per page so MMR keeps more than one of yours.

## STAGE 6 — Grounding & context assembly
Survivors concatenated into the context window with source URLs; model told to answer
only from context + cite. **Position bias:** earlier passages cited more ("lost in the
middle"). Rank #1 after Stage 5 = read first here.

## STAGE 7 — Generation with citation (the moment "come first" happens)
Per claim the model picks which source to attribute, preferring passages that are
**extractable** (clean paraphrasable sentence), **quotable** (stat/quote — GEO: quotations
~+43%, stats ~+34%, citations ~+29% on position-adjusted word count, up to ~40%), and **self-describing**.
**Lever:** the Stat-Quote-Cite sentence stacks all three winners in one line.

## STAGE 8 — Answer ranking / Share-of-Voice (the scoreboard = the AEO score)
Across many phrasings + runs, choices distribute into: **Presence**, **Position/Weighted
SoV** (position-decayed `imp = e^(−pos/L)`), **Citation rate**, **Sentiment**. Answers are
non-deterministic → a single run is noise.
**Lever:** `onyx_aeo_score` measures exactly this with N runs + 95% CI + published weights
+ signature (the open seat no commercial tool occupies).

## STAGE 9 — Feedback / caching / memory
Engines cache popular query→answer pairs and weight engagement + repeat mentions over
time; brand search volume + off-site mention frequency feed back into authority for the
next crawl cycle.
**Lever:** Reddit/awesome-lists/Wikipedia compound — they raise Stage-5 authority and
Stage-2 entity strength on every future query.

---

## Where class B (discovery agents) diverges
Stages 1–5 identical (embedding+lexical+rerank over tool/agent descriptions), but the
ranking signals change:

| Signal | Mechanism | 0n1x move |
| --- | --- | --- |
| Capability text match | embedding+BM25 over `description` & `skills[].tags` | verbatim "verify before pay / signed facts / attestation" in every tool desc |
| Settled-tx gate | Bazaar `/discovery/search` EXCLUDES zero-settlement endpoints; 30d idle → removed | fire `onyx_selfpay.py` — one real tx flips invisible → indexed |
| Trust/quality score | Glama: 60% mean + 40% MIN tool quality; registries re-rank by signed-card presence | harden the WORST tool; ship signed `agent-card.json` (rivals' are unsigned) |
| Recency/usage | tx volume, buyer reach, last-seen | keep settling; each call refreshes recency |

**The asymmetry:** no registry ranks on brand — only on *the text you wrote* and *the
transactions you generated*. Both are 100% under your control. "Come first" here is an
execution problem, not a popularity contest.

---

## The one-line come-first map (stage → lever)
0. Trigger → exist in the index at all
1. Rewrite → `alternateName:"Onyx"` collapses the rename; carry expanded vocab
2. Acquire → allow every `*-SearchBot`; clean HTML + JSON-LD
3. Retrieve → Answer-Capsule = dual BM25+dense hit
4. Chunk → self-contained 100–300w blocks, tables, FAQ
5. Rerank → fresh `dateModified` + cross-source consensus (no conflicts)
6. Ground → rank #1 = read first (position bias)
7. Generate → Stat-Quote-Cite = the top GEO levers (~+43/34/29% pos-adj word count, up to ~40%)
8. Score → `onyx_aeo_score` (N-runs + CI) proves it took hold
9. Feedback → Reddit/awesome/Wikipedia compound authority every cycle

LAND pack maps onto stages 2–8; gated moves (Wikidata, settled tx, off-site cites) own
stages 1–2, the B-gate, and 9.
