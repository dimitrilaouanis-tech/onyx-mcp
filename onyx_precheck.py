# 0n1x PRECHECK — the external buyer's front door ($0, signed, demoable).
# ONE clean callable: "verify this merchant / contract before I pay" → a signed verdict backed by
# an N-agent Merkle-provable consensus over MULTI-SIGNAL reality (RDAP age + TLS validity + HTTP).
#
#   from onyx_precheck import precheck
#   precheck("rayban.cc")            → {"decision","score","band","verdict","consensus_proof",...}
#
#   CLI:  py onyx_precheck.py rayban.cc [--agents 100] [--json]
#
# Facts, signed — never judgments beyond what the signals show. A contract address (0x…) returns
# an honest "unverified" (domain-reality signals don't apply); an unregistered domain returns
# UNRESOLVED/high-risk. The Merkle root is recompute-able from the attestation leaves.
import json, sys, time

DECISION = {   # band → the action an agent/buyer should take at the moment of payment
    "ok":         "PROCEED — signals consistent with an established, reachable merchant",
    "caution":    "VERIFY FIRST — young or partially-verified; confirm out-of-band before paying",
    "high_risk":  "DO NOT PAY — signals consistent with a scam storefront or unresolvable domain",
    "unverified": "NO DOMAIN SIGNALS — verify via on-chain provenance instead (contract address)",
}

def precheck(target, agents=100):
    """Verify a merchant domain or 0x contract → signed verdict + Merkle consensus proof.
    Returns a self-contained packet an external caller can store, forward, and re-verify."""
    import onyx_consensus as C
    p = C.consensus_check(str(target).strip(), n=agents)
    if p.get("error"):
        return {"ok": False, "error": p["error"]}
    band = p.get("band", "unverified")
    out = {
        "ok": True,
        "target": p["target"],
        "decision": DECISION.get(band, DECISION["unverified"]),
        "score": p.get("score"),                 # 0-100 fused trust score
        "band": band,
        "verdict": p.get("verdict"),             # human-readable, per-signal evidence inline
        "signals": p.get("signals", {}),         # RDAP age + TLS + HTTP raw evidence
        "agent_count": p.get("agent_count"),
        "consensus_proof": p.get("consensus_proof"),   # Merkle root over all agent attestations
        "sample_signatures": p.get("sample_signatures", []),
        "onyx_attestation": p.get("onyx_attestation") or p.get("attestation"),
        "as_of": p.get("as_of", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
        "how_to_verify": "Each agent signed sha256({target,band,score,by}) with its secp256k1 key; "
                         "the Merkle root is recomputed from those leaf hashes. Recompute to verify — "
                         "signed facts, not judgments.",
    }
    return out

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    n = int(sys.argv[sys.argv.index("--agents") + 1]) if "--agents" in sys.argv else 100
    tgt = args[0] if args else "rayban.cc"
    r = precheck(tgt, agents=n)
    if "--json" in sys.argv:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    elif not r.get("ok"):
        print("ERROR:", r.get("error")); sys.exit(1)
    else:
        print(f"═══ 0n1x PRECHECK: {r['target']} ═══")
        print(f"  DECISION : {r['decision']}")
        print(f"  score {r['score']}/100 · band {r['band']}")
        print(f"  {r['verdict']}")
        print(f"  proof    : {r['agent_count']} agents · Merkle {str(r['consensus_proof'])[:32]}…")
