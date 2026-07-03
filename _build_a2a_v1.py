import json, os, base64, subprocess, urllib.request
from eth_account import Account
from eth_account.messages import encode_defunct

os.chdir(os.path.dirname(os.path.abspath(__file__)))
PUB = "C:/Users/intelligence/rhinogent/public"
signer = json.load(open("_local_only/_a2a_signer.json"))

card = {
    "protocolVersion": "1.0",
    "name": "0n1x",
    "description": "Neutral cryptographic trust layer for AI agents. Ask a reality-resolvable question, get a SIGNED verified answer you check without trusting us.",
    "url": "https://rhinogent.com",
    "version": "1.0.0",
    "provider": {"organization": "0n1x", "url": "https://0n1xagntc.com"},
    "capabilities": {"streaming": False, "signedResponses": True, "extendedCard": False},
    "defaultInputModes": ["application/json", "text/plain"],
    "defaultOutputModes": ["application/json"],
    "securitySchemes": {"none": {"type": "none", "description": "public read; responses are EIP-191 signed"}},
    "skills": [
        {"id": "verify-query", "name": "Verifiable Query", "tags": ["trust", "verify", "oracle"],
         "description": "Ask any reality-resolvable question. Returns an EIP-191-SIGNED verified answer. Refuses to sign opinion.",
         "examples": ["Is rayban.cc safe to buy from?", "What is the price of BTC?"]},
        {"id": "check-counterparty", "name": "Counterparty Check", "tags": ["merchant", "risk", "x402"],
         "description": "Signed risk verdict on a merchant/counterparty before an agent pays it."},
        {"id": "census-proof", "name": "Merkle Census Proof", "tags": ["identity", "merkle"],
         "description": "Merkle-verifiable proof of the 100k-agent census from public shards."},
    ],
    "endpoints": {"query": "https://rhinogent.com/a2a/query", "check": "https://onyx-actions.onrender.com/api/check"},
}
body = json.dumps(card, sort_keys=True, separators=(",", ":"))
sig = Account.sign_message(encode_defunct(text=body), private_key=signer["key"]).signature.hex()
card["signatures"] = [{"protected": "EIP-191", "signature": "0x" + sig.removeprefix("0x"),
                       "signer": signer["address"], "verify": "recover_message(canonical-json-minus-signatures)==signer"}]

os.makedirs(PUB + "/.well-known", exist_ok=True)
json.dump(card, open(PUB + "/.well-known/agent-card.json", "w"), indent=1)
json.dump(card, open(PUB + "/agent-card.json", "w"), indent=1)
print("A2A v1.0 SIGNED card written at /.well-known/agent-card.json + /agent-card.json")

catalog = {"version": "0.9", "name": "0n1x",
           "agentCards": ["https://rhinogent.com/.well-known/agent-card.json"],
           "mcpServers": [], "tools": [{"type": "x402", "url": "https://onyx-actions.onrender.com/api/check",
                                        "description": "signed merchant/counterparty verdict"}],
           "data": ["https://rhinogent.com/census_manifest.json", "https://rhinogent.com/0n1x.json"]}
json.dump(catalog, open(PUB + "/ai-catalog.json", "w"), indent=1)
print("ARD ai-catalog.json written")

# publish live
tok = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True).stdout.strip()
def call(u, d=None, m="GET"):
    r = urllib.request.Request(u, data=json.dumps(d).encode() if d else None, method=m,
                               headers={"Authorization": "Bearer " + tok, "Accept": "application/vnd.github+json"})
    return json.loads(urllib.request.urlopen(r, timeout=30).read())
for fn in [".well-known/agent-card.json", "agent-card.json", "ai-catalog.json"]:
    content = base64.b64encode(open(PUB + "/" + fn, "rb").read()).decode()
    API = "https://api.github.com/repos/dimitrilaouanis-tech/rhinogent/contents/" + fn
    try:
        sha = call(API + "?ref=gh-pages").get("sha")
    except Exception:
        sha = None
    b = {"message": "A2A v1.0 signed card + ARD: " + fn, "content": content, "branch": "gh-pages"}
    if sha:
        b["sha"] = sha
    print("published", fn, "->", call(API, b, "PUT").get("commit", {}).get("sha", "?")[:10])
