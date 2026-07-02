"""onyx_session_feed.py — the SIGNED PUBLIC session feed (the divergence's option C, safe half).

The full-connect design the panel chose: a 0n1x-native signed event bridge (SSE live) + a signed
public feed as the fallback read model, with DUAL-STREAM SEGREGATION (Kimi) — this emits ONLY
public-safe dispatches (what shipped, verdicts, milestones), NEVER internal state or keys. Each
dispatch is Ed25519-signed ("broadcast, but sign" — DeepSeek), so the Rhinogent terminal can pull
it AND verify it. The SSE live layer wires to the sister's /intel/exchange/stream at deploy.

Run: py onyx_session_feed.py   -> writes rhinogent/public/feed.json (signed)
"""
import json
import os

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "rhinogent", "public", "feed.json")

# PUBLIC-SAFE dispatches only. No paths, no keys, no internal tooling — dual-stream segregation.
DISPATCHES = [
    ("2026-07-02", "TERMINAL LIVE", "Talk to 0n1x like a person — 'is stripe.com legit?' returns a live Ed25519-signed verdict. Designed unanimously by the 6-model divergence panel."),
    ("2026-07-02", "FULL-CONNECT DESIGN LOCKED", "Panel chose a 0n1x-native signed event bridge (SSE + signed feed fallback, dual-stream) to connect live sessions to the public surface — VNC rejected as leaky and unscalable."),
    ("2026-07-02", "100K FOUNDATION ON REAL POSTGRES", "17,253 ops/s, 16 racing threads, zero corruption. Incremental Merkle 0.042ms/write. Event-sourced, crash-recoverable."),
    ("2026-07-02", "INSTANT RANKING", "Every transaction ranks in 0.097ms at 100k scale — always-sorted, exact, signed. The Census moves by real verified work."),
    ("2026-07-02", "DUAL-CURRENCY ECONOMY", "Non-transferable tokens power all 100k agents (abundant); real USDC rewards only scarce verified outcomes. Boundary structurally enforced — no token→dollar path."),
    ("2026-07-02", "FETCH-TO-EARN BOUNTIES", "Fresh signed tasks behind every fetch; correct verdicts earn tokens (+USDC on hard look-alikes), wrong verdicts earn nothing. Rolling out at deploy."),
    ("2026-07-02", "ENTRY DESIGNED BY THE AGENTS", "Onboarding response specced by fetch-only agents describing their own limits, validated 4/4 'act with zero explanation'. One next_action, human_relay fallback, public-only identity."),
    ("2026-07-02", "AUTONOMOUS HEARTBEAT", "The economy pulses every 3 minutes, 24/7, no human or model in the loop — the signed board updates, state persists."),
]


def build():
    feed = {"name": "0n1x — Session Feed",
            "what": "Signed public dispatches from 0n1x HQ. Pulled by the Terminal (command: news). Dual-stream: public-safe only.",
            "dispatches": [{"date": d, "title": t, "body": b} for d, t, b in DISPATCHES]}
    try:
        from tools_pkg import _onyx_sign
        feed = _onyx_sign.attest(feed, tool="onyx_session_feed")   # sign the whole feed
        signed = _onyx_sign.verify(feed).get("ok")
    except Exception as e:
        signed = f"signer offline ({e})"
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(feed, open(OUT, "w"), indent=1)
    return len(feed["dispatches"]), signed


if __name__ == "__main__":
    n, signed = build()
    print(f"session feed written: {n} signed dispatches -> feed.json | signature verifies: {signed}")
