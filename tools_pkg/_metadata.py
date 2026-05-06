"""Buyer-language metadata for the highest-leverage tools.

Loaded once at framework startup. Each entry binds extra dunder attributes
on the tool's `run` function — picked up by the GET /v1/<tool> introspection
card so agents see when_to_use + vs_alternatives + worked example before
they pay.

Single source of truth. Edit here, no need to touch the tool files.
"""
from __future__ import annotations

META: dict[str, dict] = {
    "onyx_base_tx_explainer": {
        "when_to_use": (
            "Use when a trading agent needs to verify a Base mainnet transaction "
            "actually did what it claims — confirm a swap landed at the expected "
            "price, audit a token transfer, or explain a contract interaction. "
            "Pre-trade safety check or post-trade verification."
        ),
        "vs_alternatives": (
            "OATP charges $0.10 for the same primitive on Solana — Onyx is the "
            "first to ship this on Base mainnet, at half the price. Etherscan's "
            "free API has rate limits and no human-readable summary. Zapper's "
            "transaction-details ($0.0011) returns proprietary 'interpretation' "
            "rather than raw decoded structure."
        ),
        "example_request": {"tx_hash": "0x" + "ab" * 32},
        "example_response": {
            "summary": "Swap with 2 token transfers (1 swap event).",
            "status": "success", "method": "swapExactETHForTokens",
            "transfers": [
                {"symbol": "WETH", "amount": 1.0, "from": "0xrouter", "to": "0xpool"},
                {"symbol": "USDC", "amount": 3450.5, "from": "0xpool", "to": "0xagent"},
            ],
            "swap_events": 1, "elapsed_ms": 280,
        },
    },
    "onyx_base_tx_simulator": {
        "when_to_use": (
            "Use BEFORE signing any Base mainnet transaction with non-trivial "
            "value. Catches reverts, decodes revert reasons, projects gas. "
            "Saves agents from blowing gas on doomed txs. Read-only — never "
            "submits."
        ),
        "vs_alternatives": (
            "OATP charges $0.20 for tx_simulator on Solana. Tenderly/Foundry "
            "require infra setup and API keys. Onyx is the first x402-paid "
            "Base-native simulator, half OATP price."
        ),
        "example_request": {
            "from_address": "0x" + "a" * 40,
            "to_address": "0x4200000000000000000000000000000000000006",
            "data": "0xa9059cbb...",
        },
        "example_response": {
            "success": True, "return_data": "0x000...01",
            "gas_estimate": 51234, "elapsed_ms": 145,
        },
    },
    "onyx_base_token_risk_scan": {
        "when_to_use": (
            "Use BEFORE buying a freshly deployed Base token. Flags rug-vector "
            "risks: active owner, mint authority, supply concentration, missing "
            "or tiny bytecode. Runs in ~1s. Saves the position when verdict is "
            "high_risk."
        ),
        "vs_alternatives": (
            "OATP charges $0.50 for token_risk_scan on Solana. GoPlus and "
            "Honeypot.is are free but rate-limited and require web scraping "
            "with no x402-native payment loop. Onyx is half OATP and on Base — "
            "first x402-paid Base risk scanner."
        ),
        "example_request": {"address": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"},
        "example_response": {
            "is_erc20": True, "decimals": 6, "total_supply": 4418662780.0,
            "owner_renounced": False, "owner_balance_pct": 0.0,
            "score_0_100": 15, "verdict": "safe",
            "risk_factors": ["active owner: 0x3abd6f64..."],
        },
    },
    "onyx_solve_captcha": {
        "when_to_use": (
            "Use when an agent's browser automation hits an image-based captcha "
            "wall mid-task (signup, login, scraping checkpoint). Returns the "
            "answer in ~30ms. Not for reCAPTCHA v2/v3 or hCaptcha — those are "
            "interaction-based."
        ),
        "vs_alternatives": (
            "2captcha at $0.001/solve takes 8-20s and requires API key signup + "
            "account top-up + support tickets. Anti-Captcha similar. Onyx's "
            "$0.003 is x402-native (no signup, agent's wallet pays directly), "
            "200-600x faster, no account state to manage. Net cheaper at any "
            "volume where agent-time matters more than per-solve cost."
        ),
        "example_request": {"image_url": "https://example.com/captcha.png"},
        "example_response": {
            "answer": "AB7K9", "source": "onyx.ddddocr",
            "elapsed_ms": 32, "bytes": 1840,
        },
    },
    "onyx_url_text": {
        "when_to_use": (
            "Use when an agent needs to read a web page WITHOUT spinning up a "
            "browser. Faster and cheaper than browser_extract for static "
            "content. Pairs with onyx_url_unshorten when the URL is a t.co / "
            "bit.ly redirect."
        ),
        "vs_alternatives": (
            "Exa /search costs $0.007 and gives snippets, not full text. "
            "Browserbase session-create costs more and returns a session ID, "
            "not text. Direct fetch from agent runtime blocks on rate-limits "
            "and CDN gates. Onyx $0.001 fetches and strips HTML server-side, "
            "cap 200kB."
        ),
        "example_request": {
            "url": "https://en.wikipedia.org/wiki/Model_Context_Protocol",
            "max_chars": 4000,
        },
        "example_response": {
            "url": "https://en.wikipedia.org/wiki/Model_Context_Protocol",
            "status": 200, "title": "Model Context Protocol - Wikipedia",
            "text": "The Model Context Protocol (MCP) is an open standard...",
            "char_count": 3987, "word_count": 612, "truncated": True,
            "elapsed_ms": 240,
        },
    },
    "onyx_token_metadata": {
        "when_to_use": (
            "Use before transacting with any ERC-20 on Base — confirms the "
            "address is a real ERC-20, resolves name + symbol + decimals + "
            "total supply. Pairs with onyx_base_token_risk_scan for full "
            "pre-trade safety."
        ),
        "vs_alternatives": (
            "Alchemy/QuickNode token APIs require API keys + paid tier above "
            "free quota. Etherscan's tokeninfo is rate-limited. Onyx $0.001 "
            "reads via Base public RPC, no upstream cost, no key. Cheaper than "
            "Zapper at $0.001125."
        ),
        "example_request": {"address": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"},
        "example_response": {
            "name": "USD Coin", "symbol": "USDC", "decimals": 6,
            "total_supply": 4418662780.025056, "is_erc20": True,
            "elapsed_ms": 285,
        },
    },
    "onyx_ens_resolve": {
        "when_to_use": (
            "Use when an agent encounters an ENS name like vitalik.eth and "
            "needs to send funds, validate identity, or display the address. "
            "Reverse-resolution also supported."
        ),
        "vs_alternatives": (
            "Most ENS resolvers require Web3 RPC setup or an API key (Alchemy, "
            "Infura). Onyx $0.0008 via free public ensideas API — no key, no "
            "infra. Cheaper than Zapper account-identity at $0.0011."
        ),
        "example_request": {"name": "vitalik.eth"},
        "example_response": {
            "input": "vitalik.eth", "input_kind": "name",
            "name": "vitalik.eth",
            "address": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
            "avatar": "https://...",
            "display_name": "vitalik.eth",
        },
    },
}


def apply(tool) -> None:
    """Bind metadata onto a tool module's run function if registered."""
    name = getattr(tool, "NAME", None)
    if not name:
        return
    meta = META.get(name)
    if not meta:
        return
    fn = getattr(tool, "run", None)
    if fn is None:
        return
    if "when_to_use" in meta:
        fn.__when_to_use__ = meta["when_to_use"]
    if "vs_alternatives" in meta:
        fn.__vs_alternatives__ = meta["vs_alternatives"]
    if "example_request" in meta:
        fn.__example_request__ = meta["example_request"]
    if "example_response" in meta:
        fn.__example_response__ = meta["example_response"]
