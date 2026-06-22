# ⚠️ SHARED REPO — MULTIPLE CLAUDE SESSIONS EDIT THIS CONCURRENTLY

This repo (`onyx_mcp`, branch `main` → Render auto-deploy) is worked by **several
Claude Code sister sessions at the same time, in the same working directory.**

**Confirmed live 2026-06-22:** `onyx_paid_mcp/app.py` (and `MEMORY.md`) were edited
by one session *while another had them open* → Edit failed "file content has changed".
We've been lucky it converged. It will not always.

## Rules before you touch shared files (especially `app.py`)

1. `git pull --rebase origin main` BEFORE editing — or commit-first then rebase.
2. `git add <specific files>` only — **never `git add -A`** (avoids committing a
   sister's in-flight edits or runtime artifacts like `_claimed.json`,
   `_observation_log.jsonl`, `_reserved.json` — those are ephemeral, do not commit).
3. Expect `M onyx_paid_mcp/app.py` from a sister in the working tree — **leave it**, it's theirs.
4. **Re-read the exact block right before each Edit** — line numbers drift as others add routes.
5. Prefer adding **new modules under `tools_pkg/`** over piling more into `app.py`.
6. If you must edit `app.py`: keep it small, push immediately, and note big route
   additions in `MEMORY.md`.
7. Grep SMS-lane terms before every push (see `feedback_onyx_sms_wall`).

## Who's building what (as of 2026-06-22)
- **Onboarding / identity / continuity** — `/onboard`, `/whoami`, `/registry/*`,
  `_claim_registry.py`, `_fingerprint.py`, `/arrivals`, `/sightings`, `/watch`, `/prove`.
- **Verified registry** — `agent_verify.py`, `agent_registry.py` (hollow-detector).
- **Observation network** — `_observations.py`, `_pulse.py`, `_verified.py`, `/history /timeline /proof /verified`.
- **Card signing** — `_onyx_sign.sign_card()/verify_card()`.

Coordinate on `app.py` route additions so we don't collide.
