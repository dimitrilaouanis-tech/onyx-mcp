"""Brand-impersonation + TLD-risk guard for the merchant verdict.

Closes the two structural holes in the old deal-token substring scan:
  1. FALSE NEGATIVE — a famous brand name on a throwaway TLD (rayban.cc) had
     no detector at all, so counterfeits scored 0 flags ("LOOKS ESTABLISHED").
  2. FALSE POSITIVE — deal-tokens matched as raw substrings, so "shop" inside
     "shopify" mis-fired ("BE CAREFUL" on a legit brand).

Facts-not-judgments: every flag states the observable pattern (brand token +
non-official domain + risky TLD), never "this is a scam". Deterministic and
fully disclosed so the verdict stays signable + reproducible.
"""

import re

# High-value brands counterfeiters impersonate, mapped to the OFFICIAL apex.
# Presence of the token on a NON-official domain is the signal — not a conviction.
_BRANDS = {
    "rayban": "ray-ban.com", "ray-ban": "ray-ban.com",
    "nike": "nike.com", "adidas": "adidas.com", "yeezy": "adidas.com",
    "gucci": "gucci.com", "prada": "prada.com", "rolex": "rolex.com",
    "louisvuitton": "louisvuitton.com", "chanel": "chanel.com",
    "northface": "thenorthface.com", "thenorthface": "thenorthface.com",
    "patagonia": "patagonia.com", "ralphlauren": "ralphlauren.com",
    "balenciaga": "balenciaga.com", "moncler": "moncler.com",
    "lululemon": "lululemon.com", "supreme": "supremenewyork.com",
    "apple": "apple.com", "raybans": "ray-ban.com", "oakley": "oakley.com",
}

# TLDs over-represented in counterfeit / fake-store registrations.
_RISKY_TLD = {
    "cc", "top", "xyz", "vip", "online", "sbs", "icu", "buzz", "monster",
    "rest", "shop", "store", "sale", "boutique", "ru", "tk", "gq", "cn",
}

# Exact registered domains that are legitimate even though they contain a
# brand or deal token (kills the "shop" in "shopify" class of false positives).
_LEGIT = {
    "shopify.com", "shop.app", "shopify.dev", "nike.com", "adidas.com",
    "ray-ban.com", "apple.com", "gucci.com", "rolex.com", "oakley.com",
    "thenorthface.com", "patagonia.com", "ralphlauren.com", "lululemon.com",
}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def brand_guard(host: str) -> dict:
    """Return {flags:[{sev,text}], brand, official, tld_risky} for a hostname."""
    host = (host or "").lower().strip().strip(".")
    parts = host.split(".")
    if len(parts) < 2:
        return {"flags": [], "brand": None, "official": None, "tld_risky": False}
    sld = ".".join(parts[-2:])          # registered domain (label.tld)
    tld = parts[-1]
    label = parts[-2]                   # the registrable label
    full_label = _norm("".join(parts[:-1]))  # subdomains+label, punctuation stripped
    tld_risky = tld in _RISKY_TLD

    if sld in _LEGIT:
        return {"flags": [], "brand": None, "official": None, "tld_risky": tld_risky}

    flags: list[dict] = []
    brand_hit = None
    official = None
    for b, off in _BRANDS.items():
        bn = _norm(b)
        # brand token present in the label/subdomain, but this is NOT the official apex
        if bn in full_label and sld != off and not host.endswith("." + off):
            brand_hit, official = b, off
            sev = "high" if tld_risky else "med"
            where = f"high-risk .{tld}" if tld_risky else f".{tld}"
            flags.append({"sev": sev, "text": (
                f"Uses the brand name '{b}' but is NOT the official {off} — "
                f"and sits on a {where} domain. This is the classic counterfeit "
                f"/ brand-impersonation pattern.")})
            break

    # bare risky-TLD note (low) when no known brand but on a counterfeit-heavy TLD
    if not brand_hit and tld_risky:
        flags.append({"sev": "low", "text": (
            f"Registered on .{tld}, a TLD over-represented in fake-store "
            f"registrations. Not conclusive on its own.")})

    return {"flags": flags, "brand": brand_hit, "official": official,
            "tld_risky": tld_risky}


def deal_token_flag(host: str, deal_tokens) -> dict | None:
    """Word-boundary-aware deal-token check (fixes 'shop' in 'shopify').

    Only fires when a deal token is a STANDALONE segment of the label
    (split on non-alphanumerics or as a suffix/prefix joined to a brand),
    never as an incidental substring of a longer real word.
    """
    host = (host or "").lower().strip(".")
    label = host.split(".")[-2] if host.count(".") >= 1 else host
    # split the label into segments on common separators
    segs = re.split(r"[^a-z0-9]+", label)
    # also detect token glued to a brand, e.g. "nikeoutlet" -> outlet
    hits = []
    for t in deal_tokens:
        if t in segs:                       # standalone segment: outlet, sale...
            hits.append(t)
        elif label.endswith(t) and label != t and len(label) - len(t) >= 3:
            # token as a suffix on a longer label (nikeoutlet, yeezysale)
            hits.append(t)
    if hits:
        return {"sev": "med", "text": (
            f"The web address uses sales-pitch words ({', '.join(hits[:3])}) "
            f"as a name segment — common in fake-deal stores.")}
    return None
