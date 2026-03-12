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

## Tools (13 total)

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

## Data Sources

All free, no API keys required:

| Source | Data |
|--------|------|
| [CoinGecko](https://www.coingecko.com/) | Prices, token info, trending |
| [DeFiLlama](https://defillama.com/) | DeFi yields, protocol TVL |
| [ParaSwap](https://www.paraswap.io/) | DEX swap quotes |
| [Ankr](https://www.ankr.com/) | Wallet balances |
| Public RPCs | Gas prices, native balances |

## Roadmap

- [x] Phase 1: Data & analytics (prices, wallets, DeFi, swap quotes)
- [ ] Phase 2: On-chain actions (execute swaps, token transfers)
- [ ] Phase 3: Multi-chain DeFi management (auto-yield, rebalancing)

## License

MIT
