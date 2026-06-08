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
    "onyx_solana_tx_explainer": {
        "when_to_use": (
            "Use when a Solana trading agent needs to verify what a tx "
            "actually did — confirm a Jupiter swap landed at the expected "
            "price, audit a pump.fun buy, explain a stake-account interaction. "
            "Pre-trade safety check or post-trade verification on Solana."
        ),
        "vs_alternatives": (
            "OATP charges $0.10 for the exact same primitive on Solana with "
            "1,350+ unique paying agents — Onyx is the second x402-paid Solana "
            "tx_explainer at HALF the price. Helius/QuickNode require API keys + "
            "paid tiers. Solscan is free but rate-limited and returns HTML."
        ),
        "example_request": {"signature": "5j7s4..." + "x" * 80},
        "example_response": {
            "summary": "DEX swap touching 3 program(s), 4 token-balance update(s).",
            "status": "success",
            "fee_sol": 0.000005,
            "compute_units": 142000,
            "instruction_count": 7,
            "programs": ["JUP6Lk...", "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"],
            "elapsed_ms": 320,
        },
    },
    "onyx_solana_token_metadata": {
        "when_to_use": (
            "Use before transacting with any SPL token on Solana — confirms "
            "the address is a real SPL mint, resolves name + symbol + "
            "decimals + total supply via SPL Mint layout + Metaplex PDA. "
            "Pairs with onyx_solana_token_risk_scan for full pre-trade safety."
        ),
        "vs_alternatives": (
            "Helius DAS API needs an API key + paid tier above 100 RPM. "
            "Birdeye token-overview is rate-limited and returns proprietary "
            "fields. Onyx $0.0008 reads SPL Mint + Metaplex PDA via free "
            "public RPC, no signup, x402-direct."
        ),
        "example_request": {"mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"},
        "example_response": {
            "mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "name": "USD Coin", "symbol": "USDC", "decimals": 6,
            "total_supply": 8776108207.89,
            "mint_authority": "2wmVCSfPxGPjrnMMn7rchp4uaeoTqN39mXFC2zhPdri9",
            "freeze_authority": "3sNBr7kMccME5D55xNgsmYpZnzPgP2g12CixAajXypn6",
            "is_spl_token": True,
            "elapsed_ms": 285,
        },
    },
    "onyx_solana_token_risk_scan": {
        "when_to_use": (
            "Use BEFORE buying any freshly-deployed Solana token — "
            "memecoins, pump.fun launches, freshly-bonded curves. Flags "
            "the dominant rug vectors: active mint authority (unlimited "
            "supply risk), active freeze authority (wallet-freeze risk), "
            "top-1/top-10 holder concentration, pump.fun-style mint. "
            "Sub-second latency for sniper/MEV agent gates."
        ),
        "vs_alternatives": (
            "OATP charges $0.50 for the same primitive with 800+ paying "
            "agents — Onyx is HALF price ($0.25). RugCheck.xyz is free "
            "but rate-limited, requires HTML scraping, and has no x402 "
            "settlement loop. Bubblemaps and DEXTools require API keys "
            "and paid tiers."
        ),
        "example_request": {"mint": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"},
        "example_response": {
            "mint": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
            "score_0_100": 8, "verdict": "safe",
            "mint_authority_renounced": True,
            "freeze_authority_renounced": True,
            "top1_holder_pct": 4.2, "top10_holders_pct": 31.8,
            "is_pump_fun_style": False,
            "risk_factors": ["mint_authority renounced",
                             "top-10 holders own 31.8% of supply"],
            "elapsed_ms": 410,
        },
    },
    "onyx_solana_jupiter_quote": {
        "when_to_use": (
            "Use BEFORE every Solana swap to lock execution price. "
            "Aggregates Orca/Raydium/Meteora/Phoenix/Lifinity into one "
            "best-route quote with price impact + slippage + intermediate "
            "hops. Pairs with onyx_solana_token_risk_scan as the standard "
            "pre-trade gate."
        ),
        "vs_alternatives": (
            "Jupiter's lite-api is free but agents need their own retry/"
            "rate-limit logic and have no per-call billing primitive. "
            "Birdeye's quote API costs $0.005 + API key signup. Helius "
            "swap quotes need a paid tier. Onyx $0.001 with x402-direct "
            "USDC settlement, no signup, no key tracking."
        ),
        "example_request": {
            "input_mint": "So11111111111111111111111111111111111111112",
            "output_mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "amount": "1000000000",
        },
        "example_response": {
            "out_amount": "88083339", "min_out_amount": "87637925",
            "price_impact_pct": 0.0001, "hop_count": 2,
            "amms_used": ["Whirlpool", "Raydium"],
            "elapsed_ms": 320,
        },
    },
    "onyx_solana_wallet_activity": {
        "when_to_use": (
            "Use for whale-watching, copy-trading, or KYT agents that "
            "need to know what a wallet just did on Solana. Returns "
            "recent signatures with program/action tags so the agent "
            "doesn't need a second call per signature."
        ),
        "vs_alternatives": (
            "Helius webhooks: $25/mo subscription. Birdeye wallet-"
            "portfolio: $0.002 + API key. Solscan API: rate-limited, "
            "no real-time. Onyx $0.002 per call, no signup, x402-direct."
        ),
        "example_request": {
            "wallet": "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM",
            "limit": 25,
        },
        "example_response": {
            "wallet": "9WzD...AWWM", "count": 25, "error_count": 0,
            "activity": [{"signature": "5xj7...", "status": "success",
                          "actions": ["jupiter_swap", "spl_token"]}],
            "elapsed_ms": 410,
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
