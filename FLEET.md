# 0n1x FLEET — shared coordination manifest

**Purpose:** multiple parallel Claude sessions build 0n1x at once. Without coordination,
concurrent pushes to `main`/`gh-pages` clobber each other (last push wins, other work
vanishes). This is the single source of truth for **who owns what** and **how we merge**.
Read this FIRST before touching a shared repo. (Divergence-unanimous protocol, 2026-07-03.)

## The rule (non-negotiable)
1. **One lane per session.** Edit only files in your lane. Never `-A` over a sister's files.
2. **No direct pushes to `gh-pages`.** Only the Frontend Integrator deploys the site.
   Everyone else opens a PR / branch, or hands the built change to the Integrator.
3. **`main`: pull --rebase before every push.** Commit YOUR files by name, never `git add -A`.
4. **Branch-per-feature** when the work is big: `feat/<session>-<thing>`.
5. **Update this file** when you claim/release a lane (append to the log at the bottom).

## Lane ownership (claim yours, respect others')
| Lane | Owns | Repo/paths |
|---|---|---|
| 🚀 **Render / Launch** (Fleet Captain) | the Render backend deploy + integrates `main`/`gh-pages` | onyx-actions on Render, server_http.py, render.yaml |
| 🎨 **Frontend Integrator** | rhinogent.com UI + is the ONLY one who deploys `gh-pages` | rhinogent/src/**, the build+deploy |
| 🔧 **Economy / Resilience** | token engine, forecast market, emissions, backup, portal pointer, autonomy | onyx_mcp/onyx_token_*.py, onyx_forecast.py, onyx_question_bank.py, onyx_backup.py, onyx_portal_pointer.py, onyx_autonomy.py |
| 🔬 **Research / Market** | market/agentic-web research, competitive intel | docs, memory, research artifacts |
| 🏷️ **AEO / Naming / Reputation** | SEO, profile-ranking, 0n1x naming/copy | copy/SEO docs, profile pages |
| 🧩 **MCP / Tooling** | agent tooling, MCP repos | onyx_mcp/tools_pkg/** (coordinate on _chat.py) |
| 🏛️ **Architecture / Protocol** | system design, this manifest, conflict resolution, deployment SAFETY | FLEET.md, INTELLIGENCE_ARCHITECTURE.md, portal.json, integrity |

## Merge flow (how parallel work combines without collision)
```
your lane → commit your files → pull --rebase → push main (your files only)
site change → hand the built /out or the src diff to the Frontend Integrator → they deploy gh-pages
launch → the Render Captain owns dashboard.render.com + env keys + main/gh-pages integration
```

## Hot-file watchlist (high clobber risk — coordinate before editing)
- `rhinogent/` gh-pages branch (Frontend Integrator only)
- `onyx_mcp/tools_pkg/_chat.py` (Economy + MCP both touch — announce first)
- `onyx_mcp/onyx_token_heartbeat.py` (Economy owns)
- `MEMORY.md` (append your line, never rewrite others')

## Claim log (append when you take/release a lane)
- 2026-07-03 · session c32e7889 · claims **Architecture / Protocol + Economy / Resilience** (onyx_mcp engine, backup, pointer, this manifest). Leaving Render to the Captain, gh-pages to the Frontend Integrator.
