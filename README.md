# Crypto MCP Server

> Give your AI agent real-time crypto intelligence. Prices, wallets, DeFi yields, DEX quotes — all through MCP.

[![PyPI](https://img.shields.io/pypi/v/crypto-mcp-server)](https://pypi.org/project/crypto-mcp-server/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An MCP (Model Context Protocol) server that connects AI agents to the crypto/DeFi ecosystem. Works with Claude Desktop, Claude Code, and any MCP-compatible client.

## What can it do?

Ask your AI assistant things like:
- *"What's the price of ETH right now?"*
- *"Show me the best USDC yield opportunities above 5% APY"*
- *"Check the balance of this wallet: 0xd8dA..."*
- *"Get me a swap quote for 1 ETH to USDC"*
- *"What's the gas price on Arbitrum?"*
- *"Show me trending tokens right now"*
- *"Deposit 1000 USDC into Aave on Arbitrum"*
- *"Auto-optimize my USDC yield across chains"*
- *"Show my DeFi positions on Aave V3"*

## Tools (23 total)

| Category | Tool | Description |
|----------|------|-------------|
| **Prices** | `crypto_price` | Real-time price, market cap, 24h change for any token |
| | `crypto_prices_batch` | Batch price query for multiple tokens |
| | `crypto_price_history` | Historical price data (1d to 1y) |
| | `trending_tokens` | Currently trending tokens across the market |
| **Wallet** | `wallet_balance` | All token balances + USD values for any EVM address |
| | `wallet_transactions` | Recent transaction history |
| **DeFi** | `defi_yields` | Best yield opportunities filtered by token, chain, APY |
| | `defi_protocol_tvl` | Top DeFi protocols ranked by TVL |
| **On-chain** | `gas_prices` | Current gas prices with cost estimates |
| | `token_info` | Detailed token data: supply, links, categories |
| | `whale_transactions` | Large transaction / whale activity tracking |
| **Swap** | `swap_quote` | Best swap quote across DEX aggregators |
| | `swap_compare` | Compare rates across multiple DEXes |
| **Actions** | `swap_execute` | Execute token swaps via ParaSwap |
| | `token_transfer` | Send ETH or ERC-20 tokens |
| | `token_approve` | Approve token spending for contracts |
| | `wrap_eth` | Wrap/unwrap ETH to WETH |
| **Portfolio** | `portfolio_summary` | Cross-chain portfolio overview |
| | `portfolio_history` | Historical portfolio tracking |
| **DeFi Mgmt** | `defi_deposit` | Deposit tokens into Aave V3 for yield |
| | `defi_withdraw` | Withdraw tokens from Aave V3 |
| | `defi_positions` | Check Aave V3 positions (collateral, debt, health) |
| | `auto_yield` | Auto-optimize yield across protocols |

## Supported Chains

Ethereum, Arbitrum, Base, Polygon, Optimism (and growing)

## Quick Start

### Install

```bash
pip install crypto-mcp-server
```

Or install from source:

```bash
git clone https://github.com/kms-kr/crypto-mcp-server.git
cd crypto-mcp-server
pip install -e .
```

For on-chain actions and DeFi management, install with web3 support:

```bash
pip install 'crypto-mcp-server[web3]'
```

### Claude Desktop

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "crypto": {
      "command": "crypto-mcp",
      "args": []
    }
  }
}
```

### Claude Code

```bash
claude mcp add crypto-mcp -- crypto-mcp
```

### Programmatic Usage

```python
from src.tools.prices import PriceTool
import asyncio

async def main():
    pt = PriceTool()
    price = await pt.get_price("BTC")
    print(price)
    # {'symbol': 'BTC', 'price': 70309, 'market_cap': 1406279032802, ...}

asyncio.run(main())
```

## Operator Setup (Revenue & Auth)

### Environment Variables

The server is configurable via environment variables. All are optional for basic usage.

| Variable | Description | Default |
|----------|-------------|---------|
| `WALLET_PRIVATE_KEY` | Private key for signing transactions (required for actions/DeFi) | - |
| `FEE_WALLET` | Operator wallet address that receives fees | - |
| `FEE_BPS` | Fee in basis points (10 = 0.1%) | `10` |
| `MAX_TX_VALUE_USD` | Maximum single transaction value in USD | `10000` |
| `REQUIRE_AUTH` | Set to `true` to enforce API key authentication | `false` |
| `API_KEYS` | Comma-separated list of valid paid-tier API keys | - |

### Revenue / Fee Structure

When `FEE_WALLET` is set, the server collects a small fee on revenue-generating operations:

- **Swap execution** (`swap_execute`): Fee is deducted from the input amount before the swap.
- **DeFi deposits** (`defi_deposit`, `auto_yield`): Fee is deducted before depositing into the protocol.
- **Default fee**: 0.1% (10 basis points). Configurable via `FEE_BPS`.
- **Fee collection**: Fees are sent on-chain to `FEE_WALLET` as a separate transaction.
- **Fee tracking**: In-memory stats available via the `FeeManager.get_fee_stats()` API.

Example operator setup:

```bash
export FEE_WALLET="0xYourWalletAddress"
export FEE_BPS=10          # 0.1% fee
export WALLET_PRIVATE_KEY="0x..."
```

### Authentication & Rate Limiting

When `REQUIRE_AUTH=true`, the server enforces tiered rate limits:

| Tier | API Key Required | Daily Limit |
|------|-----------------|-------------|
| **Free** | No | 100 calls/day |
| **Paid** | Yes | 10,000 calls/day |

To set up paid-tier keys:

```bash
export REQUIRE_AUTH=true
export API_KEYS="key1-abc-123,key2-def-456,key3-ghi-789"
```

Callers pass `api_key` in their tool arguments to authenticate. When auth is not required (default), all tools work without a key and usage is still tracked.

### DeFi Management Tools

The DeFi management tools interact with **Aave V3** on supported chains:

- **`defi_deposit`**: Approves and supplies tokens to Aave V3. Earns lending yield automatically.
- **`defi_withdraw`**: Withdraws supplied tokens. Use `amount: -1` for max withdrawal.
- **`defi_positions`**: Read-only query of collateral, debt, health factor, and liquidation threshold.
- **`auto_yield`**: The killer feature -- queries all DeFi protocols for the best APY, compares with current positions, and automatically deposits into Aave V3. If a better yield exists on another protocol, it provides recommendations.

Supported Aave V3 chains: Ethereum, Arbitrum, Base, Polygon.

## Data Sources

All free, no API keys required:

| Source | Data |
|--------|------|
| [CoinGecko](https://www.coingecko.com/) | Prices, token info, trending |
| [DeFiLlama](https://defillama.com/) | DeFi yields, protocol TVL |
| [ParaSwap](https://www.paraswap.io/) | DEX swap quotes & execution |
| [Ankr](https://www.ankr.com/) | Wallet balances |
| [Aave V3](https://aave.com/) | DeFi deposits, withdrawals, positions |
| Public RPCs | Gas prices, native balances |

## Roadmap

- [x] Phase 1: Data & analytics (prices, wallets, DeFi, swap quotes)
- [x] Phase 2: On-chain actions (execute swaps, token transfers, approvals)
- [x] Phase 3: Monetization + DeFi management (fees, auth, Aave V3, auto-yield)
- [ ] Phase 4: Cross-chain bridging, multi-protocol DeFi, advanced strategies

## License

MIT
