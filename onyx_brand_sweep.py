"""Brand sweep — the pilot-closing demo. Run the neutral signed gate across a LIST
of domains for one brand and emit a single report: what an agent would be cleared
to pay vs held, each verdict Ed25519-signed and offline-verifiable.

This is the artifact for a brand-protection call: not "we caught one counterfeit"
(a fluke) but "we swept your brand's domains, signed every verdict, in seconds"
(a product). Honest by design: we report the live FACTS the gate disclosed; we do
NOT assert any domain is a counterfeit — HOLD means the facts warrant a human look.

No spend, no funds, read-only network. Run:
    py onyx_brand_sweep.py "Ray-Ban" rayban.com rayban.cc ray-ban-sale.com
    py onyx_brand_sweep.py            (built-in Ray-Ban demo set)
"""
import json
import sys

from tools_pkg import payment_gate as pg


def sweep(brand, domains):
    rows = []
    for d in domains:
        try:
            r = pg.run(d, brand=brand)
            reasons = r.get("reasons") or [""]
            # surface the most salient reason (brand-similarity / age) over boilerplate
            salient = next((x for x in reasons
                            if any(k in x.lower() for k in
                                   ("similar", "brand", "old", "young", "age", "deviat",
                                    "redirect", "unreachable", "tls"))), reasons[0])
            rows.append({
                "domain": d,
                "clearance": r.get("clearance"),
                "age_days": (r.get("signals") or {}).get("domain_age_days"),
                "tls": (r.get("signals") or {}).get("tls_valid"),
                "reason": salient[:120],
                "signed": bool(r.get("onyx_attestation")),
                "verify_at": (r.get("evidence") or {}).get("verified_status"),
            })
        except Exception as e:
            rows.append({"domain": d, "clearance": "ERROR", "reason": str(e)[:120]})
    return rows


def report(brand, rows):
    held = [r for r in rows if r["clearance"] == "HOLD"]
    review = [r for r in rows if r["clearance"] == "REVIEW"]
    ok = [r for r in rows if r["clearance"] == "PROCEED"]
    signed_n = sum(1 for r in rows if r.get("signed"))
    print("=" * 72)
    print(f" 0n1x BRAND SWEEP  ·  {brand}  ·  {len(rows)} domains, {signed_n} signed verdicts")
    print("=" * 72)
    print(f" {'DOMAIN':28} {'CLEARANCE':10} {'AGE(d)':7} WHY")
    print(" " + "-" * 70)
    order = {"HOLD": 0, "REVIEW": 1, "PROCEED": 2, "ERROR": 3}
    for r in sorted(rows, key=lambda x: order.get(x["clearance"], 9)):
        age = r.get("age_days")
        age = str(age) if age is not None else "-"
        print(f" {r['domain'][:28]:28} {str(r['clearance']):10} {age:7} {r.get('reason','')}")
    print(" " + "-" * 70)
    print(f" SUMMARY: an agent would be HELD on {len(held)}, REVIEW on {len(review)}, "
          f"cleared to PAY {len(ok)}.")
    print(f" Every verdict is Ed25519-signed and re-verifiable offline / at the verify_at URL.")
    print(" Bright line: HOLD = the FACTS warrant a human look; not an assertion of fraud.")
    print("=" * 72)
    return {"brand": brand, "n": len(rows), "hold": len(held),
            "review": len(review), "proceed": len(ok), "signed": signed_n, "rows": rows}


_DEMO = ["rayban.com", "rayban.cc", "ray-ban-sale.com", "raybanoutlet.com",
         "sunglasshut.com"]

if __name__ == "__main__":
    if len(sys.argv) >= 3:
        brand, domains = sys.argv[1], sys.argv[2:]
    else:
        brand, domains = "Ray-Ban", _DEMO
    rows = sweep(brand, domains)
    res = report(brand, rows)
    out = "_brand_sweep_result.json"
    json.dump(res, open(out, "w", encoding="utf-8"), indent=2)
    print(f" wrote {out}")
