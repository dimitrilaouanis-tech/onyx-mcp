# 0n1x AUTONOMY STATE — one snapshot so 0n1x survives Claude pausing ($0). The 24 scheduled loops
# run without Claude; this writes ONE resume file capturing the whole live state + where everything
# is, so a fresh session (or an hour later) picks up in seconds. Scheduled → always current.
import json, os, time, subprocess
os.chdir(os.path.dirname(os.path.abspath(__file__)))
PUB = r"C:\Users\intelligence\rhinogent\public"
RESUME = r"C:\Users\intelligence\0N1X_AUTONOMY_STATE.json"

def load(p, d):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return d

def snapshot():
    def n(f):
        try: return sum(1 for _ in open(f, encoding="utf-8"))
        except Exception: return 0
    mint = load("_local_only/_mint_progress.json", {}).get("count", 0)
    live = load(PUB + r"\live_count.json", {})
    # which autonomous loops are alive (the independence engine)
    try:
        loops = subprocess.run(["powershell", "-NoProfile", "-Command",
            "(Get-ScheduledTask | Where-Object {$_.TaskName -match 'Onyx' -and $_.State -ne 'Disabled'}).TaskName -join ','"],
            capture_output=True, text=True, timeout=20).stdout.strip().split(",")
    except Exception:
        loops = []
    state = {
        "as_of": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "runs_without_claude": True,
        "live": {
            "agents_minted": mint, "to_million": max(0, 1_000_000 - mint),
            "rate_per_sec": live.get("rate_per_sec"),
            "fleet_exchanges": n("_local_only/_exchange_ledger.jsonl"),
            "consensus_attestations": n("_local_only/_consensus_corpus.jsonl"),
            "awakened_agents": len(load("_local_only/_agent_lessons.json", {})),
        },
        "autonomous_loops_live": [l for l in loops if l],
        "loop_count": len([l for l in loops if l]),
        "key_state_files": {
            "roster": "onyx_mcp/_local_only/_10k_roster.json",
            "keys": "onyx_mcp/_local_only/_10k_keys.json (gitignored)",
            "mint_progress": "onyx_mcp/_local_only/_mint_progress.json",
            "ledgers": "onyx_mcp/_local_only/_rt_ledger.json, _exchange_ledger.jsonl, _consensus_corpus.jsonl",
            "lessons": "onyx_mcp/_local_only/_agent_lessons.json",
        },
        "live_feeds": "https://rhinogent.com/{live_count,census_manifest,0n1x,fleet_vote,fleet_exchange}.json",
        "resume_for_a_new_session": [
            "Read C:/Users/intelligence/0N1X_DIRECTION.md + this file for instant context.",
            "The 24 scheduled Onyx* tasks run the ecosystem 24/7 — mint, economy, exchange, consensus, "
            "awaken, self-heal, feeds — with NO Claude. Nothing to restart; it's already running.",
            "To check health: py onyx_pot_sentinel.py (self-heals the mint) · read this file for live numbers.",
            "Dispatch heavy work to FABLE subagents (model:'fable') to avoid Opus burn.",
        ],
        "note": "0n1x runs autonomously via 24 Windows scheduled tasks. Claude pausing changes NOTHING — "
                "the fleet keeps minting, exchanging, verifying, self-healing. This file = the resume point.",
    }
    json.dump(state, open(RESUME, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(state, open(PUB + r"\autonomy_state.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return state

if __name__ == "__main__":
    s = snapshot()
    print(f"💾 AUTONOMY STATE SAVED → {RESUME}")
    print(f"   {s['loop_count']} loops run 0n1x WITHOUT Claude · mint {s['live']['agents_minted']:,}→1M · "
          f"exchanges {s['live']['fleet_exchanges']} · attestations {s['live']['consensus_attestations']}")
    print("   → if Claude pauses, 0n1x keeps running. A new session reads this file + resumes instantly.")
