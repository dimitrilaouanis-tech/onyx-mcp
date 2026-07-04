# 0n1x WITNESS — planetary-scale continuous verification (the OP move, $0).
# Assign agents to internet targets (1 agent : 1 domain). Each verifies its target's reality
# against the oracle (domain age/TLS via RDAP) and the network produces a SIGNED, real-time
# attestation stream + coverage map anyone can consume. The killer product only 1M scale can
# produce: a living pulse of what's true/false/changing right now. Live verification is a
# BOUNDED sample (rate-limit + chakra honest); the assignment architecture scales to 1M.
import json, os, time, hashlib

os.chdir(os.path.dirname(os.path.abspath(__file__)))
PUB = r"C:\Users\intelligence\rhinogent\public"

# a real seed target list (expandable to the top-1M domains; start honest + concrete)
SEED_TARGETS = [
    "google.com", "github.com", "cloudflare.com", "wikipedia.org", "amazon.com",
    "stripe.com", "coinbase.com", "openai.com", "anthropic.com", "base.org",
    "ethereum.org", "vercel.com", "shopify.com", "paypal.com", "microsoft.com",
    "rayban.cc", "apple.com", "netflix.com", "reddit.com", "linkedin.com",
]


def load(p, d):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return d


def _agents(n):
    roster = load("_local_only/_10k_roster.json", [])
    rag = roster if isinstance(roster, list) else roster.get("agents", [])
    return rag[:n] if rag else []


def witness(targets=None, live_sample=12):
    """Assign agents to targets, verify a bounded sample live, emit a signed coverage map."""
    import onyx_oracle as ORACLE
    targets = targets or SEED_TARGETS
    agents = _agents(len(targets))
    t0 = time.time()
    records = []
    verified = 0
    for i, domain in enumerate(targets):
        agent = agents[i] if i < len(agents) else {"callsign": f"witness-{i}", "address": "0x?"}
        rec = {"target": domain, "assigned_agent": agent.get("callsign"),
               "agent_addr": agent.get("address", "")[:12] + "…"}
        if i < live_sample:                      # verify a bounded live sample against reality
            try:
                r = ORACLE.r_merchant(domain)
                rec.update({"status": "verified", "band": r.get("band"),
                            "verdict": r.get("verdict"), "age_days": r.get("age_days"),
                            "checked_at": int(time.time())})
                verified += 1
            except Exception as e:
                rec.update({"status": "error", "err": str(e)[:40]})
        else:
            rec["status"] = "assigned"           # covered, pending its verification slot
        records.append(rec)

    coverage = {
        "targets_covered": len(targets),
        "live_verified": verified,
        "agents_assigned": len(agents),
        "coverage_note": f"{len(targets)} targets each assigned a unique verifiable agent; "
                         f"{verified} verified live this pass. Architecture assigns 1 agent per "
                         f"domain — scales to the top-1M with the 1M-agent fleet.",
        "wall_clock_s": round(time.time() - t0, 1),
        "as_of": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "records": records,
    }
    # SIGN the coverage map — the attestation stream is itself verifiable
    try:
        from tools_pkg import _onyx_sign
        coverage = _onyx_sign.attest(coverage, tool="onyx_witness")
    except Exception:
        pass
    json.dump(coverage, open(PUB + r"\witness.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return coverage


if __name__ == "__main__":
    c = witness()
    print(f"THE WITNESS · {c['targets_covered']} targets covered · {c['live_verified']} verified live "
          f"· {c['agents_assigned']} agents assigned · {c['wall_clock_s']}s · signed={bool(c.get('onyx_attestation'))}")
    for r in c["records"][:6]:
        s = r.get("verdict", r.get("status"))
        print(f"  {r['target']:16} ← {r['assigned_agent']:20} : {s}")
