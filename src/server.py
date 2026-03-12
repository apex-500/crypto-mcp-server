"""Crypto MCP Server - AI agents' gateway to crypto/DeFi.

Provides tools for:
- Real-time price data (any token, any chain)
- Wallet portfolio analysis
- DEX swap quotes & optimal routing
- On-chain analytics (gas, trending tokens, whale alerts)
- DeFi protocol data (yields, TVL, lending rates)
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


app = Server("crypto-mcp-server")

# Initialize tool handlers
price_tool = PriceTool()
wallet_tool = WalletTool()
defi_tool = DeFiTool()
onchain_tool = OnChainTool()
swap_tool = SwapTool()


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
]


@app.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Route tool calls to appropriate handlers."""
    try:
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
