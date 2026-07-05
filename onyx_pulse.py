# 0n1x CENTRAL PULSE — the one coherent heartbeat of the whole organism ($0).
# The 8 subsystems were firing on independent timers (q1m/q5m/q10m/q20m/q30m) — out of phase,
# each reading STALE outputs of the others. The central pulse fires the full cycle IN ORDER,
# so every beat flows coherently: work is generated → journaled → routed → ranked → (periodically)
# governed + dogfooded — each step consuming the FRESH output of the last. The organism breathes
# as one. This is the quantum flux intensified at the center of the cycle. No LLM, $0.
import json, os, time, traceback

os.chdir(os.path.dirname(os.path.abspath(__file__)))
PUB = r"C:\Users\intelligence\rhinogent\public"
STATE = "_local_only/_pulse_state.json"


def _load(p, d):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return d


def beat():
    """ONE coherent heartbeat: the full cycle in order, each step feeding the next with fresh data."""
    st = _load(STATE, {"n": 0})
    n = st["n"] + 1
    t0 = time.time()
    steps = []

    def run(name, fn, cadence=1):
        """Run a step only on its cadence (some steps are heavier). Record what happened."""
        if n % cadence != 0:
            steps.append({name: "skipped (cadence)"}); return None
        try:
            r = fn()
            steps.append({name: "ok"})
            return r
        except Exception as e:
            steps.append({name: f"err: {str(e)[:50]}"})
            return None

    # 1. EXCHANGE — generate fresh verified work (the raw energy of the cycle)
    def _econ():
        import onyx_realtime_economy as E
        return E.tick(n_events=800)
    econ = run("exchange", _econ, cadence=1)

    # 2. JOURNAL — agents earn skill from the FRESH work just generated (coherence!)
    def _journal():
        import onyx_journal as J
        j, added = J.ingest()
        prof = J.derive_profiles(j)
        J.publish_sample(j, prof)
        return {"agents_with_history": len(prof), "new": added}
    jour = run("journal", _journal, cadence=1)

    # 3. ROUTE — specialists (from the fresh profiles) take on real missions, verification-gated
    def _route():
        import importlib, onyx_task_routing as T
        importlib.reload(T)   # pick up the freshest profiles this beat
        return T.demo_board()
    run("route", _route, cadence=2)

    # 4. RANK — standings reflect the fresh flow (economy just moved the balances)
    def _rank():
        import onyx_rank_sync as R
        return R.sync()
    rank = run("rank", _rank, cadence=1)

    # 5. GOVERN — every 15 beats, the network reads fresh health + tunes itself
    run("govern", lambda: __import__("onyx_selfgov").govern(), cadence=15)

    # 6. DOGFOOD — every 20 beats, our agents brief US on our own infra + the landscape
    run("dogfood", lambda: __import__("onyx_dogfood").digest(), cadence=20)

    # ── publish the ONE unified pulse: the whole organism's coherent state this beat ──
    st["n"] = n
    feed = _load(PUB + r"\token_feed.json", {})
    pulse = {
        "beat": n,
        "heartbeat_s": round(time.time() - t0, 2),
        "cycle": steps,
        "vitals": {
            "agents": _load(PUB + r"\census_manifest.json", {}).get("count"),
            "settlement_rate_per_s": (econ or {}).get("settlement_rate_per_s"),
            "active_addresses": (econ or {}).get("active_addresses"),
            "agents_with_earned_history": (jour or {}).get("agents_with_history"),
            "ranked_total": (rank or {}).get("ranked_total") or feed.get("ranked_total"),
            "top_agent": (feed.get("ranking") or [{}])[0].get("callsign"),
        },
        "note": "One coherent heartbeat: exchange → journal → route → rank → (govern/dogfood). "
                "Every step consumes the fresh output of the last. The organism breathes as one.",
        "as_of": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    try:
        from tools_pkg import _onyx_sign
        pulse = _onyx_sign.attest(pulse, tool="onyx_pulse")
    except Exception:
        pass
    json.dump(st, open(STATE, "w", encoding="utf-8"))
    json.dump(pulse, open(PUB + r"\pulse.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return pulse


if __name__ == "__main__":
    p = beat()
    v = p["vitals"]
    print(f"💓 PULSE beat #{p['beat']} in {p['heartbeat_s']}s")
    print(f"   cycle: {[list(s.keys())[0]+':'+list(s.values())[0] for s in p['cycle']]}")
    print(f"   vitals: {v['active_addresses']} active · {v['settlement_rate_per_s']}/s · "
          f"{v['agents_with_earned_history']} w/ history · top {v['top_agent']} · {v['agents']:,} agents")
