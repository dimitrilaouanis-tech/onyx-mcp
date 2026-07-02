"""onyx_portal_local.py — run the 0n1x PORTAL locally with YOUR OWN API key.

The exact same /v1/chat the cloud will serve, on your machine — full natural conversation with
the network, every fact from a signed ecosystem tool. Use it to test the portal TODAY without
waiting for the Render deploy.

Setup (eyes-open — the key is yours, set it yourself, never paste it in chat):
  1.  set your key in THIS shell only:   $env:ANTHROPIC_API_KEY = "sk-ant-..."   (PowerShell)
  2.  py onyx_portal_local.py            -> portal on http://localhost:8402
  3.  talk to it:
      curl -s -X POST localhost:8402/v1/chat -H "content-type: application/json" ^
           -d "{\"message\": \"is stripe.com legit?\"}"

The web terminal can point here via a tunnel later; this runner is the fastest full test.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from tools_pkg import _chat

app = FastAPI(title="0n1x Portal (local)")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
_chat.register(app)


@app.get("/health")
def health():
    return {"ok": True, "portal": "armed" if os.environ.get("ANTHROPIC_API_KEY") else "no key set"}


if __name__ == "__main__":
    import uvicorn
    armed = bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())
    print(f"0n1x PORTAL local -> http://localhost:8402  | key: {'ARMED' if armed else 'NOT SET (set ANTHROPIC_API_KEY first)'}")
    uvicorn.run(app, host="127.0.0.1", port=8402, log_level="warning")
