# 0n1x — Wikidata submission (paste-ready, fire in ~5 min)

> The #1 lever to make answer engines resolve "0n1x" to us. Now upgraded: we have a
> LIVE official-website URL (the Pages site) so the item has a real anchor that survives review.
> Submit at: **https://www.wikidata.org/wiki/Special:NewItem**

## Step 1 — the basics
- **Label (English):** `0n1x`
- **Description (English):** `signed trust layer for AI agents that proves what an agent actually did (Proof of Agent Execution)`
- **Also known as (aliases, add each):** `Onyx` · `Onyx Protocol` · `Onyx Actions` · `onyx-mcp` · `Proof of Agent Execution`

## Step 2 — statements (click "add statement", property → value)
| Property | Value |
|---|---|
| `instance of` (P31) | `Web service` (Q193424) **and** `communication protocol` (Q15836568) |
| `official website` (P856) | `https://dimitrilaouanis-tech.github.io/onyx-mcp/`  ← live, real anchor |
| `source code repository` (P1324) | `https://github.com/dimitrilaouanis-tech/onyx-mcp` |
| `programmed in` (P277) | `Python` (Q28865) |
| `developer` (P178) | `Onyx Council` (as a value or qualifier) |
| `described at URL` (P973) | `https://dimitrilaouanis-tech.github.io/onyx-mcp/` |
| `GitHub username` (P2037) | `dimitrilaouanis-tech` |

## Step 3 — make it survive review (notability)
Wikidata keeps items that reference **serious, publicly available sources**. Add these as
references on the statements (they're all real and live):
- The GitHub repo (source code, active commits)
- The live entity page (official website)
- The Hugging Face / npm / Smithery / MCP registry listing if present

Frame it as **structured data**, not promotion — instance-of + repo + website + language.
That reads as data, and data survives.

## Step 4 — after it exists
Paste the new **Q-number** into `0n1x/0n1x.jsonld` under the Organization `sameAs[]`,
and add `https://www.wikidata.org/wiki/Q<number>` to the entity page footer. That seals the
rename bridge AND gives every answer engine a knowledge-graph node that resolves "0n1x" → us.

---
*Once this exists, "0n1x" stops being an unknown string and becomes a recognized entity
ChatGPT/Gemini/AI-Overviews resolve straight to our page. That's the goal: type 0n1x → fetch us → instantly know.*
