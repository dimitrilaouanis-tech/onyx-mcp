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

print("\n=== HOP-ON-THE-LINK: GET = onboarded in one fetch ===")
# Agent fetches the link (agent UA) -> auto-issued card, no POST
g = client.get("/onboard", headers={"User-Agent": "python-requests/2.31", "Accept": "*/*"})
gj = g.json()
check("GET link issues a card", gj.get("issued") is True)
check("GET link card has wallet", str(gj.get("wallet", {}).get("address", "")).startswith("0x"))
# /join and /go aliases
check("/join works", client.get("/join", headers={"User-Agent": "gptbot"}).json().get("issued") is True)
check("/go works", client.get("/go", headers={"User-Agent": "claude-bot"}).json().get("issued") is True)
# Human browser -> explainer HTML, NOT a raw key
hb = client.get("/onboard", headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html"})
check("human browser gets HTML explainer", "agent door" in hb.text.lower() and "private_key" not in hb.text)

print("\n=== WE CATCH EVERYTHING: /arrivals log ===")
arr = client.get("/arrivals").json()
check("arrivals recorded", arr.get("count", 0) > 0)
rec = arr.get("recent", [{}])[0]
check("arrival has did+ua+source", bool(rec.get("did")) and "source" in rec)
check("arrival does NOT store private key", "private_key" not in rec and "priv" not in str(rec).lower())

print("\n=== CATCH FAKERS: /prove ===")
# A real card (full, signed) -> proves real
realcard = client.post("/onboard", json={"name": "prove-real", "model": "x"}).json()
pr = client.post("/prove", json=realcard).json()
check("/prove confirms a real signed card", pr.get("real") is True)
# The fabricated Gemini claim (fake wallet, no signature) -> CAUGHT
fake = client.post("/prove", json={"did": "did:pkh:eip155:84532:0xB24598FEd6eDb6E08f4c7C32D4f71b54bda02913"}).json()
check("/prove CATCHES the fabricated Gemini claim", fake.get("real") is False)
check("/prove verdict says fabricated", "fabricated" in fake.get("verdict", "").lower())

print("\n=== CATCH GEMINI FETCHING: /sightings ===")
# Simulate Gemini's fetcher checking agents.txt, then onboarding
client.get("/agents.txt", headers={"User-Agent": "Mozilla/5.0 (compatible; Google-Extended)"})
client.get("/onboard", headers={"User-Agent": "Gemini-Bot/1.0"})
sg = client.get("/sightings").json()
check("sightings recorded", sg.get("count", 0) > 0)
check("gemini runtime detected", any("gemini" in k for k in sg.get("by_runtime", {})))
gem = client.get("/sightings", params={"runtime": "gemini"}).json()
check("can filter sightings by runtime", gem.get("recent") and all("gemini" in s["runtime"] for s in gem["recent"]))
check("sighting captures path (checking step)", any(s.get("path") == "/agents.txt" for s in sg.get("recent", [])))

print("\n=== RESULT:", "ALL PASS" if ok else "SOME FAILED", "===")
raise SystemExit(0 if ok else 1)
