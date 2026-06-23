# 0n1x — integration plan for the 2026-06 updated data

Goal: fold every confirmed delta from `AEO_PATCH_2026-06.md` into the live 0n1x
system so the come-first mandate (`SEARCH_MECHANISM.md`) reflects the CURRENT
rules, across all three surfaces — answer engines, agent discovery, on-chain.

Legend: 🟢 autonomous (I can build + push) · 🟡 build now, publish needs you ·
🔴 gated (your account/funds/decision). Each item cites the patch delta it closes.

Sequenced by dependency × leverage. Phases can overlap; numbering = recommended order.

---

## PHASE 1 — Measurement: `onyx_aeo_score` v2  🟢
The tool must measure the world as it is now. Current tool = single-engine (Exa),
flat freshness, no abstention. Upgrade (new module `onyx_aeo_score` stays; add an
internal `_aeo_engines.py` helper so app.py is untouched):

1.1 **Per-engine profiles** — model 4 distinct engines, not one average:
    ChatGPT (Wikipedia+Reddit, high abstention), Perplexity (freshness++, GitHub/
    LinkedIn allow-list, hard authority gate), Gemini/AI-Mode (Fandom, model-drift),
    Claude (legacy-press, least fresh). *(patch: per-engine citation divergence)*
1.2 **Answer-without-citation rate** — add `abstention_rate` (share of prompts the
    engine answered with zero citations). *(patch: ChatGPT zero-cite 28→78%)*
1.3 **Per-engine freshness weight** — freshness term weighted highest for Perplexity,
    lowest for Claude. *(patch: Perplexity 30-day 3.2×; Claude least fresh)*
1.4 **Model-version stamp** — record the engine/model version in the signed payload so
    a score is comparable only within a model era. *(patch: Gemini 3 reshuffled 42%)*
1.5 Keep published weights + N-runs + 95% CI + signature. Add the new sub-metrics to
    the disclosed `weights`/`methodology`. Bump price tier note if call-count rises.
    **Deliverable:** `onyx_aeo_score` v2, still one `tools_pkg/` module, auto-registered.
    **Test:** weights sum to 1.0, CI math, graceful no-key, per-engine fields present.

## PHASE 2 — Model docs sync  🟢
2.1 Update `SEARCH_MECHANISM.md`: insert Perplexity's **L3 hard authority drop-gate**
    as a distinct stage (not soft rerank); add **abstention** at Stage 7; add
    **model-version drift** + **organic-rank decoupling** notes at Stage 8; add
    **Google Preferred Sources** as a Stage-2 personalization signal.
2.2 Update `AEO_PLAYBOOK.md` off-site section: re-rank targets to **YouTube (#1) →
    LinkedIn Pulse (#2 riser) → Reddit (category-conditional) → Wikipedia → awesome/
    GitHub**; add per-engine routing table; add Preferred Sources as move #1.
    **Deliverable:** both docs reflect the patch; single commit.

## PHASE 3 — Citable spec pages (answer-engine surface)  🟡
The Stack-Overflow "verification layer" + Web3-GEO finding says: ship official,
named-spec, Answer-Capsule-shaped pages. Build as static files in `0n1x/site/`:
3.1 `docs.md` (docs-home), `api.md` (API/tool reference — the 22 kept tools), the
    existing `0N1X_LAND.md` as the entity page.
3.2 `governance.md`, `security.md`, `ecosystem.md` — the high-trust page types.
3.3 Each: question-heading + 40–75w capsule + Stat-Quote-Cite + the `0n1x.jsonld`
    block in head; cite the OA-1 / FACT_LAYER spec **by name**.
    **Deliverable:** `0n1x/site/` ready to publish to GitHub Pages / homepage.
    *(publish = 🔴 your call on where the entity-home domain lives)*

## PHASE 4 — Agent-discovery integration  🟢/🟡
4.1 🟢 **Bazaar metadata-quality (5th signal)** — audit every kept tool's
    description/schema completeness; ensure verbatim "verify before pay / agent trust
    / signed facts / attestation" + full input/output schema. *(patch: metadata
    quality now a ranked signal; 6h recompute)*
4.2 🟢 **Glama server-coherence** — naming consistency across the 22 tools, no
    ambiguous names, complete descriptions. *(patch: Glama 70% TDQ + 30% coherence)*
4.3 🟡 **`server.json` → official MCP Registry** under verified `io.github.
    dimitrilaouanis-tech/...` namespace (GitHub OAuth). Fans out to Smithery/Glama/
    PulseMCP. *(patch: Official-vs-Claimed tiers)*
4.4 🟡 **Signed `agent-card.json` to A2A v1.0.1** — confirm JWS-over-JCS, exact-match
    skill tags. *(patch: A2A v1.0.0/1.0.1 production cut)*
4.5 🔴 **List on Agentic.Market** (Apr-21 public marketplace) — needs the first
    settled tx to populate metrics.

## PHASE 5 — ERC-8004 on-chain integration (the concrete wedge)  🟡→🔴
*(patch: ERC-8004 LIVE mainnet Jan 29; Identity `0x8004A169…a432` + Reputation
`0x8004BAa1…9b63` fixed on 30+ chains; Validation Registry STILL OPEN)*
5.1 🟢 **Read-side first:** new tool `onyx_erc8004_lookup` — resolve an agent's
    Identity + Reputation entries from the live registries (read-only, no funds).
    Real, shippable, no gating. Establishes us as the reader/verifier.
5.2 🟡 **Validation attestation format** — design the 0n1x signed-validation object
    that fits the still-unfinished Validation Registry shape; publish it as the
    reference (occupy the empty seat before the spec closes). Aligns OA-1/FACT_LAYER
    with ERC-8004 Validation.
5.3 🔴 **Write-side** (register 0n1x identity / anchor an attestation on-chain) —
    gated on gas + your go. Defer until 5.1/5.2 prove the read+format.

## PHASE 6 — External "come-first" moves  🔴 (gated, sequenced for you)
6.1 **One settled tx** — fire `onyx_selfpay.py` (~0.002 USDC). Unblocks Bazaar +
    Agentic.Market metrics (≤6h recompute). Highest single discovery unlock.
6.2 **Wikidata Q-item** for 0n1x w/ "Onyx" alias — I draft every statement+source,
    you submit. Door into Gemini/AI-Mode.
6.3 **Google Preferred Sources opt-in** — once the entity domain is live (3–7×).
6.4 **Off-site push** — 1 YouTube explainer + 1 LinkedIn Pulse article + 1 Reddit
    answer-in-thread + awesome-list PRs. I draft, you post.
6.5 **Rename consensus fan-out** — "0n1x, formerly Onyx" across GitHub desc / PyPI /
    Smithery same week (no fact conflict). The "11-parallel" job.

---

## Dependency graph (what unlocks what)
- 6.1 settled tx → unblocks 4.5 + populates Bazaar/Agentic.Market ranking
- 3.x spec pages → prerequisite for 6.3 Preferred Sources + 6.2 Wikidata `sameAs`
- 5.1 read tool → de-risks 5.2 format → de-risks 5.3 write
- 1.x tool v2 → makes 6.x measurable (prove each move moved the number)

## Suggested execution order
**Now, autonomous:** 1 (tool v2) → 2 (docs) → 4.1/4.2 (Bazaar/Glama text) → 5.1
(ERC-8004 read tool) → 3 (spec pages, build).
**Then, with you:** 6.1 settled tx → 4.3/4.4 registry+card → 6.2 Wikidata → 3 publish
→ 6.3 Preferred Sources → 6.4 off-site → 6.5 rename fan-out → 5.2/5.3 Validation seat.

## Definition of done
Every patch delta has a closing artifact; `onyx_aeo_score` v2 measures the new world;
the LAND pack + spec pages reflect current rules; 0n1x is read-integrated with
ERC-8004 and holds the Validation-seat reference format; the gated list is drafted
and queued for your go.
