#!/usr/bin/env python3
"""IndexNow push — instant Bing/Yandex (re)index of the 0n1x LAND pages.

Why this matters (verified): ChatGPT-search is ~87% Bing-shaped (its citations sit
in Bing's top-20), and Bing accepts IndexNow — a push protocol that ingests new/
changed URLs in MINUTES instead of waiting for an organic recrawl. Google has not
adopted it, so this is the cheapest high-leverage answer-engine lever there is:
rank in Bing -> win most of the ChatGPT-search battle.

SETUP (one time):
  1. Pick/keep the key below (a 32+ char hex string). Generating a fresh one:
       py -c "import secrets; print(secrets.token_hex(16))"
  2. Host it at the domain root as  https://<DOMAIN>/<KEY>.txt  whose body is the
     key itself (proves you own the domain). Also drop it next to this file.
  3. Set DOMAIN below to the live 0n1x domain, list the canonical URLs, run:
       py 0n1x/indexnow_push.py

It submits to api.indexnow.org (fans out to Bing + Yandex). Re-run on every real
content change (bump the page, push again) to ride the freshness multiplier.
"""
from __future__ import annotations

import json
import sys
import urllib.request

# --- configure these for the live deployment ---
DOMAIN = "0n1x.com"                      # <-- set to the live 0n1x domain
KEY = "0n1x4ae0a11d1742be71c0de5ea7c0ffee"   # <-- 32+ hex chars; host as /<KEY>.txt
URLS = [
    f"https://{DOMAIN}/",
    f"https://{DOMAIN}/aeo-methodology",
    f"https://{DOMAIN}/competitive-landscape",
    f"https://{DOMAIN}/land",
]
# ------------------------------------------------

_ENDPOINT = "https://api.indexnow.org/indexnow"
_UA = "Mozilla/5.0 (compatible; onyx-observer/1.0; +https://0n1x)"


def push(domain: str, key: str, urls: list[str]) -> int:
    payload = {
        "host": domain,
        "key": key,
        "keyLocation": f"https://{domain}/{key}.txt",
        "urlList": urls,
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        _ENDPOINT, data=body, method="POST",
        headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": _UA},
    )
    with urllib.request.urlopen(req, timeout=25) as resp:
        code = resp.getcode()
        print(f"IndexNow accepted {len(urls)} URL(s) for {domain} -> HTTP {code}")
        print("(200/202 = accepted; Bing ingests within minutes. Re-run on each real change.)")
        return code


if __name__ == "__main__":
    if "0n1x.com" == DOMAIN and len(sys.argv) < 2:
        print("Set DOMAIN to the live 0n1x domain (and host /<KEY>.txt) before pushing.")
        print("Dry-run payload:")
        print(json.dumps({"host": DOMAIN, "key": KEY,
                          "keyLocation": f"https://{DOMAIN}/{KEY}.txt", "urlList": URLS}, indent=2))
        sys.exit(0)
    push(DOMAIN, KEY, URLS)
