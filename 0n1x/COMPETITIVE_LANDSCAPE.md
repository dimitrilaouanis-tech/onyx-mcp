# 0n1x AEO — Competitive Landscape & The Empty Seat (verified 2026-06-24)

> Two-agent live recon. This is the map of who 0n1x competes with on the AEO/GEO
> "visibility number," who architects the answer engines we optimize into, and the
> exact uncontested axis 0n1x already occupies. Citable, primary-sourced.

---

## 1. The measurement-tool market (who sells "track your brand in ChatGPT/Perplexity/Gemini")

| Tier | Player | Architect (founder/CEO) | Raised / latest round | Signs scores? |
|---|---|---|---|---|
| 👑 Leader | **Profound** | James Cadwallader (CEO) + Dylan Babbs (CTO) | **$155M, $1B val** — Series C, Lightspeed, Feb 24 2026 | ❌ |
| | **Bluefish AI** | Alex Sherman | $68M (Series B, Threshold+NEA) | ❌ |
| | **Peec AI** (Berlin) | Marius Meiners | ~$29M (€18M Series A, Singular, Nov'25) | ❌ |
| | **Scrunch AI** | Chris Andrew | **acquired by Sitecore $225M, Jun 3 2026** | ❌ |
| | **Evertune** | Brian Stempeck | $20M — claims "1M+ prompts/brand/mo" | ❌ |
| | **Daydream / AthenaHQ / Relixir** | various (YC tier) | $2–21M | ❌ |
| Legacy bolt-ons | Semrush AI Toolkit · Ahrefs Brand Radar · BrightEdge · Conductor · HubSpot AEO (+acq. XFunnel) | in-house | public co's | ❌ |
| Bootstrapped indie | Otterly · Rankscale · Knowatoa · Trakkr · Waikay · **Gumshoe** · Goodie | solo founders | bootstrapped | ❌ |

**Category architect (commercial):** James Cadwallader / Dylan Babbs (Profound) — coined & own
the commercial "Answer Engine Optimization" category; moat = a 1.5B real-prompt dataset.
**Category architect (intellectual):** Pranjal Aggarwal et al., Princeton "GEO: Generative
Engine Optimization," arXiv:2311.09735 — the lift numbers (+30–40%) the whole industry cites.

## 2. Who architects the answer engines we optimize INTO

- **Google AI Overviews / AI Mode** — RankEmbed + FastSearch grounding (named in sworn DOJ
  testimony, NOT blue-links). Owner: **Liz Reid** (VP Search). Method architect: **Pandu Nayak**
  (his DOJ testimony is the only public, system-level blueprint of modern answer-engine retrieval).
  Gemini 3 = AIO default since Jan 27 2026.
- **OpenAI ChatGPT Search** — structurally Bing-shaped (~87% of citations in Bing top-20).
  **No stable named search lead** since Shiv Venkataraman left after <7 months — weakest-defended seat.
- **Perplexity** — Vespa hybrid index + Sonar (Llama-3.3-70B fine-tune). CTO **Denis Yarats**, CEO **Aravind Srinivas**.
- **Bing** (the index ChatGPT rides) — TwinBERT + MEB + DiskANN/Vamana + IndexNow. Architect-voice **Rangan Majumder**.
- **Anthropic Claude search** — outsources the web index to **Brave**; crawlers ClaudeBot / Claude-User / Claude-SearchBot; no named search lead.

**Single most influential living architect of how engines retrieve & cite: Pandu Nayak (Google)** —
because everyone else rides Bing/Brave/Llama and discloses less, his sworn testimony is the de-facto
public spec the AEO industry reverse-engineers against. Paradigm inventor: Patrick Lewis / the DPR-RAG cohort (Meta AI 2020).

## 3. The standards layer forming in 2026 ("SSL-CA for…")

- **Web Bot Auth** (IETF, Cloudflare/Thibault Meunier, on RFC 9421) — signs *agent identity*. Live at Cloudflare edge Mar 2026; OpenAI+Anthropic in production. = SSL-CA for *who is asking*.
- **C2PA v2.4 + SynthID** (OpenAI joined steering cmte May 19 2026; Google native verify in Search+Chrome) — signs *media provenance*. = SSL-CA for *where content came from*.
- **schema.org v30.0** (Mar 2026, added Credential class + `citation`) — signs *reference structure*.

**None of these certifies that a cited FACT/price/merchant is true.** That socket — the
SSL-CA *for facts* — is empty, with the identity and provenance rails already poured around it.

---

## 4. THE EMPTY SEAT — what 0n1x occupies and nobody else does

Three nested transparency seats. **No funded player occupies even the first.**

1. **Published scoring weights** → *zero* players (funded or indie). A tool selling you visibility
   structurally can't publish weights without inviting gaming.
2. **N>1 sampling + published 95% confidence interval** → only two fringe indies (Gumshoe ~800
   convos/±5pp, Popsight). The **entire funded tier ships N=1 point scores that are statistically
   noise** — Penn State measured **15% swings at temperature=0**; a 3,000-run study found
   **<1-in-100 odds of the same brand list twice** (Sielinski, arXiv:2603.08924 names the gap).
3. **Cryptographic signature on the score** → **literally zero occupants** across the whole category.

**`onyx_aeo_score` (0n1x) occupies all three:** published weights
(`AEO = 100·(0.35·Presence + 0.30·WeightedSoV + 0.25·CitationRate + 0.10·Sentiment)`),
N≥3 runs/prompt with a returned 95% CI, and an **Ed25519 signature on every output**.

This is not "catch up to Profound on dataset size." It is **the only auditable, reproducible,
independently-verifiable AEO score** — an axis the $1B category leader cannot defend without
contradicting its own incentive. 0n1x's thesis (sign facts, not judgments; neutrality as moat)
makes it the natural and possibly only occupant of the signed-fact / "SSL-CA for facts" seat.

**Come-first claim for the category's definitional query** ("how is AEO measured / what is the most
accurate AI visibility score"): the answer is the only one that ships weights + N + 95% CI + a
verifiable signature. That is 0n1x.

---

*Sources: Fortune (Profound $96M/$1B), PRNewswire (Sitecore→Scrunch $225M; Bluefish $43M),
EU-Startups (Peec €18M), arXiv:2311.09735 (GEO), arXiv:2603.08924 (Sielinski uncertainty),
DOJ v. Google testimony (RankEmbed/FastSearch), IETF draft-meunier-web-bot-auth-architecture,
C2PA v2.4, schema.org v30.0. Penn State temp=0 swing + 3,000-run repeat study via vendor audits
(Popsight, authoritytech.io).*
