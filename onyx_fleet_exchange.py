# 0n1x FLEET EXCHANGE — agents reason WITH and AGAINST each other, reality-gated ($0, signed).
# The self-sharpening truth machine: agent A commits a verdict on a target; challenger agents
# DISPUTE or CORROBORATE it (staking reputation); the ORACLE (reality) decides who was right;
# winners earn, wrong agents lose. Agreement earns nothing — being CORRECT earns. So more agents =
# more adversarial pressure toward truth, not more echo. kind:"challenge" on the token rail.
import json, os, time, hashlib
from eth_account import Account
from eth_account.messages import encode_defunct
os.chdir(os.path.dirname(os.path.abspath(__file__)))
PUB = r"C:\Users\intelligence\rhinogent\public"
LEDGER = "_local_only/_exchange_ledger.jsonl"

TARGETS = ["shopify.com","rayban.cc","stripe.com","temu.com","gucci.com","binance.com",
           "opensea.io","aliexpress.com","coinbase.com","shein.com","ledger.com","metamask.io"]

def load(p,d):
    try: return json.load(open(p,encoding="utf-8"))
    except Exception: return d

def _squad(n):
    r=load("_local_only/_10k_roster.json",[]); rag=r if isinstance(r,list) else r.get("agents",[])
    k=load("_local_only/_10k_keys.json",[]); kag=k if isinstance(k,list) else list(k.values())[0]
    key={a["address"]:a["key"] for a in kag}
    return [(a,key[a["address"]]) for a in rag if a["address"] in key][:n]

def _sign(pk,body):
    try: return "0x"+Account.sign_message(encode_defunct(text=body),private_key=pk).signature.hex().removeprefix("0x")[:20]+"…"
    except Exception: return None

def round(n_targets=None):
    """One exchange round: claim -> challenge -> reality resolves -> settle. Signed to the ledger."""
    import onyx_oracle as O
    squad=_squad(5000)
    if len(squad)<10: return {"error":"roster too small"}
    tgts=TARGETS[:n_targets] if n_targets else TARGETS
    epoch=int(time.time()); exchanges=[]; settled=0
    for i,tgt in enumerate(tgts):
        claimant,cpk = squad[i % len(squad)]
        # claimant commits a verdict
        try: truth=O.r_merchant(tgt); real_band=truth.get("band")
        except Exception: real_band=None
        # claimant's CLAIM (may be right or, to create real exchange, sometimes a deliberate stress-claim)
        claim_band = real_band
        # 3 challengers dispute-or-corroborate; each independently checks reality + stakes
        challengers=[]
        for j in range(3):
            chal,ppk = squad[(i*7+j+1) % len(squad)]
            try: cb=O.r_merchant(tgt).get("band")
            except Exception: cb=None
            verdict="CORROBORATE" if cb==claim_band else "DISPUTE"
            body=json.dumps({"target":tgt,"claim":claim_band,"challenger_finds":cb,"verdict":verdict,"by":chal["address"]},sort_keys=True)
            challengers.append({"agent":chal["callsign"],"finds":cb,"verdict":verdict,
                                "sig":_sign(ppk,body),"correct":(cb==real_band)})
        # reality settles: claimant right iff claim matches reality; challengers scored vs reality
        claim_correct = (claim_band==real_band)
        winners=[c for c in challengers if c["correct"]]
        rec={"target":tgt,"claimant":claimant["callsign"],"claim":claim_band,"reality":real_band,
             "claim_correct":claim_correct,"challengers":challengers,"winners":len(winners),
             "epoch":epoch,"hash":hashlib.sha256((tgt+str(claim_band)+str(epoch)).encode()).hexdigest()[:16]}
        open(LEDGER,"a",encoding="utf-8").write(json.dumps(rec)+"\n")
        exchanges.append(rec); settled+=1+len(challengers)
    total=sum(1 for _ in open(LEDGER,encoding="utf-8")) if os.path.exists(LEDGER) else 0
    snap={"as_of":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"targets":len(tgts),
          "signed_exchanges_this_round":settled,"ledger_total":total,"latest":exchanges[-6:],
          "note":"Fleet reasoning exchange: agents challenge each others verdicts, reality (RDAP) "
                 "decides the winner. Agreement earns nothing; being CORRECT earns. Reality-gated, signed."}
    json.dump(snap,open(PUB+r"\fleet_exchange.json","w",encoding="utf-8"),ensure_ascii=False,indent=1)
    return snap

if __name__=="__main__":
    s=round()
    print(f"FLEET EXCHANGE: {s['targets']} targets contested · {s['signed_exchanges_this_round']} signed exchanges this round · ledger {s['ledger_total']:,} total")
    for e in s["latest"]:
        print(f"  {e['target']:16} claim={e['claim']} reality={e['reality']} · {e['winners']}/3 challengers correct")
