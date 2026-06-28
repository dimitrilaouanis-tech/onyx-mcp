"""Know Before You Pay — the consumer-facing scam red-flag check.

The problem, felt by millions TODAY: brand-new fake storefronts pushed through
Instagram/TikTok/Facebook ads drain people before any blocklist catches up. The
scam that gets you is the one that's 6 days old and on nobody's list yet.

This wraps the SAME forensic engine as onyx_merchant_fact_check (domain age,
live TLS, reachability, off-domain redirect, lookalike-name tokens, price
sanity) and translates the raw facts into ONE plain-English verdict a
non-technical person understands instantly:

    LOOKS ESTABLISHED  ·  BE CAREFUL  ·  HIGH RISK — RED FLAGS

HONEST BY DESIGN (this is the moat, not a disclaimer): it is a red-flag check
based on public signals, NOT a guarantee. It catches the PATTERNS scammers use
so a person thinks twice — a smoke detector, not a force field. We never claim
certainty; we show the facts and the reasons, each one verifiable. That honesty
is what makes it official and undeniable, where competitors sell opinions.

Stdlib-only on top of the existing engine. Underscore-prefixed -> not a tool.
"""
from __future__ import annotations

import time

from . import _onyx_sign
from . import _cross_verify

# Suspicious tokens that, combined with a famous brand or a deal-pitch, recur in
# lookalike scam-store registrations. Presence is a flag, never a conviction.
_DEAL_TOKENS = (
    "outlet", "sale", "sales", "discount", "clearance", "official", "store",
    "shop", "online", "cheap", "factory", "deals", "promo", "liquidation",
    "wholesale", "bigsale", "blackfriday", "70off", "80off", "90off",
)


def _verdict_from(facts: dict, expected_price: float | None) -> dict:
    flags: list[dict] = []   # each: {sev: 'high'|'med'|'low', text: ...}
    greens: list[str] = []

    age = facts.get("domain_age_days")
    tls_ok = bool(facts.get("tls_ok"))
    tls_age = facts.get("tls_cert_age_days")
    status = facts.get("http_status")
    reachable = isinstance(status, int) and 200 <= status < 300
    off_domain = bool(facts.get("redirected_off_domain"))
    host = facts.get("domain", "")
    dev = facts.get("price_deviation_pct")

    # --- the strong red flags ---
    if off_domain:
        flags.append({"sev": "high", "text":
            f"Sends you to a different website ({facts.get('final_url','?')}) before checkout — a classic scam move."})
    if not tls_ok:
        flags.append({"sev": "high", "text":
            "No valid security certificate — your connection isn't properly protected."})
    elif not reachable:
        flags.append({"sev": "med", "text":
            f"The site didn't load normally (status {status})."})

    if isinstance(age, int):
        if age < 7:
            flags.append({"sev": "high", "text":
                f"This domain is only {age} day{'s' if age!=1 else ''} old — scam stores are usually brand new."})
        elif age < 30:
            flags.append({"sev": "med", "text":
                f"This domain is just {age} days old. Be cautious with new stores."})
        elif age < 90:
            flags.append({"sev": "low", "text":
                f"Fairly new domain ({age} days old)."})
        elif age >= 365:
            yrs = age // 365
            greens.append(f"Established domain — registered {yrs}+ year{'s' if yrs!=1 else ''} ago.")
    if isinstance(tls_age, int) and tls_age < 14 and isinstance(age, int) and age < 60:
        flags.append({"sev": "low", "text":
            f"Security certificate is only {tls_age} days old (consistent with a brand-new site)."})

    # brand-impersonation + TLD-risk guard (replaces the naive substring scan
    # that waved rayban.cc through and false-flagged shopify.com on "shop").
    from ._brand_guard import brand_guard, deal_token_flag
    _bg = brand_guard(host)
    flags.extend(_bg["flags"])
    _dt = deal_token_flag(host, _DEAL_TOKENS)
    if _dt:
        flags.append(_dt)

    # price too good to be true
    if isinstance(dev, (int, float)) and dev <= -40:
        flags.append({"sev": "high", "text":
            f"The price is {abs(dev):.0f}% below what you expected — 'too good to be true' is the #1 scam hook."})
    elif isinstance(dev, (int, float)) and dev <= -25:
        flags.append({"sev": "med", "text":
            f"The price is {abs(dev):.0f}% under your expectation — unusually cheap."})

    if tls_ok and reachable and not off_domain:
        greens.append("Loads securely on its own domain with a valid certificate.")

    # --- score + verdict (rules disclosed to the user) ---
    weight = {"high": 40, "med": 18, "low": 7}
    risk = min(100, sum(weight[f["sev"]] for f in flags))
    has_high = any(f["sev"] == "high" for f in flags)
    meds = sum(1 for f in flags if f["sev"] == "med")

    if has_high or risk >= 50:
        verdict, band = "HIGH RISK — RED FLAGS", "danger"
    elif meds or risk >= 18:
        verdict, band = "BE CAREFUL", "caution"
    else:
        verdict, band = "LOOKS ESTABLISHED", "ok"

    trust = max(0, 100 - risk)
    return {
        "verdict": verdict, "band": band,
        "trust_score": trust, "risk_score": risk,
        "red_flags": flags, "good_signs": greens,
    }


def check(url: str, expected_price: float | None = None) -> dict:
    """Run the forensic engine and return a consumer verdict (signed)."""
    from . import merchant_fact_check as _mfc
    raw = (url or "").strip()
    host = raw.split("://", 1)[-1].split("/", 1)[0].split("?", 1)[0].lower().strip(".")
    if "." not in host:
        raise ValueError("Enter a real website address, e.g. shop.example.com")

    facts = _mfc.run(domain=host, expected_price=expected_price)
    v = _verdict_from(facts, expected_price)
    now = int(time.time())

    # agentic-readiness: how machine-/agent-consumable this merchant is (0-100).
    # Disclosed weighting — a signal of agent-readiness, not a safety claim.
    secure = bool(facts.get("tls_ok"))
    reachable_ok = isinstance(facts.get("http_status"), int) and 200 <= facts["http_status"] < 300
    on_domain = not facts.get("redirected_off_domain", False)
    structured = bool(facts.get("has_structured_data"))
    ar = (35 if structured else 0) + (20 if secure else 0) + (20 if reachable_ok else 0) \
         + (15 if on_domain else 0) + (10 if facts.get("business_category") not in (None, "unclassified") else 0)
    agentic_readiness = min(100, ar)

    one_liner = {
        "danger": "We found serious red flags. Don't pay until you're sure this is real.",
        "caution": "Some warning signs. Double-check before you hand over money or card details.",
        "ok": "No major red flags in our public-signal check. Still use normal caution.",
    }[v["band"]]

    out = {
        "ok": True,
        "site": host,
        "checked_at": now,
        "checked_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "verdict": v["verdict"],
        "band": v["band"],
        "summary": one_liner,
        "trust_score": v["trust_score"],
        "red_flags": [f["text"] for f in v["red_flags"]],
        "good_signs": v["good_signs"],
        "facts": {
            "domain_age_days": facts.get("domain_age_days"),
            "registrar": facts.get("registrar"),
            "secure_https": bool(facts.get("tls_ok")),
            "loads_ok": isinstance(facts.get("http_status"), int) and 200 <= facts["http_status"] < 300,
            "redirects_off_domain": bool(facts.get("redirected_off_domain")),
            "final_url": facts.get("final_url"),
        },
        "honest_note": "A red-flag check based on public signals — not a guarantee. "
                       "It catches the patterns scammers use so you think twice. A new "
                       "store can be real, and a clever scam can still slip through. "
                       "Your judgment matters. Every fact here is independently verifiable.",
        # --- agent-consumer spec (fields requested by integrating agents) ---
        "domain": host,
        "score": v["trust_score"],
        "securityStatus": {
            "https": secure, "reachable": reachable_ok, "no_offdomain_redirect": on_domain,
        },
        "businessCategory": facts.get("business_category"),
        "agenticReadinessScore": agentic_readiness,
        # cross-METHOD verification tier — GOLD/SILVER/CONTESTED from agreement
        # of two orthogonal evidence paths (infra vs identity). Inside the signed
        # body so the tier itself is Ed25519-attested, not just asserted.
        "cross_verify": _cross_verify.cross_verify(host, facts),
        # signatureDetails describes the signing key/alg; the actual signature +
        # content hash live in onyx_attestation (added by attest below). Kept
        # INSIDE the signed body — adding fields AFTER attest would break verify.
        "signatureDetails": {
            "alg": "Ed25519+JCS",
            "kid": _onyx_sign.signer().kid,
            "public_key": _onyx_sign.signer().pub_b64,
            "signature_in": "onyx_attestation.sig",
            "verify_at": "https://onyx-actions.onrender.com/verify",
        },
    }
    return _onyx_sign.attest(out, tool="onyx_know_before_you_pay")


def render_page(base: str = "https://onyx-actions.onrender.com") -> str:
    """The consumer product: paste a store link, get a red-flag verdict. Mobile
    first, instant, free, no signup. The page a sales team can promote anywhere."""
    return """<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Know Before You Pay — free scam check</title>
<meta name=description content="Paste any online store link. We check it for scam red flags in seconds — free, no signup. Catch the fake stores blocklists miss.">
<meta property="og:title" content="Know Before You Pay — free scam check">
<meta property="og:description" content="Paste a store link, get an instant red-flag check. Catch the fake stores blocklists miss.">
<link rel="canonical" href="https://onyx-actions.onrender.com/check">
<script type="application/ld+json">
{"@context":"https://schema.org","@graph":[
{"@type":"WebApplication","@id":"https://onyx-actions.onrender.com/check#app","name":"Onyx — Know Before You Pay","url":"https://onyx-actions.onrender.com/check","applicationCategory":"SecurityApplication","operatingSystem":"Web","offers":{"@type":"Offer","price":"0","priceCurrency":"USD"},"description":"Free instant scam red-flag check for any online store or checkout link. Catches brand-new fake stores that blocklists miss. No signup. Every verdict is Ed25519-signed and independently verifiable.","provider":{"@id":"https://onyxprotocol.io#org"}},
{"@type":"Organization","@id":"https://onyxprotocol.io#org","name":"Onyx Protocol","url":"https://onyxprotocol.io","description":"The independent, conflict-free trust layer for the agentic web. Onyx signs verifiable real-world facts — merchant, price, contract and counterparty-agent checks — that agents verify before they transact, and publishes SAEI, a signed index of the agent economy.","sameAs":["https://onyx-actions.onrender.com/.well-known/agent-card.json","https://onyx-actions.onrender.com/.well-known/saei/v1.json"]},
{"@type":"FAQPage","mainEntity":[
{"@type":"Question","name":"How do I check if an online store is a scam?","acceptedAnswer":{"@type":"Answer","text":"Paste the store or checkout link into Onyx Know Before You Pay. It scans for scam red flags — new domain age, mismatched TLS certificate, registrar risk and more — and returns an instant free verdict you don't have to sign up for."}},
{"@type":"Question","name":"Is the Onyx scam check free?","acceptedAnswer":{"@type":"Answer","text":"Yes. The consumer scam check at onyx-actions.onrender.com/check is free with no signup. Deeper machine-readable checks are available to AI agents pay-per-call over x402."}},
{"@type":"Question","name":"Can the result be trusted or faked?","acceptedAnswer":{"@type":"Answer","text":"Every Onyx verdict is Ed25519-signed and hash-bound, so any third party can verify it offline. If a result is tampered with, verification rejects it. Onyx earns nothing from any transaction it grades, so it has no conflict of interest."}}
]}
]}
</script>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}
body{font:16px/1.55 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#06070c;color:#e8eef5;margin:0;padding:0;-webkit-font-smoothing:antialiased}
.wrap{max-width:620px;margin:0 auto;padding:34px 18px 60px}
h1{font-size:30px;line-height:1.1;margin:0 0 8px;letter-spacing:-.02em}
.tag{color:#34d399;font-weight:700}
.sub{color:#93a4b8;margin:0 0 26px;font-size:16px}
form{display:flex;gap:8px;margin:0 0 8px}
input{flex:1;min-width:0;background:#0d1119;border:1.5px solid #1d2738;color:#e8eef5;border-radius:12px;padding:15px 14px;font-size:16px}
input:focus{outline:none;border-color:#34d399}
button{background:#34d399;color:#04150d;border:0;border-radius:12px;padding:0 20px;font-size:16px;font-weight:800;cursor:pointer;white-space:nowrap}
button:disabled{opacity:.55;cursor:wait}
.hint{color:#5b6c80;font-size:13px;margin:0 0 26px}
.card{display:none;border-radius:16px;padding:20px;margin:18px 0;border:1.5px solid #1d2738;background:#0a0e16;animation:rise .25s ease}
@keyframes rise{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
.card.ok{border-color:#1f7a52;background:#08130d}
.card.caution{border-color:#9a7b1e;background:#15120a}
.card.danger{border-color:#9a2b2b;background:#160a0a}
.vbig{font-size:23px;font-weight:800;margin:0 0 4px;display:flex;align-items:center;gap:10px}
.ok .vbig{color:#34d399}.caution .vbig{color:#fbbf24}.danger .vbig{color:#f87171}
.dot{width:13px;height:13px;border-radius:50%;flex:none}
.ok .dot{background:#34d399}.caution .dot{background:#fbbf24}.danger .dot{background:#f87171}
.site{color:#93a4b8;font-size:14px;margin:0 0 14px;word-break:break-all}
.smry{font-size:16px;margin:0 0 16px}
.sec{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:#7c8da0;margin:16px 0 7px;font-weight:700}
ul{margin:0;padding:0;list-style:none}
li{padding:8px 0 8px 26px;position:relative;border-bottom:1px solid #121a27;font-size:15px}
li.flag::before{content:'⚠';position:absolute;left:0;color:#fbbf24}
li.danger::before{content:'⛔';position:absolute;left:0}
li.good::before{content:'✓';position:absolute;left:0;color:#34d399}
.score{display:flex;align-items:center;gap:12px;margin:18px 0 4px}
.bar{flex:1;height:9px;background:#121a27;border-radius:6px;overflow:hidden}
.fill{height:100%;border-radius:6px;transition:width .5s}
.note{color:#7c8da0;font-size:12.5px;line-height:1.5;margin:18px 0 0;border-top:1px solid #121a27;padding-top:14px}
.foot{color:#4a5a6e;font-size:12px;text-align:center;margin:34px 0 0;line-height:1.7}
.foot b{color:#7c8da0}
.err{color:#f87171;font-size:14px;margin:8px 0}
</style></head><body><div class=wrap>
<h1>Know <span class=tag>before you pay</span>.</h1>
<p class=sub>Paste any online store or checkout link. We scan it for scam red flags in seconds — free, no signup. We catch the brand-new fake stores blocklists miss.</p>
<form id=f><input id=u type=text inputmode=url autocomplete=off autocapitalize=off
 placeholder="paste a store link, e.g. amazing-deals-outlet.com" aria-label="store link"><button id=b type=submit>Check</button></form>
<p class=hint>No link saved. No account. Works on your phone.</p>
<p class=err id=e></p>
<div class=card id=c>
  <div class=vbig><span class=dot></span><span id=v></span></div>
  <div class=site id=s></div>
  <div class=smry id=m></div>
  <div id=flags></div>
  <div id=goods></div>
  <div class=score><span style="font-size:13px;color:#93a4b8">Trust</span>
    <div class=bar><div class=fill id=fill></div></div>
    <span id=ts style="font-size:14px;font-weight:700;width:42px;text-align:right"></span></div>
  <div class=note id=note></div>
</div>
<div class=foot>Every result is <b>cryptographically signed</b> &amp; independently verifiable — we show facts, not opinions.<br>An independent red-flag check. Not affiliated with any store. Your judgment matters.</div>
</div><script>
var API="/api/check";
var f=document.getElementById('f'),u=document.getElementById('u'),b=document.getElementById('b'),
e=document.getElementById('e'),c=document.getElementById('c');
function esc(t){var d=document.createElement('div');d.textContent=t;return d.innerHTML;}
f.addEventListener('submit',function(ev){ev.preventDefault();go();});
function go(){
  var val=u.value.trim();e.textContent='';c.style.display='none';
  if(!val){e.textContent='Paste a store link first.';return;}
  b.disabled=true;b.textContent='Checking…';
  fetch(API+'?url='+encodeURIComponent(val)).then(function(r){return r.json();}).then(function(d){
    b.disabled=false;b.textContent='Check';
    if(!d||d.ok===false&&!d.verdict){e.textContent=(d&&d.error)||'Could not check that link.';return;}
    render(d);
  }).catch(function(){b.disabled=false;b.textContent='Check';e.textContent='Network error — try again.';});
}
function render(d){
  c.className='card '+(d.band||'caution');
  document.getElementById('v').textContent=d.verdict||'';
  document.getElementById('s').textContent=d.site||'';
  document.getElementById('m').textContent=d.summary||'';
  var fl=document.getElementById('flags');fl.innerHTML='';
  if((d.red_flags||[]).length){var h='<div class=sec>What we found</div><ul>';
    d.red_flags.forEach(function(t){var cl=(d.band==='danger')?'danger':'flag';h+='<li class="'+cl+'">'+esc(t)+'</li>';});
    fl.innerHTML=h+'</ul>';}
  var gd=document.getElementById('goods');gd.innerHTML='';
  if((d.good_signs||[]).length){var g='<div class=sec>Good signs</div><ul>';
    d.good_signs.forEach(function(t){g+='<li class=good>'+esc(t)+'</li>';});
    gd.innerHTML=g+'</ul>';}
  var ts=(d.trust_score==null?50:d.trust_score);
  document.getElementById('ts').textContent=ts;
  var fill=document.getElementById('fill');fill.style.width=ts+'%';
  fill.style.background=ts>=67?'#34d399':ts>=34?'#fbbf24':'#f87171';
  document.getElementById('note').textContent=d.honest_note||'';
  c.style.display='block';c.scrollIntoView({behavior:'smooth',block:'nearest'});
}
</script></body></html>"""
