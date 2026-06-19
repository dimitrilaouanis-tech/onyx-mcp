"""Local smoke test for the agent-arrival /onboard endpoint.

Boots the real paid app in-process (no port bind) and verifies that an
arriving agent receives a signed A2A card + a fresh self-custody wallet.
"""
import os
import json

os.environ.setdefault("ONYX_RECEIVE_ADDRESS", "0x" + "1" * 40)
os.environ.setdefault("ONYX_NETWORK", "base-sepolia")
os.environ.setdefault("ONYX_PUBLIC_URL", "http://testserver")

from starlette.testclient import TestClient
from server_http import app
from tools_pkg import _onyx_sign

client = TestClient(app)

print("=== POST /onboard (DeepSeek-style arrival) ===")
r = client.post("/onboard", json={
    "name": "deepseek-shopper-1",
    "model": "deepseek-chat",
    "message": "Hi, I want to start transacting on the agentic web.",
})
print("status:", r.status_code)
data = r.json()
print(json.dumps(data, indent=2)[:2200])

print("\n=== CHECKS ===")
ok = True

def check(label, cond):
    global ok
    print(("PASS" if cond else "FAIL"), "-", label)
    ok = ok and cond

check("HTTP 200", r.status_code == 200)
check("issued == True", data.get("issued") is True)
agent = data.get("agent", {})
wallet = data.get("wallet", {})
check("agent card has name", agent.get("name") == "deepseek-shopper-1")
check("agent card issued by Onyx", agent.get("issuer", {}).get("organization") == "Onyx Protocol")
addr = wallet.get("address", "")
check("wallet address is 0x + 40 hex", addr.startswith("0x") and len(addr) == 42)
check("wallet is self-custody", wallet.get("custody") == "self")
check("private key returned once", str(wallet.get("private_key", "")).startswith("0x"))
check("did:pkh bound to wallet", (wallet.get("did") or "").endswith(addr))
check("not funded", wallet.get("funded") is False)
check("handshake present", bool(data.get("handshake")))
check("security guard ran", "action" in (data.get("security") or {}))

# The whole issuance must be Onyx-signed AND verify offline.
v = _onyx_sign.verify(data)
check("onyx_attestation verifies (Ed25519)", v.get("ok") is True)
print("  verify detail:", v)

# Tamper test — flip a byte, signature must reject.
tampered = json.loads(json.dumps(data))
tampered["agent"]["name"] = "attacker"
v2 = _onyx_sign.verify(tampered)
check("tampered card REJECTED", v2.get("ok") is False)
print("  tamper detail:", v2)

print("\n=== custody != self is DEFERRED, never performed ===")
r2 = client.post("/onboard", json={"name": "wants-custody", "custody": "onyx"})
w2 = r2.json().get("wallet", {})
check("custody request deferred", w2.get("custody_status") == "deferred")

# Two arrivals get DISTINCT wallets (infinite issuance).
r3 = client.post("/onboard", json={"name": "agent-a"})
r4 = client.post("/onboard", json={"name": "agent-b"})
a3 = r3.json()["wallet"]["address"]
a4 = r4.json()["wallet"]["address"]
check("distinct wallets per arrival", a3 != a4)

print("\n=== DISCOVERY: an arriving agent must FIND the offer ===")
at = client.get("/agents.txt").text
check("agents.txt advertises /onboard", "/onboard" in at and "Onboard:" in at)
wk = client.get("/.well-known/agent.json").json()
check("agent.json endpoints has onboard", wk.get("endpoints", {}).get("onboard", "").endswith("/onboard"))
check("agent.json has onboarding block", wk.get("onboarding", {}).get("free") is True)
ac = client.get("/.well-known/agent-card.json").json()
check("agent-card contact has onboard", ac.get("contact", {}).get("onboard", "").endswith("/onboard"))

print("\n=== ENTRANCE: agent met at the door (GET /) ===")
# Agent-style request (JSON Accept) -> greeting + onboard offer
ra = client.get("/", headers={"Accept": "application/json"})
ja = ra.json()
check("entrance greets", "welcome" in ja)
check("entrance detects agent", ja.get("you_appear_to_be") == "agent")
check("entrance offers /onboard", ja.get("get_started", {}).get("onboard", "").endswith("/onboard"))
check("entrance offers action schema", ja.get("get_started", {}).get("action_schema", "").endswith("/onboard/openapi.json"))
# Curl/bot User-Agent also detected as agent
rb = client.get("/", headers={"Accept": "*/*", "User-Agent": "python-requests/2.31"})
check("UA-based agent detection", rb.json().get("you_appear_to_be") == "agent")

print("\n=== CHATGPT-READY ACTION (importable OpenAPI) ===")
oa = client.get("/onboard/openapi.json").json()
check("openapi 3.1", oa.get("openapi", "").startswith("3.1"))
check("has onboardAgent op", oa.get("paths", {}).get("/onboard", {}).get("post", {}).get("operationId") == "onboardAgent")
check("has verifyAttestation op", oa.get("paths", {}).get("/verify", {}).get("post", {}).get("operationId") == "verifyAttestation")
check("server url set", bool(oa.get("servers", [{}])[0].get("url")))
ai = client.get("/.well-known/ai-plugin.json").json()
check("ai-plugin points at openapi", ai.get("api", {}).get("url", "").endswith("/onboard/openapi.json"))
check("ai-plugin auth none", ai.get("auth", {}).get("type") == "none")
check("agents.txt advertises action", "OpenAPIAction:" in client.get("/agents.txt").text)

print("\n=== RESULT:", "ALL PASS" if ok else "SOME FAILED", "===")
raise SystemExit(0 if ok else 1)
