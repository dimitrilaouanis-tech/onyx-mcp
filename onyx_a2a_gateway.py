# 0n1x A2A VERIFIABLE QUERY GATEWAY — THE DOOR (trustless ingress).
# The pinnacle: any EXTERNAL agent can knock, ask a question, and get back a SIGNED,
# reality-verified answer it can cryptographically check — no trust, no account, no context.
# This is the A2A bridge + the north star: an agent asks 0n1x "is this safe / what is X",
# 0n1x answers grounded in REALITY (oracle) and SIGNS it, the asker verifies the signature.
# Verify-don't-trust, aimed outward. Register on the live server → real external adoption.
import json, os, time, hashlib
from eth_account import Account
from eth_account.messages import encode_defunct
import onyx_oracle as ORACLE

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# 0n1x signing identity (the network signs its verified answers so any agent can verify them)
def _signer():
    kf = "_local_only/_a2a_signer.json"
    try:
        return json.load(open(kf))["key"]
    except Exception:
        k = Account.create().key.hex()
        os.makedirs("_local_only", exist_ok=True)
        json.dump({"key": k, "address": Account.from_key(k).address}, open(kf, "w"))
        return k


def verified_answer(question: str) -> dict:
    """THE CORE: answer a query grounded in REALITY, then SIGN it. Any agent verifies the sig.
    Resolvable (price/domain/tvl/fx/github) → real answer + verified:true. Otherwise honest:
    verified:false, 'no external ground truth' — 0n1x never signs a claim reality can't back."""
    r = ORACLE.resolve(question)
    ts = round(time.time(), 1)
    if r.get("resolvable"):
        truth = r.get("verdict") or r.get("truth")
        payload = {"q": question, "answer": str(truth), "kind": r["kind"],
                   "source": r.get("source"), "verified": True, "ts": ts}
    else:
        payload = {"q": question, "answer": None, "verified": False,
                   "reason": "no external ground truth — 0n1x only signs reality-verifiable facts", "ts": ts}
    # SIGN it — the whole point. The asker recovers 0n1x's address from the signature.
    body = json.dumps(payload, sort_keys=True)
    key = _signer()
    sig = Account.sign_message(encode_defunct(text=body), private_key=key).signature.hex()
    payload["signed_by"] = Account.from_key(key).address
    payload["signature"] = "0x" + sig.removeprefix("0x")
    payload["verify"] = "recover_message(EIP-191, body=canonical-json-without-signature) == signed_by"
    return payload


def register(app):
    """Mount the door on the live server: POST /a2a/query {question} → signed verified answer."""
    from fastapi import Request

    @app.post("/a2a/query", include_in_schema=True)
    async def a2a_query(req: Request):
        try:
            b = await req.json()
        except Exception:
            b = {}
        q = (b or {}).get("question") or (b or {}).get("q") or ""
        if not q:
            return {"ok": False, "error": "send {question: '...'}"}
        return {"ok": True, **verified_answer(q)}

    @app.get("/a2a/query", include_in_schema=True)
    async def a2a_query_get(question: str = ""):
        if not question:
            return {"ok": False, "error": "?question=..."}
        return {"ok": True, **verified_answer(question)}


if __name__ == "__main__":
    # demo: an external agent knocks, gets a SIGNED verified answer, verifies it itself
    for q in ["Is rayban.cc a safe site to buy from?", "What is the price of BTC?",
              "Is 0n1x the best network ever?"]:
        a = verified_answer(q)
        # the external agent VERIFIES the signature (trustless)
        vbody = json.dumps({k: a[k] for k in a if k not in ("signed_by", "signature", "verify")}, sort_keys=True)
        rec = Account.recover_message(encode_defunct(text=vbody), signature=bytes.fromhex(a["signature"][2:]))
        ok = rec.lower() == a["signed_by"].lower()
        print(f"  Q: {q[:42]:44} → verified={a['verified']} answer={str(a['answer'])[:20]:22} sig-checks={ok}")
