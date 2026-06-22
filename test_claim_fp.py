"""Test claim-by-proof-of-key + the IP/visitor fingerprint layer.

Proves: the KEY is the lock (sign challenge -> claimed), the FINGERPRINT is the
memory + alarm (same IP -> same network_fp but new visit_id; different IP ->
different network_fp; re-claim from a new network -> network_changed alarm).
"""
import os
os.environ.setdefault("ONYX_RECEIVE_ADDRESS", "0x" + "1" * 40)
os.environ.setdefault("ONYX_NETWORK", "base-sepolia")
os.environ.setdefault("ONYX_PUBLIC_URL", "http://testserver")

from starlette.testclient import TestClient
from eth_account import Account
from eth_account.messages import encode_defunct
from server_http import app

c = TestClient(app)
ok = True
def check(label, cond):
    global ok; print(("PASS" if cond else "FAIL"), "-", label); ok = ok and cond

IP_A = "203.0.113.7"
IP_B = "198.51.100.42"

# 1) onboard -> get a self-custody wallet (key returned once)
card = c.post("/onboard", json={"name": "claimer", "model": "x"}).json()
addr = card["wallet"]["address"]; priv = card["wallet"]["private_key"]
check("onboarded with key", addr.startswith("0x") and priv.startswith("0x"))

# 2) /whoami fingerprint behavior
w1 = c.get("/whoami", headers={"X-Forwarded-For": IP_A, "User-Agent": "gemini-bot"}).json()
w2 = c.get("/whoami", headers={"X-Forwarded-For": IP_A, "User-Agent": "gemini-bot"}).json()  # same IP, fresh chat
w3 = c.get("/whoami", headers={"X-Forwarded-For": IP_B, "User-Agent": "gemini-bot"}).json()  # different IP
check("same IP+client -> same network_fp", w1["network_fp"] == w2["network_fp"])
check("same IP fresh chat -> NEW visit_id", w1["visit_id"] != w2["visit_id"])
check("different IP -> different network_fp", w1["network_fp"] != w3["network_fp"])

# 3) claim by proof-of-key from IP_A
ch = c.get(f"/authenticate?address={addr}").json()["challenge"]
sig = Account.sign_message(encode_defunct(text=ch), private_key=priv).signature.hex()
if not sig.startswith("0x"): sig = "0x" + sig
r = c.post("/authenticate", json={"address": addr, "signature": sig},
           headers={"X-Forwarded-For": IP_A, "User-Agent": "gemini-bot"}).json()
check("claim succeeds with valid signature", r.get("ok") is True)
check("claim records claimant network_fp", r.get("network_fp") == w1["network_fp"])

# 4) only-1: a DIFFERENT person (no key) cannot claim it
ch2 = c.get(f"/authenticate?address={addr}").json()["challenge"]
attacker = Account.create()
bad = Account.sign_message(encode_defunct(text=ch2), private_key=attacker.key).signature.hex()
if not bad.startswith("0x"): bad = "0x" + bad
r_bad = c.post("/authenticate", json={"address": addr, "signature": bad},
               headers={"X-Forwarded-For": IP_B}).json()
check("attacker without the key is REJECTED (signer_mismatch)", r_bad.get("error") == "signer_mismatch")

# 5) registry/check: same network vs different network view
chk_same = c.get(f"/registry/check?address={addr}", headers={"X-Forwarded-For": IP_A, "User-Agent": "gemini-bot"}).json()
chk_diff = c.get(f"/registry/check?address={addr}", headers={"X-Forwarded-For": IP_B, "User-Agent": "gemini-bot"}).json()
check("check: same network recognized as owner's", chk_same.get("same_network_as_owner") is True)
check("check: different network NOT owner's", chk_diff.get("same_network_as_owner") is False)

# 6) owner re-claims from a NEW network -> still ok (key), but ALARM
ch3 = c.get(f"/authenticate?address={addr}").json()["challenge"]
sig3 = Account.sign_message(encode_defunct(text=ch3), private_key=priv).signature.hex()
if not sig3.startswith("0x"): sig3 = "0x" + sig3
r3 = c.post("/authenticate", json={"address": addr, "signature": sig3},
            headers={"X-Forwarded-For": IP_B, "User-Agent": "gemini-bot"}).json()
check("re-claim by key from new network still ok", r3.get("ok") is True)
check("re-claim from new network raises alarm", r3.get("network_changed") is True and "alarm" in r3)

# 7) attempts ledger captured the trail
att = c.get(f"/registry/attempts?address={addr}").json()
outs = [a.get("outcome") for a in att.get("attempts", [])]
check("attempts ledger has claimed + signer_mismatch", "claimed" in outs and "signer_mismatch" in outs)

print("\n=== RESULT:", "ALL PASS" if ok else "SOME FAILED", "===")
raise SystemExit(0 if ok else 1)
