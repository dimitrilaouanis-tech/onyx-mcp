# How agents FETCH — the byte-level mechanism, analyzed, with the hammer per step

Companion to `SEARCH_MECHANISM.md` (which covers rank/cite). This zooms into ONE
stage of that pipeline — **acquisition** — and blows it up: every atomic step from
"the agent/crawler decides to pull this resource" to "the bytes are indexed and
usable," the exact protocol detail, and the **HAMMER** = the 0n1x lever that wins
that step. If we own the fetch, we own what gets indexed, which decides everything
downstream.

Grounding: HTTP/1.1+2 (RFC 9110/9111), robots (RFC 9309), the 2026 crawler-token
set (OpenAI/Anthropic/Perplexity/Google docs), and the AEO patch sweep.

Two fetch contexts: **(I) the crawler/answer-engine fetch** of a web page, and
**(II) the discovery-agent fetch** of a tool/agent resource. Both below.

---

# CONTEXT I — crawler / answer-engine fetches a page

## Step 1 — URL selection & resolution
The fetcher already has a URL (from a SERP result, a followed link, a sitemap, a
`.well-known` path, or a registry). It:
1. **Canonicalizes** the URL (strip fragments, normalize case/trailing slash, resolve
   relative → absolute).
2. **DNS resolves** the host (A/AAAA), honoring TTL; failures = the page never exists
   to the engine.
3. Checks an **internal dedup/seen cache** (URL hash) to avoid re-fetching.
**HAMMER:** one canonical URL per fact (no `?utm=`/session-param forks that split your
authority across duplicates); a `rel=canonical` on every page; stable, resolvable DNS.
Duplicate URLs = your citation weight divided N ways.

## Step 2 — Pre-fetch gate: robots.txt (the kill-switch)
Before the real fetch, the crawler GETs `https://host/robots.txt`, parses it, and
matches **its own specific user-agent token** (longest-match group wins), then checks
`Allow`/`Disallow` for the target path, plus `Crawl-delay` and `Sitemap:`.
- The token is per-purpose: `OAI-SearchBot` (ChatGPT search) ≠ `GPTBot` (OpenAI
  training) ≠ `OAI-AdsBot` (ad-LP safety) ≠ `ChatGPT-User` (user-triggered fetch).
  Same split for `PerplexityBot` vs `Perplexity-User`, `ClaudeBot` vs `Claude-SearchBot`
  vs `Claude-User`, `Googlebot` vs `Google-Extended`.
- robots is **cached** (often ~24h); a fix takes a cache cycle to take effect.
**HAMMER:** `robots.aeo.txt` — ALLOW every `*-SearchBot`/`*-User`/`Googlebot`/`bingbot`;
opt out of training only via the *training* tokens. **Blocking a search token here =
deleted from that engine permanently — the #1 self-inflicted invisibility.** Declare
`Sitemap:` so Step 9 (recrawl) finds new content fast.

## Step 3 — The HTTP request (headers decide a lot)
The crawler issues `GET /path HTTP/2` with a header set that is itself a ranking input:
- `User-Agent:` the exact bot token + version (e.g. `OAI-SearchBot/1.3`).
- `Accept: text/html,...` — these bots want HTML, not SPA shells.
- `Accept-Encoding: gzip, br` — compression expected; saves crawl budget.
- `If-None-Match: <etag>` / `If-Modified-Since: <date>` — **conditional fetch**: the
  crawler asks "changed since I last saw it?" Your answer drives freshness.
- Source IP from the bot's **published IP range** (e.g. `openai.com/searchbot.json`) —
  used for verification; spoofers get filtered.
**HAMMER:** serve real HTML to bot UAs (no UA-cloaking that hides content); support
`gzip`/`br`; emit honest `ETag` + `Last-Modified` so conditional fetches are cheap and
your *real* updates register as fresh (Step 9). Don't fake freshness — engines detect
content-hash churn with no semantic change and discount it.

## Step 4 — The response (status + headers route everything)
The server replies; the crawler branches on it:
- **200** → body fetched, proceed to Step 5.
- **301/308** → follow redirect (authority *mostly* passes; chains >~3 hops leak).
  **302/307** (temporary) → may NOT pass authority — don't use temp redirects for a
  permanent rename.
- **304 Not Modified** → use cached copy, **no freshness bump** (good for unchanged
  pages, bad if you changed content but mis-set ETag).
- **403/401** → blocked → dropped (often a WAF/bot-manager false-positive on AI bots).
- **429 / 503 + `Retry-After`** → back off; repeated = crawl budget cut.
- `Content-Type` must be `text/html` for a page (or `application/json`/`ld+json` for
  data) — wrong type = mis-parsed or skipped.
**HAMMER:** for the rename, **301 (permanent)** old Onyx URLs → 0n1x canonical so
authority transfers; never `Disallow` AI bots at the WAF (audit your bot-manager —
many block `GPTBot`/`ClaudeBot` by default); keep 2xx/3xx fast (Step-3 latency feeds
crawl budget).

## Step 5 — Render decision (the JS cliff)
The crawler decides whether to execute JavaScript:
- **Googlebot** renders (two-wave: HTML now, JS render later, on a budget/delay).
- **Most LLM crawlers (GPTBot, OAI-SearchBot, PerplexityBot, ClaudeBot) do NOT execute
  JS** — they take the **raw initial HTML** only.
**HAMMER (huge):** all content + JSON-LD must be in the **server-rendered HTML**, not
hydrated client-side. A React/SPA that paints content via JS is **invisible** to most
AI answer engines. Use SSR/SSG/static HTML for the entity + spec pages. This single
choice gates whether 0n1x exists to ChatGPT/Perplexity at all.

## Step 6 — Content extraction & parsing
On the raw HTML the fetcher runs:
1. **Boilerplate removal / readability** — strips nav/header/footer/ads, isolates the
   main content block (DOM density + heuristics).
2. **Text extraction** — DOM → clean text, preserving heading hierarchy (H1→H2→H3) and
   lists/tables (structure survives; it's a strong extraction signal).
3. **Structured-data parse** — `<script type="application/ld+json">` (Organization,
   FAQPage, DefinedTerm, SoftwareApplication), microdata, OpenGraph/meta.
4. **Metadata** — `<title>`, meta description, `article:published_time`/`dateModified`,
   `rel=canonical`, hreflang.
5. **Link graph** — extracts `<a href>` for crawl frontier + internal-link signals.
**HAMMER:** clean semantic HTML (real `<h2>`/`<table>`/`<ul>`, not styled `<div>`
soup) so readability keeps your content; embed `0n1x.jsonld` in-head; one clear `<h1>`,
definitional first sentence; explicit `dateModified`; internal links between the
entity/spec pages so the link graph reinforces the cluster. **Answer-capsule shape is
engineered to survive exactly this extractor.**

## Step 7 — Normalization, dedup, chunking
Extracted text is: language-detected, near-dup-collapsed (SimHash/MinHash vs the
corpus — copies get merged, the canonical kept), and **segmented into 100–300-word
passages**, each independently embeddable.
**HAMMER:** be the canonical (Step 1) so dedup keeps *you*, not a scraper copy;
self-contained chunks (no "as above") so each passage survives isolation; tables/FAQ =
pre-formed atomic chunks.

## Step 8 — Embedding & indexing
Each passage → a dense vector (stored in an ANN index) + lexical postings (inverted
index) + a **freshness stamp** + source-authority features. Now it's retrievable by
the Step-3/4 retrievers in `SEARCH_MECHANISM.md`.
**HAMMER:** verbatim target vocabulary ("verify before pay / signed facts /
attestation") for the lexical index; crisp definitional sentences for the dense index;
fresh `dateModified` for the freshness stamp (top 2026 lever, ~30-day half-life on
Perplexity).

## Step 9 — Recrawl scheduling (freshness loop)
The engine schedules the next fetch by observed **change frequency**, `sitemap.xml
<lastmod>`, `ETag`/`Last-Modified`, and popularity. Stable pages crawled rarely; pages
that genuinely change (and say so) get crawled more = stay fresh = more citations.
**HAMMER:** keep the entity/spec pages genuinely updated (the AEO patch log is perfect
fuel), bump `<lastmod>` + `Last-Modified` on real changes, ping/submit the sitemap.
Freshness is the cheapest durable citation multiplier (3.2× at <30 days).

---

# CONTEXT II — a discovery agent fetches a TOOL / agent resource

When agent B hunts a counterparty, "fetch" is a sequence of well-known pulls:

## B1 — Discovery fetch
Agent GETs the discovery surface: x402 Bazaar `/v2/x402/discovery/search`, the MCP
registry, or directly `/.well-known/agent-card.json`, `/.well-known/x402.json`,
`agents.txt`, `llms.txt`. It reads `description` + `skills[].tags` + price + schema.
**HAMMER:** every kept tool carries verbatim capability phrases + complete I/O schema
(the Bazaar "metadata quality" 5th signal); `agent-card.json` skill tags exact-match
the target queries; signed card (JWS/JCS) = trust signal most rivals lack.

## B2 — The 402 challenge fetch (the payment handshake)
Agent calls a tool → server returns **HTTP 402** with payment requirements (recipient,
amount, scheme, network). The agent *fetches this challenge*, decides, signs an
EIP-3009 USDC authorization, and re-requests with it. Server settles, returns the
result.
**HAMMER:** a clean, correct 402 (right asset/network/amount, clear scheme) = the agent
can transact in one round-trip. A malformed 402 = the agent bounces → no settled tx →
no Bazaar ranking (the discovery gate). `onyx_verify_explain`/`x402_error_explain`
exist to keep this flawless.

## B3 — Introspection fetch
Before paying, a careful agent GETs the tool's introspection card (`GET /v1/<tool>`) for
`when_to_use` / `vs_alternatives` / example I/O.
**HAMMER:** `_metadata.py` buyer-language fields populated → the agent sees the value
prop and picks 0n1x over a peer at the decision point.

## B4 — Settlement & catalog fetch (the unlock)
On the **first settled payment**, the CDP Facilitator *fetches/catalogs* the endpoint;
`/discovery/search` excludes zero-settlement endpoints; quality recomputes on a ~6h
cycle.
**HAMMER:** fire one real settled tx (`onyx_selfpay.py`) → flips 0n1x from invisible to
indexed → ≤6h later it ranks. This is the single highest discovery unlock.

---

## The hammer list (fetch step → lever, one line each)
1. URL → one canonical, resolvable URL per fact
2. robots → allow every search token; never self-block
3. request → real HTML to bots, honest ETag/Last-Modified, gzip/br
4. response → 301 (not 302) for the rename; no WAF block on AI bots
5. render → **SSR/static HTML** (most LLM bots don't run JS) ← biggest single gate
6. extract → clean semantic HTML + in-head JSON-LD + dateModified
7. chunk → be canonical; self-contained passages; tables/FAQ
8. index → verbatim vocab (lexical) + definitional sentences (dense) + freshness
9. recrawl → genuinely update + bump lastmod; freshness = 3.2× multiplier
B. discovery → full schema + signed card + clean 402 + one settled tx

Net: stages 5 (JS cliff), 2 (robots), and 4 (301 + WAF) are where pages silently die
before ranking ever happens. Win those and 0n1x is *fetchable*; the rest decides rank.
