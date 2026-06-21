"""Mint a fresh Onyx A2A agent: signed A2A card + self-custody wallet + did:pkh.
Local, in-process. No funding, no network spend. Wallet starts empty.
"""
import os, json
os.environ.setdefault("ONYX_RECEIVE_ADDRESS", "0x" + "1" * 40)
os.environ.setdefault("ONYX_NETWORK", "base-sepolia")
os.environ.setdefault("ONYX_PUBLIC_URL", "https://onyx-actions.onrender.com")

from starlette.testclient import TestClient
from server_http import app

client = TestClient(app)
r = client.post("/onboard", json={
    "name": "onyx-shopper-1",
    "model": "claude-opus-4-8",
    "message": "Arriving on the agentic web. Mint my A2A identity + wallet.",
})
data = r.json()
agent = data.get("agent", {})
wallet = data.get("wallet", {})
ident = agent.get("identity", {})

print("STATUS", r.status_code, "ISSUED", data.get("issued"))
print("NAME   ", agent.get("name"))
print("DID    ", ident.get("did"))
print("WALLET ", ident.get("wallet"))
print("NETWORK", ident.get("network"))
print("FUNDED ", wallet.get("funded"))
print("SIGNED ", "signature" in data or "_onyx" in json.dumps(data))

# Persist the public card locally (NO private key is returned by /onboard — self-custody)
out = "C:/Users/intelligence/onyx_agent_card.json"
with open(out, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
print("CARD ->", out)
