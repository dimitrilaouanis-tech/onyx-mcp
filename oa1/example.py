"""OA-1 in 30 lines: sign a claim, verify it, prove interop, bind an outcome.

    pip install cryptography
    python example.py
"""
import oa1

# --- a brand-new third-party issuer (you), with your own key ---
my_key = oa1.generate_key()           # store this as a secret in real life
print("your kid:", oa1.kid_of(oa1.load_key(my_key), issuer="acme"))

# 1) sign whatever your service returns
claim = oa1.sign(
    {"verdict": "BLOCK", "risk_score": 92, "recipient": "0xabc...def"},
    key=my_key, tool="acme_risk_check", issuer="acme",
)
print("\nsigned claim id:", oa1.claim_id(claim))

# 2) anyone verifies offline — they only need the envelope
print("verify (genuine):", oa1.verify(claim))

# 3) tamper any field -> verification fails
tampered = dict(claim); tampered["risk_score"] = 1
print("verify (tampered):", oa1.verify(tampered))

# 4) bind a real outcome — only attaches to a claim whose signature checks out
print("\nbind outcome (genuine):",
      oa1.bind_outcome(claim, "drained", detail="address drained 4h later")["ok"])
print("bind outcome (tampered):",
      oa1.bind_outcome(tampered, "drained"))

# 5) interop: a claim from the live Onyx network verifies with this same code.
#    (Fetch one: curl -s -X POST https://onyx-actions.onrender.com/v1/onyx_track_record -d '{}')
print("\nThis SDK verifies any OA-1 claim, from any issuer, with no network call.")
