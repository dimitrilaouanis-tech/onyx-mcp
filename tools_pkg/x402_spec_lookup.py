"""x402 spec quick-reference, as a tool.

Given an error string, status code, header name, payload field, or feature
keyword from the x402 v2 protocol, return the relevant spec section and a
plain-English fix. Documentation-as-a-tool — closes the loop with
onyx_x402_simulate (before sign) + onyx_verify_explain (after sign).

Stdlib-only. No network. Free tier — knowledge embedded.
"""
from __future__ import annotations

NAME = "onyx_x402_spec_lookup"
PRICE_USDC = "0"
TIER = "free"
DESCRIPTION = (
    "Quick-reference into the x402 v2 protocol spec. Look up an error string, "
    "HTTP status, header name, payload field, or feature keyword and get the "
    "relevant spec snippet plus a plain-English fix. Replaces 30 minutes of "
    "spec-grepping with a single call. Free tier — embedded knowledge, no network."
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "What to look up: error string ('invalid_exact_evm_payload_authorization_valid_before'), header name ('PAYMENT-SIGNATURE'), status code ('402'), payload field ('nonce'), or feature keyword ('EIP-3009', 'CAIP-2', 'facilitator', 'JWT').",
        },
    },
    "required": ["query"],
}


_KNOWLEDGE: list[tuple[list[str], str, str, str]] = [
    # (keywords matched lowercased, topic, spec snippet, plain-English fix)
    (
        ["402", "payment required", "payment-required"],
        "HTTP 402 Payment Required",
        "HTTP 402 with a 'payment-required' header (base64-encoded x402 challenge) is the canonical 'pay-before-response' signal. v2: header named 'payment-required'; v1: 'X-PAYMENT-REQUIRED'.",
        "Decode the base64 'payment-required' header value as JSON to recover the challenge: {x402Version, resource, accepts:[...]}. The 'accepts' array lists payment options the server will honor.",
    ),
    (
        ["payment-signature", "x-payment", "header"],
        "Payment headers (v1 vs v2)",
        "v1 used 'X-PAYMENT'; v2 renamed to 'PAYMENT-SIGNATURE'. Both carry base64(JSON(paymentPayload)). Servers accepting v2 should still accept X-PAYMENT for back-compat.",
        "When retrying a 402, send PAYMENT-SIGNATURE: <base64> (v2). If the server only knows v1, send X-PAYMENT: <base64>. The body is identical — just the header name changes.",
    ),
    (
        ["paymentpayload", "payload", "shape", "flat", "nested", "v1 shape", "v2 shape"],
        "PaymentPayload shape (v2 = flat)",
        "v2: paymentPayload is FLAT: {x402Version:2, scheme, network, payload:{signature, authorization}}. v1: nested under resource/accepted. Most facilitator rejections come from sending the v1 shape.",
        "If you see 'invalid_exact_evm_payload' or bare 402 with empty body, check that paymentPayload is the v2 flat shape — NOT wrapped in {resource, accepted}.",
    ),
    (
        ["eip-3009", "eip3009", "transferwithauthorization", "authorization"],
        "EIP-3009 TransferWithAuthorization",
        "x402 'exact' scheme on EVM uses EIP-3009. The authorization object is: {from, to, value, validAfter, validBefore, nonce}. Signer signs an EIP-712 typed-data digest of this struct.",
        "EIP-712 domain MUST be {name: extra.name, version: extra.version, chainId: <int from CAIP-2 network>, verifyingContract: asset_address}. For USDC on Base: name='USDC', version='2', chainId=8453, verifyingContract=USDC contract.",
    ),
    (
        ["validbefore", "validafter", "expired", "timing", "clock"],
        "EIP-3009 timing constraints",
        "validAfter and validBefore are string-encoded unix seconds. The facilitator enforces: now-30 <= validAfter <= now AND validBefore >= now+10. validBefore typically = now + maxTimeoutSeconds - 5.",
        "If validBefore <= block.timestamp at /verify time, facilitator returns invalid_exact_evm_payload_authorization_valid_before. Set validBefore = floor(now) + maxTimeoutSeconds - 5 minimum. NTP-sync your client.",
    ),
    (
        ["nonce", "replay", "nonce_already_used"],
        "EIP-3009 nonce",
        "nonce is 32 random bytes, 0x-prefixed (66 chars total). Facilitator persists used nonces — replay = rejection. Generate fresh via os.urandom(32).",
        "If you see nonce_already_used: your client is reusing a nonce. Don't cache or derive the nonce; mint a fresh os.urandom(32).hex() per request.",
    ),
    (
        ["caip-2", "caip2", "network", "chain", "chainid", "invalid_network"],
        "Network identifier (CAIP-2)",
        "All x402 'network' fields are CAIP-2: 'eip155:<chainId>' for EVM, 'solana:<cluster>' for Solana. Base mainnet = eip155:8453; Base Sepolia = eip155:84532. NOT 'base' or 'base-mainnet' or bare integer.",
        "Map your env NETWORK to a CAIP-2 string. Both paymentPayload.network AND paymentRequirements.network must match exactly.",
    ),
    (
        ["asset", "usdc", "wrong asset", "asset_address"],
        "Asset addresses per network",
        "USDC Base mainnet: 0x833589fcd6edb6e08f4c7c32d4f71b54bda02913. USDC Base Sepolia: 0x036cbd53842c5426634e7929541ec2318f3dcf7e. USDC Ethereum: 0xa0b86991c6218b266c1d19d4a2e9eb0ce3606eb48. USDC Polygon: 0x3c499c542cef5e3811e1192ce70d8cc03d5c3359. USDC Arbitrum: 0xaf88d065e77c8cc2239327c5edb3a432268e5831.",
        "Hardcode an asset table keyed by CAIP-2 network. Mismatched asset = 'invalid_exact_evm_payload' or 'unsupported_asset'.",
    ),
    (
        ["scheme", "exact", "upto", "permit2", "invalid_scheme", "unsupported_scheme"],
        "Payment schemes",
        "x402 supports 'exact' (fixed amount, EIP-3009) and 'upto' (variable up to maxAmountRequired). 'exact' is the universal default. Other schemes like 'permit2' are reserved.",
        "Both paymentPayload.scheme and paymentRequirements.scheme must match. Start with 'exact' — it works on every facilitator including CDP mainnet.",
    ),
    (
        ["jwt", "cdp", "ed25519", "edcdsa", "401", "auth"],
        "CDP facilitator JWT auth",
        "Coinbase's CDP /verify and /settle require a per-request Ed25519 JWT. Header {alg:EdDSA, kid:<CDP_API_KEY_ID>, typ:JWT, nonce:<rand16>}; claims {sub:<API_KEY_ID>, iss:cdp, aud:cdp_service, nbf:now, exp:now+120, uri:'POST api.cdp.coinbase.com/platform/v2/x402/verify'}.",
        "If your facilitator call gets HTTP 401 or bare HTTP 402 with no body, the JWT is wrong, missing, or expired. Mint a fresh JWT per request — exp=120s. Sign with Ed25519 from your CDP API secret.",
    ),
    (
        ["invalid_exact_evm_payload_signature", "signature", "signer", "recover", "ecrecover"],
        "Signature recovery",
        "Facilitator verifies that ecrecover(EIP-712 digest, signature) == authorization.from. Signature is 0x + 130 hex chars (r:32, s:32, v:1).",
        "If the recovered signer doesn't match authorization.from: check the EIP-712 domain (name + version + chainId + verifyingContract must match how USDC defines its domain). USDC 'version' on Base = '2'.",
    ),
    (
        ["isvalid", "invalidreason", "verify response"],
        "/verify response shape",
        "/verify returns HTTP 200 with {isValid: bool, invalidReason: string|null, payer: address}. invalidReason enum: insufficient_funds, invalid_exact_evm_payload, invalid_exact_evm_payload_authorization_valid_before/_after/_value, invalid_exact_evm_payload_signature, invalid_exact_evm_payload_recipient_mismatch, invalid_network, invalid_scheme, unsupported_scheme, invalid_payment_requirements, unexpected_verify_error.",
        "If /verify returned HTTP 200 + isValid:false → that's a payment problem (read invalidReason). If /verify returned bare HTTP 402 with empty body → that's an auth/schema problem upstream of the verifier.",
    ),
    (
        ["settle", "settlement", "x-payment-response", "payment-response"],
        "/settle and settlement receipts",
        "After successful /verify, the facilitator calls /settle which submits the EIP-3009 transferWithAuthorization on-chain. Successful tool response includes header 'X-PAYMENT-RESPONSE' (or 'PAYMENT-RESPONSE' in v2) with base64-encoded settlement receipt {success, transactionHash, network, payer, recipient}.",
        "Settlement happens AFTER your tool returns 200. Parse PAYMENT-RESPONSE to get the on-chain tx hash for audit logs.",
    ),
    (
        ["facilitator", "verify endpoint", "settle endpoint"],
        "Facilitator endpoints",
        "Standard facilitator API: POST /verify (validate payment without settling), POST /settle (submit to chain), GET /supported (advertise networks/schemes). Coinbase CDP: api.cdp.coinbase.com/platform/v2/x402/{verify,settle,supported}. Public x402.org facilitator: x402.org/facilitator/{verify,settle,supported} (Sepolia only).",
        "Choose your facilitator based on network: CDP for Base/EVM mainnet (requires JWT), x402.org for Sepolia testnet (no auth), Faremeter for Solana. See onyx_x402_facilitators for live status.",
    ),
    (
        ["maxamountrequired", "amount", "value", "underpay", "underpayment"],
        "Amount / maxAmountRequired",
        "paymentRequirements.maxAmountRequired and paymentPayload.payload.authorization.value are decimal strings of base units. USDC uses 6 decimals: $0.01 = '10000', $1.00 = '1000000'. value MUST be >= maxAmountRequired.",
        "Don't trust client-supplied value. Server reconstructs maxAmountRequired from the route's price and rejects if authorization.value is lower.",
    ),
    (
        ["bazaar", "discovery", "x402scan", "indexing"],
        "Discovery / Bazaar",
        "Coinbase's CDP discovery API (api.cdp.coinbase.com/platform/v2/x402/discovery/resources) indexes paid x402 services. Indexing criteria: server must respond to GET /openapi.json with an inputSchema in extra.inputSchema (or extensions.bazaar).",
        "If your endpoints aren't appearing in Bazaar after ~24h, check (1) openapi.json shows the route, (2) inputSchema is present in the 402 challenge under extra.inputSchema or extensions.bazaar.schema.",
    ),
    (
        ["oauth", "dcr", "dynamic client registration", "well-known"],
        "OAuth 2.1 DCR (MCP April 2026 spec)",
        "MCP 2026-04 spec mandates DCR for paid MCP servers to be visible to ChatGPT custom connectors and Claude Managed Agents. Required endpoints: /.well-known/oauth-authorization-server, /.well-known/oauth-protected-resource, POST /oauth/register, POST /oauth/token.",
        "Even if you don't gate by OAuth (payment is the gate), serve these endpoints with public 'client_id_issued_at' stubs. Without them, DCR-aware clients silently skip your server.",
    ),
]


def run(query: str, **_: object) -> dict:
    if not isinstance(query, str):
        raise ValueError("query must be a string")
    q = (query or "").strip().lower()
    if not q:
        raise ValueError("query is required")

    matches = []
    for keys, topic, spec, fix in _KNOWLEDGE:
        if any(k in q for k in keys):
            matches.append({"topic": topic, "spec": spec, "fix": fix, "keywords_matched": [k for k in keys if k in q]})

    if not matches:
        # Token-level fallback: split query, look for any token match
        tokens = [t for t in q.replace("-", " ").replace("_", " ").split() if t]
        for keys, topic, spec, fix in _KNOWLEDGE:
            if any(any(t in k or k in t for t in tokens) for k in keys):
                matches.append({"topic": topic, "spec": spec, "fix": fix, "keywords_matched": ["(fuzzy)"]})

    return {
        "ok": True,
        "query": query,
        "matches": matches,
        "match_count": len(matches),
        "all_topics": [topic for _, topic, _, _ in _KNOWLEDGE],
    }


run.__when_to_use__ = (
    "An agent or developer hit an x402 error, header name, status code, or feature "
    "they don't immediately recognize. One call returns the spec snippet + the fix."
)
run.__vs_alternatives__ = (
    "x402.org docs are good but require navigation; coinbase/x402 GitHub README is "
    "comprehensive but long. This tool returns the EXACT relevant snippet in one shot, "
    "machine-readable, suitable for agent decision-making mid-loop."
)
run.__example_request__ = {"query": "invalid_exact_evm_payload_authorization_valid_before"}
run.__example_response__ = {
    "ok": True,
    "query": "invalid_exact_evm_payload_authorization_valid_before",
    "match_count": 2,
    "matches": [
        {"topic": "/verify response shape", "spec": "...", "fix": "..."},
        {"topic": "EIP-3009 timing constraints", "spec": "...", "fix": "..."},
    ],
}
