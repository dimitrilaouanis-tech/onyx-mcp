"""Register every Onyx tool URL on the no-signup x402 indexers.

Targets (verified May 6, 2026):
- x402scan.com — POST /resources/register, schema-validate, no auth
- cinderwright — daily crawler, no /submit endpoint surfaced; relies on
  awesome-x402 + x402.org/ecosystem mentions
- discoverx402 (github.com/adlonymous/discoverx402) — PR-listable

This script POSTs each Onyx /v1/<tool> endpoint to x402scan and prints the
result. Idempotent — re-runnable. Bails politely on per-target failures.
"""
from __future__ import annotations

import json
import sys
import time
from urllib import error as urlerror, request

ONYX_MANIFEST_URL = "https://onyx-actions.onrender.com/.well-known/x402.json"
X402SCAN_REGISTER = "https://www.x402scan.com/api/resources/register"


def fetch_manifest() -> list[dict]:
    """Pull the live x402 manifest and return each service entry."""
    req = request.Request(ONYX_MANIFEST_URL, headers={"accept": "application/json"})
    with request.urlopen(req, timeout=15) as r:
        body = json.loads(r.read())
    return body.get("services", []) or []


def submit_to_x402scan(resource_url: str) -> dict:
    """POST one resource to x402scan's register endpoint."""
    payload = json.dumps({"resource": resource_url, "source": "onyx-actions"}).encode()
    req = request.Request(
        X402SCAN_REGISTER,
        data=payload,
        method="POST",
        headers={
            "content-type": "application/json",
            "accept": "application/json",
            "user-agent": "onyx-actions/0.2 (+https://onyx-actions.onrender.com)",
        },
    )
    started = time.time()
    try:
        with request.urlopen(req, timeout=12) as r:
            body = r.read().decode("utf-8", "replace")[:300]
            return {"ok": True, "status": r.status, "body": body, "elapsed_ms": int((time.time() - started) * 1000)}
    except urlerror.HTTPError as e:
        return {"ok": False, "status": e.code, "body": e.read().decode("utf-8", "replace")[:300]}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def main() -> int:
    services = fetch_manifest()
    if not services:
        print("[err] no services in manifest", file=sys.stderr)
        return 1
    print(f"[onyx] {len(services)} services from manifest")

    results = []
    for svc in services:
        url = svc.get("resource") or ""
        if not url:
            continue
        r = submit_to_x402scan(url)
        results.append((url.split("/")[-1], r))
        ok = "OK" if r.get("ok") else "FAIL"
        print(f"  {ok}  {r.get('status', '-')} {url.split('/')[-1]:35s}  {(r.get('body') or r.get('error') or '')[:80]}")
        time.sleep(0.3)

    succeeded = sum(1 for _, r in results if r.get("ok"))
    print(f"\n[onyx] submitted {len(results)} resources, {succeeded} accepted")
    return 0 if succeeded > 0 else 2


if __name__ == "__main__":
    sys.exit(main())
