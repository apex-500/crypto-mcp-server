"""Crypto MCP Server - AI agents' gateway to crypto/DeFi.

Provides tools for:
- Real-time price data (any token, any chain)
- Wallet portfolio analysis
- DEX swap quotes & optimal routing
- On-chain analytics (gas, trending tokens, whale alerts)
- DeFi protocol data (yields, TVL, lending rates)
- On-chain actions (swap execution, transfers, approvals, wrapping)
- Portfolio aggregation across chains
- DeFi management (deposits, withdrawals, positions, auto-yield)
- Revenue collection via FeeManager
- API key auth and rate limiting
"""
import asyncio
import json
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .tools.prices import PriceTool
from .tools.wallet import WalletTool
from .tools.defi import DeFiTool
from .tools.onchain import OnChainTool
from .tools.swap import SwapTool
from .tools.fee_manager import FeeManager
from .tools.actions import ActionTool
from .tools.portfolio import PortfolioTool
from .tools.defi_actions import DefiActionTool
from .auth import AuthManager


app = Server("crypto-mcp-server")

# Initialize shared components
fee_manager = FeeManager()
auth_manager = AuthManager()

# Initialize tool handlers
price_tool = PriceTool()
wallet_tool = WalletTool()
defi_tool = DeFiTool()
onchain_tool = OnChainTool()
swap_tool = SwapTool()
action_tool = ActionTool(fee_manager=fee_manager)
portfolio_tool = PortfolioTool(wallet_tool=wallet_tool)
defi_action_tool = DefiActionTool(fee_manager=fee_manager)


TOOLS = [
    # --- Price Tools ---
    Tool(
        name="crypto_price",
        description="Get real-time price for any cryptocurrency. Supports 10,000+ tokens.",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Token symbol (e.g., 'BTC', 'ETH', 'SOL', 'PEPE')",
                },
                "currency": {
                    "type": "string",
                    "description": "Quote currency (default: 'usd')",
                    "default": "usd",
                },
            },
            "required": ["symbol"],
        },
    ),
    Tool(
        name="crypto_prices_batch",
        description="Get prices for multiple cryptocurrencies at once. Efficient batch query.",
        inputSchema={
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of token symbols (e.g., ['BTC', 'ETH', 'SOL'])",
                },
                "currency": {
                    "type": "string",
                    "default": "usd",
                },
            },
            "required": ["symbols"],
        },
    ),
    Tool(
        name="crypto_price_history",
        description="Get historical price data for a token. Useful for trend analysis.",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Token symbol"},
                "days": {
                    "type": "integer",
                    "description": "Number of days of history (1, 7, 30, 90, 365)",
                    "default": 7,
                },
            },
            "required": ["symbol"],
        },
    ),
    Tool(
        name="trending_tokens",
        description="Get currently trending tokens across the crypto market.",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    # --- Wallet Tools ---
    Tool(
        name="wallet_balance",
        description="Get all token balances for an Ethereum/EVM wallet address. Shows ETH + all ERC-20 tokens with USD values.",
        inputSchema={
            "type": "object",
            "properties": {
                "address": {
                    "type": "string",
                    "description": "Wallet address (0x...)",
                },
                "chain": {
                    "type": "string",
                    "description": "Chain name: 'ethereum', 'arbitrum', 'base', 'polygon', 'optimism'",
                    "default": "ethereum",
                },
            },
            "required": ["address"],
        },
    ),
    Tool(
        name="wallet_transactions",
        description="Get recent transactions for a wallet address.",
        inputSchema={
            "type": "object",
            "properties": {
                "address": {"type": "string", "description": "Wallet address"},
                "chain": {"type": "string", "default": "ethereum"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["address"],
        },
    ),
    # --- DeFi Tools ---
    Tool(
        name="defi_yields",
        description="Find the best DeFi yield opportunities across protocols. Filter by token, chain, or minimum APY.",
        inputSchema={
            "type": "object",
            "properties": {
                "token": {
                    "type": "string",
                    "description": "Filter by token (e.g., 'USDC', 'ETH'). Optional.",
                },
                "chain": {
                    "type": "string",
                    "description": "Filter by chain. Optional.",
                },
                "min_apy": {
                    "type": "number",
                    "description": "Minimum APY percentage. Optional.",
                },
                "min_tvl": {
                    "type": "number",
                    "description": "Minimum TVL in USD. Default: 100000",
                    "default": 100000,
                },
                "limit": {"type": "integer", "default": 10},
            },
        },
    ),
    Tool(
        name="defi_protocol_tvl",
        description="Get Total Value Locked (TVL) for DeFi protocols. Ranked by size.",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 20},
            },
        },
    ),
    # --- On-chain Tools ---
    Tool(
        name="gas_prices",
        description="Get current gas prices for EVM chains. Shows slow/standard/fast estimates.",
        inputSchema={
            "type": "object",
            "properties": {
                "chain": {
                    "type": "string",
                    "description": "Chain: 'ethereum', 'arbitrum', 'base', 'polygon'",
                    "default": "ethereum",
                },
            },
        },
    ),
    Tool(
        name="token_info",
        description="Get detailed information about a token: contract address, market cap, supply, description, links.",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Token symbol"},
            },
            "required": ["symbol"],
        },
    ),
    Tool(
        name="whale_transactions",
        description="Get recent large transactions (whale movements) for a token.",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Token symbol (e.g., 'BTC', 'ETH')",
                },
                "min_usd": {
                    "type": "number",
                    "description": "Minimum transaction value in USD",
                    "default": 1000000,
                },
            },
            "required": ["symbol"],
        },
    ),
    # --- Swap Tools ---
    Tool(
        name="swap_quote",
        description="Get the best swap quote across DEXes. Shows optimal route, expected output, price impact, and gas cost.",
        inputSchema={
            "type": "object",
            "properties": {
                "from_token": {
                    "type": "string",
                    "description": "Token to sell (symbol or address)",
                },
                "to_token": {
                    "type": "string",
                    "description": "Token to buy (symbol or address)",
                },
                "amount": {
                    "type": "number",
                    "description": "Amount of from_token to swap",
                },
                "chain": {
                    "type": "string",
                    "default": "ethereum",
                },
            },
            "required": ["from_token", "to_token", "amount"],
        },
    ),
    Tool(
        name="swap_compare",
        description="Compare swap rates across multiple DEXes for the same trade.",
        inputSchema={
            "type": "object",
            "properties": {
                "from_token": {"type": "string"},
                "to_token": {"type": "string"},
                "amount": {"type": "number"},
                "chain": {"type": "string", "default": "ethereum"},
            },
            "required": ["from_token", "to_token", "amount"],
        },
    ),
    # --- Action Tools (Phase 2: On-chain Execution) ---
    Tool(
        name="swap_execute",
        description=(
            "Execute a token swap on a DEX. Builds and sends the transaction via ParaSwap. "
            "Requires WALLET_PRIVATE_KEY env var. A fee (default 0.1%) is applied to swaps. "
            "Safety: max $10k per tx (configurable), 1% slippage protection, gas price sanity checks."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "from_token": {
                    "type": "string",
                    "description": "Token to sell (symbol like 'ETH', 'USDC' or contract address)",
                },
                "to_token": {
                    "type": "string",
                    "description": "Token to buy (symbol or contract address)",
                },
                "amount": {
                    "type": "number",
                    "description": "Amount of from_token to swap",
                },
                "chain": {
                    "type": "string",
                    "description": "Chain: 'ethereum', 'arbitrum', 'base', 'polygon'",
                    "default": "ethereum",
                },
                "slippage_bps": {
                    "type": "integer",
                    "description": "Slippage tolerance in basis points (100 = 1%). Default: 100",
                    "default": 100,
                },
                "fee_bps": {
                    "type": "integer",
                    "description": "Fee in basis points (10 = 0.1%). Default from FEE_BPS env or 10",
                },
            },
            "required": ["from_token", "to_token", "amount"],
        },
    ),
    Tool(
        name="token_transfer",
        description=(
            "Send tokens (ETH, ERC-20) to an address. Requires WALLET_PRIVATE_KEY env var. "
            "Safety: max $10k per tx (configurable), gas price sanity checks."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "token": {
                    "type": "string",
                    "description": "Token to send (symbol like 'ETH', 'USDC' or contract address)",
                },
                "to_address": {
                    "type": "string",
                    "description": "Recipient wallet address (0x...)",
                },
                "amount": {
                    "type": "number",
                    "description": "Amount to send",
                },
                "chain": {
                    "type": "string",
                    "description": "Chain: 'ethereum', 'arbitrum', 'base', 'polygon'",
                    "default": "ethereum",
                },
            },
            "required": ["token", "to_address", "amount"],
        },
    ),
    Tool(
        name="token_approve",
        description=(
            "Approve a contract to spend tokens on your behalf. Required before swaps/DeFi interactions. "
            "If amount is omitted, grants unlimited approval. Requires WALLET_PRIVATE_KEY env var."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "token": {
                    "type": "string",
                    "description": "Token to approve (symbol or contract address)",
                },
                "spender": {
                    "type": "string",
                    "description": "Contract address to approve as spender (0x...)",
                },
                "amount": {
                    "type": "number",
                    "description": "Amount to approve. Omit for unlimited approval.",
                },
                "chain": {
                    "type": "string",
                    "description": "Chain: 'ethereum', 'arbitrum', 'base', 'polygon'",
                    "default": "ethereum",
                },
            },
            "required": ["token", "spender"],
        },
    ),
    Tool(
        name="wrap_eth",
        description=(
            "Wrap ETH to WETH or unwrap WETH to ETH. WETH is needed for many DeFi interactions. "
            "Requires WALLET_PRIVATE_KEY env var."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "amount": {
                    "type": "number",
                    "description": "Amount of ETH to wrap/unwrap",
                },
                "direction": {
                    "type": "string",
                    "description": "'wrap' (ETH->WETH) or 'unwrap' (WETH->ETH). Default: 'wrap'",
                    "default": "wrap",
                    "enum": ["wrap", "unwrap"],
                },
                "chain": {
                    "type": "string",
                    "description": "Chain: 'ethereum', 'arbitrum', 'base', 'polygon'",
                    "default": "ethereum",
                },
            },
            "required": ["amount"],
        },
    ),
    # --- Portfolio Tools ---
    Tool(
        name="portfolio_summary",
        description=(
            "Get a complete portfolio overview for a wallet across all supported chains. "
            "Shows total value, per-chain breakdown, token allocation percentages, and top holdings."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "address": {
                    "type": "string",
                    "description": "Wallet address (0x...)",
                },
                "chains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Chains to scan (default: all supported). E.g., ['ethereum', 'arbitrum']",
                },
            },
            "required": ["address"],
        },
    ),
    Tool(
        name="portfolio_history",
        description=(
            "Track portfolio value and activity over time for a wallet. "
            "Shows current value, transaction activity, net flows, and top holdings."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "address": {
                    "type": "string",
                    "description": "Wallet address (0x...)",
                },
                "days": {
                    "type": "integer",
                    "description": "Number of days to look back. Default: 30",
                    "default": 30,
                },
                "chain": {
                    "type": "string",
                    "description": "Chain to analyze. Default: 'ethereum'",
                    "default": "ethereum",
                },
            },
            "required": ["address"],
        },
    ),
    # --- DeFi Management Tools (Phase 3: Monetization + DeFi) ---
    Tool(
        name="defi_deposit",
        description=(
            "Deposit tokens into Aave V3 to earn yield. Automatically approves and supplies tokens. "
            "A fee (default 0.1%) is deducted before deposit. "
            "Supported chains: ethereum, arbitrum, base, polygon. "
            "Requires WALLET_PRIVATE_KEY env var."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "token": {
                    "type": "string",
                    "description": "Token to deposit (symbol like 'USDC', 'WETH' or contract address)",
                },
                "amount": {
                    "type": "number",
                    "description": "Amount of token to deposit",
                },
                "chain": {
                    "type": "string",
                    "description": "Chain: 'ethereum', 'arbitrum', 'base', 'polygon'",
                    "default": "ethereum",
                },
                "fee_bps": {
                    "type": "integer",
                    "description": "Fee in basis points (10 = 0.1%). Default from FEE_BPS env or 10",
                },
            },
            "required": ["token", "amount"],
        },
    ),
    Tool(
        name="defi_withdraw",
        description=(
            "Withdraw tokens from Aave V3. Use amount=-1 to withdraw the maximum available. "
            "Supported chains: ethereum, arbitrum, base, polygon. "
            "Requires WALLET_PRIVATE_KEY env var."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "token": {
                    "type": "string",
                    "description": "Token to withdraw (symbol like 'USDC', 'WETH' or contract address)",
                },
                "amount": {
                    "type": "number",
                    "description": "Amount to withdraw. Use -1 for max withdrawal.",
                },
                "chain": {
                    "type": "string",
                    "description": "Chain: 'ethereum', 'arbitrum', 'base', 'polygon'",
                    "default": "ethereum",
                },
            },
            "required": ["token", "amount"],
        },
    ),
    Tool(
        name="defi_positions",
        description=(
            "Check current DeFi positions on Aave V3. Shows total collateral, debt, "
            "available borrows, health factor, and liquidation threshold. "
            "If no address is given, uses the configured wallet."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "address": {
                    "type": "string",
                    "description": "Wallet address to check (0x...). Optional - defaults to configured wallet.",
                },
                "chain": {
                    "type": "string",
                    "description": "Chain: 'ethereum', 'arbitrum', 'base', 'polygon'",
                    "default": "ethereum",
                },
            },
        },
    ),
    Tool(
        name="auto_yield",
        description=(
            "Automatically find and deposit into the best yield opportunity for a token. "
            "Queries all DeFi protocols for the best APY, compares with current position, "
            "and deposits into Aave V3 (with recommendations if better yields exist elsewhere). "
            "This is the AI agent's auto-yield optimizer. "
            "Requires WALLET_PRIVATE_KEY env var."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "token": {
                    "type": "string",
                    "description": "Token to optimize yield for (e.g., 'USDC', 'WETH')",
                },
                "amount": {
                    "type": "number",
                    "description": "Amount of token to deposit",
                },
                "chain": {
                    "type": "string",
                    "description": "Preferred chain: 'ethereum', 'arbitrum', 'base', 'polygon'",
                    "default": "ethereum",
                },
                "min_apy_improvement": {
                    "type": "number",
                    "description": "Minimum APY improvement (%) to trigger a move. Default: 0.5",
                    "default": 0.5,
                },
                "fee_bps": {
                    "type": "integer",
                    "description": "Fee in basis points (10 = 0.1%). Default from FEE_BPS env or 10",
                },
            },
            "required": ["token", "amount"],
        },
    ),
]


@app.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Route tool calls to appropriate handlers."""
    try:
        # --- Auth check ---
        api_key = arguments.pop("api_key", None)
        if auth_manager.require_auth:
            allowed, tier, remaining = auth_manager.check_auth(api_key)
            if not allowed:
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "error": "Rate limit exceeded",
                        "tier": tier,
                        "remaining": 0,
                        "hint": "Upgrade to paid tier with an API key for higher limits."
                        if tier == "free" else "Daily limit reached. Try again tomorrow.",
                    }),
                )]
        # Track usage regardless of auth requirement
        auth_manager.track_usage(api_key)

        # Price tools
        if name == "crypto_price":
            result = await price_tool.get_price(
                arguments["symbol"],
                arguments.get("currency", "usd"),
            )
        elif name == "crypto_prices_batch":
            result = await price_tool.get_prices_batch(
                arguments["symbols"],
                arguments.get("currency", "usd"),
            )
        elif name == "crypto_price_history":
            result = await price_tool.get_price_history(
                arguments["symbol"],
                arguments.get("days", 7),
            )
        elif name == "trending_tokens":
            result = await price_tool.get_trending()

        # Wallet tools
        elif name == "wallet_balance":
            result = await wallet_tool.get_balance(
                arguments["address"],
                arguments.get("chain", "ethereum"),
            )
        elif name == "wallet_transactions":
            result = await wallet_tool.get_transactions(
                arguments["address"],
                arguments.get("chain", "ethereum"),
                arguments.get("limit", 10),
            )

        # DeFi tools
        elif name == "defi_yields":
            result = await defi_tool.get_yields(
                token=arguments.get("token"),
                chain=arguments.get("chain"),
                min_apy=arguments.get("min_apy"),
                min_tvl=arguments.get("min_tvl", 100000),
                limit=arguments.get("limit", 10),
            )
        elif name == "defi_protocol_tvl":
            result = await defi_tool.get_protocol_tvl(
                limit=arguments.get("limit", 20),
            )

        # On-chain tools
        elif name == "gas_prices":
            result = await onchain_tool.get_gas_prices(
                arguments.get("chain", "ethereum"),
            )
        elif name == "token_info":
            result = await onchain_tool.get_token_info(arguments["symbol"])
        elif name == "whale_transactions":
            result = await onchain_tool.get_whale_transactions(
                arguments["symbol"],
                arguments.get("min_usd", 1_000_000),
            )

        # Swap tools
        elif name == "swap_quote":
            result = await swap_tool.get_quote(
                arguments["from_token"],
                arguments["to_token"],
                arguments["amount"],
                arguments.get("chain", "ethereum"),
            )
        elif name == "swap_compare":
            result = await swap_tool.compare_dexes(
                arguments["from_token"],
                arguments["to_token"],
                arguments["amount"],
                arguments.get("chain", "ethereum"),
            )

        # Action tools (Phase 2)
        elif name == "swap_execute":
            result = await action_tool.swap_execute(
                arguments["from_token"],
                arguments["to_token"],
                arguments["amount"],
                chain=arguments.get("chain", "ethereum"),
                slippage_bps=arguments.get("slippage_bps", 100),
                fee_bps=arguments.get("fee_bps"),
            )
        elif name == "token_transfer":
            result = await action_tool.token_transfer(
                arguments["token"],
                arguments["to_address"],
                arguments["amount"],
                chain=arguments.get("chain", "ethereum"),
            )
        elif name == "token_approve":
            result = await action_tool.token_approve(
                arguments["token"],
                arguments["spender"],
                amount=arguments.get("amount"),
                chain=arguments.get("chain", "ethereum"),
            )
        elif name == "wrap_eth":
            result = await action_tool.wrap_eth(
                arguments["amount"],
                direction=arguments.get("direction", "wrap"),
                chain=arguments.get("chain", "ethereum"),
            )

        # Portfolio tools
        elif name == "portfolio_summary":
            result = await portfolio_tool.portfolio_summary(
                arguments["address"],
                chains=arguments.get("chains"),
            )
        elif name == "portfolio_history":
            result = await portfolio_tool.portfolio_history(
                arguments["address"],
                days=arguments.get("days", 30),
                chain=arguments.get("chain", "ethereum"),
            )

        # DeFi management tools (Phase 3)
        elif name == "defi_deposit":
            result = await defi_action_tool.defi_deposit(
                arguments["token"],
                arguments["amount"],
                chain=arguments.get("chain", "ethereum"),
                fee_bps=arguments.get("fee_bps"),
            )
        elif name == "defi_withdraw":
            result = await defi_action_tool.defi_withdraw(
                arguments["token"],
                arguments["amount"],
                chain=arguments.get("chain", "ethereum"),
            )
        elif name == "defi_positions":
            result = await defi_action_tool.defi_positions(
                address=arguments.get("address"),
                chain=arguments.get("chain", "ethereum"),
            )
        elif name == "auto_yield":
            result = await defi_action_tool.auto_yield(
                arguments["token"],
                arguments["amount"],
                chain=arguments.get("chain", "ethereum"),
                min_apy_improvement=arguments.get("min_apy_improvement", 0.5),
                fee_bps=arguments.get("fee_bps"),
            )
        else:
            result = {"error": f"Unknown tool: {name}"}

        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as e:
        return [TextContent(
            type="text",
            text=json.dumps({"error": str(e)}),
        )]


def main():
    """Run the MCP server."""
    asyncio.run(run())


async def run():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    main()
