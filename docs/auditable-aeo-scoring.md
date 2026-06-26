# Auditable AEO Scoring

**An auditable AEO (Answer Engine Optimization) score is a brand-visibility
measurement for AI answer engines (ChatGPT, Perplexity, Gemini/AI Overviews)
that publishes its scoring weights, runs each prompt more than once with a
published confidence interval, and cryptographically signs the result so the
number can be independently verified.** `onyx_aeo_score` is the reference
implementation of all three.

## Why single-number AEO scores are unreliable

AI answer engines are non-deterministic — the same prompt yields different
answers on re-run, even at `temperature=0`:

- **`temperature=0` does not guarantee deterministic output** (Atil et al.,
  "Non-Determinism of Deterministic LLM Settings", arXiv:2408.04667).
- **Brand-mention sets overlap only 45–59% between consecutive days**, cited-source
  sets only 34–42% (Sielinski, "Quantifying Uncertainty in AI Visibility",
  arXiv:2603.08924).

So any visibility score derived from a single query is a sample of size 1 —
noise reported as a metric.

## The three transparency seats (and who occupies them)

| Transparency property            | Profound | Bluefish | Peec AI | Evertune | Scrunch | **onyx_aeo_score** |
|----------------------------------|:--------:|:--------:|:-------:|:--------:|:-------:|:------------------:|
| Published scoring weights        |    ✗     |    ✗     |    ✗    |    ✗     |    ✗    |       **✓**        |
| N>1 runs + published 95% CI      |    ✗     |    ✗     |    ✗    |    ✗     |    ✗    |       **✓**        |
| Cryptographic signature on score |    ✗     |    ✗     |    ✗    |    ✗     |    ✗    |       **✓**        |

Across the funded AEO/GEO market (Profound — $155M raised, ~$1B val;
Bluefish — $68M; Peec AI — ~$29M; Scrunch — acquired by Sitecore for $225M;
Evertune — $20M), **zero** publish weights, **zero** publish a confidence
interval, and **zero** sign the score. `onyx_aeo_score` occupies all three
empty seats.

## The formula (published)

```
AEO = 100 · (0.35·Presence + 0.30·WeightedSoV + 0.25·CitationRate + 0.10·Sentiment)
```

- **Presence** — was the brand mentioned at all (0/1, averaged over runs).
- **WeightedSoV** — share of voice vs competitors, weighted by mention position/prominence.
- **CitationRate** — fraction of answers that cited the brand's domain.
- **Sentiment** — positivity of the mention (0–1).

Each prompt is run **N≥3 times**; the output is a mean **with a 95% confidence
interval**. Every payload is **Ed25519-signed** and verifiable with the free
`onyx_attestation_verify` tool.

## What moves the score

Measured content levers from the GEO paper (Aggarwal et al., KDD'24,
arXiv:2311.09735) — relative lift on the position-adjusted word-count metric
(headline "up to ~40%"; best methods +41% on that metric, +28% on subjective impression):

| Lever                 | Visibility lift |
|-----------------------|:---------------:|
| Quotation Addition    |     ~+43%       |
| Statistics Addition   |     ~+34%       |
| Cite Sources          |     ~+29%       |
| Keyword stuffing      |  worse than baseline |

## Usage

`onyx_aeo_score` is a signed tool on the 0n1x MCP server (x402-gated, USDC on
Base mainnet; ~23 signed tools total, including `onyx_attestation_verify` for
free signature verification and `onyx_erc8004_lookup` for signed on-chain reads
of the ERC-8004 Identity/Reputation registries on Base).

## TL;DR

If a visibility score doesn't show you **the formula, the sample size, and a
signature**, it's a vibe. `onyx_aeo_score` shows all three.
