"""On-chain analytics tools."""
import httpx
from typing import Dict, Optional


COINGECKO_BASE = "https://api.coingecko.com/api/v3"

# Symbol -> CoinGecko ID (reuse from prices)
from .prices import SYMBOL_MAP


class OnChainTool:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=15)

    async def get_gas_prices(self, chain: str = "ethereum") -> Dict:
        """Get current gas prices."""
        chain = chain.lower()

        if chain == "ethereum":
            # Use public ETH RPC for gas estimate
            try:
                resp = await self.client.post(
                    "https://eth.llamarpc.com",
                    json={
                        "jsonrpc": "2.0",
                        "method": "eth_gasPrice",
                        "params": [],
                        "id": 1,
                    },
                )
                resp.raise_for_status()
                gas_wei = int(resp.json().get("result", "0x0"), 16)
                gas_gwei = gas_wei / 1e9

                return {
                    "chain": "ethereum",
                    "gas_gwei": round(gas_gwei, 2),
                    "estimates": {
                        "transfer_eth": f"${round(gas_gwei * 21000 / 1e9 * 3500, 2)}",
                        "swap_uniswap": f"${round(gas_gwei * 150000 / 1e9 * 3500, 2)}",
                        "nft_mint": f"${round(gas_gwei * 200000 / 1e9 * 3500, 2)}",
                    },
                    "note": "Estimates assume ETH ~$3,500. Actual costs vary.",
                }
            except Exception as e:
                return {"chain": chain, "error": str(e)}

        # L2 chains - gas is very cheap
        rpc_urls = {
            "arbitrum": "https://arb1.arbitrum.io/rpc",
            "base": "https://mainnet.base.org",
            "polygon": "https://polygon-rpc.com",
            "optimism": "https://mainnet.optimism.io",
        }
        rpc = rpc_urls.get(chain)
        if not rpc:
            return {"error": f"Chain '{chain}' not supported"}

        try:
            resp = await self.client.post(
                rpc,
                json={"jsonrpc": "2.0", "method": "eth_gasPrice", "params": [], "id": 1},
            )
            resp.raise_for_status()
            gas_wei = int(resp.json().get("result", "0x0"), 16)
            gas_gwei = gas_wei / 1e9

            return {
                "chain": chain,
                "gas_gwei": round(gas_gwei, 4),
                "note": f"L2 gas is typically very cheap (~$0.01-0.10 per tx)",
            }
        except Exception as e:
            return {"chain": chain, "error": str(e)}

    async def get_token_info(self, symbol: str) -> Dict:
        """Get detailed token information."""
        s = symbol.upper().strip()
        coin_id = SYMBOL_MAP.get(s, s.lower())

        try:
            resp = await self.client.get(
                f"{COINGECKO_BASE}/coins/{coin_id}",
                params={
                    "localization": "false",
                    "tickers": "false",
                    "community_data": "false",
                    "developer_data": "false",
                },
            )
            resp.raise_for_status()
            data = resp.json()

            market = data.get("market_data", {})
            return {
                "name": data.get("name"),
                "symbol": data.get("symbol", "").upper(),
                "description": (data.get("description", {}).get("en", "") or "")[:500],
                "market_cap_rank": data.get("market_cap_rank"),
                "price_usd": market.get("current_price", {}).get("usd"),
                "market_cap": market.get("market_cap", {}).get("usd"),
                "fully_diluted_valuation": market.get("fully_diluted_valuation", {}).get("usd"),
                "total_volume": market.get("total_volume", {}).get("usd"),
                "circulating_supply": market.get("circulating_supply"),
                "total_supply": market.get("total_supply"),
                "max_supply": market.get("max_supply"),
                "ath": market.get("ath", {}).get("usd"),
                "ath_change_pct": market.get("ath_change_percentage", {}).get("usd"),
                "atl": market.get("atl", {}).get("usd"),
                "chains": list((data.get("platforms", {}) or {}).keys())[:5],
                "categories": data.get("categories", [])[:5],
                "links": {
                    "website": (data.get("links", {}).get("homepage", [""]) or [""])[0],
                    "twitter": data.get("links", {}).get("twitter_screen_name"),
                    "github": (data.get("links", {}).get("repos_url", {}).get("github", [""]) or [""])[0],
                },
            }
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return {"error": f"Token '{symbol}' not found"}
            return {"error": str(e)}

    async def get_whale_transactions(self, symbol: str, min_usd: float = 1_000_000) -> Dict:
        """Get large holder/whale data for a token.

        Uses CoinGecko market data as proxy for whale activity
        (real whale tracking would need Etherscan/Nansen API).
        """
        s = symbol.upper().strip()
        coin_id = SYMBOL_MAP.get(s, s.lower())

        try:
            # Get market data including large holder stats
            resp = await self.client.get(
                f"{COINGECKO_BASE}/coins/{coin_id}",
                params={
                    "localization": "false",
                    "tickers": "true",
                    "community_data": "false",
                    "developer_data": "false",
                },
            )
            resp.raise_for_status()
            data = resp.json()

            market = data.get("market_data", {})
            tickers = data.get("tickers", [])[:10]

            # Top exchanges by volume (proxy for where whales trade)
            top_exchanges = []
            for t in tickers:
                vol = t.get("converted_volume", {}).get("usd", 0)
                if vol > 0:
                    top_exchanges.append({
                        "exchange": t.get("market", {}).get("name", ""),
                        "pair": t.get("target", ""),
                        "volume_24h_usd": round(vol),
                        "spread_pct": round(t.get("bid_ask_spread_percentage", 0) or 0, 4),
                        "trust_score": t.get("trust_score", ""),
                    })

            top_exchanges.sort(key=lambda x: x["volume_24h_usd"], reverse=True)

            return {
                "symbol": symbol.upper(),
                "total_volume_24h": market.get("total_volume", {}).get("usd", 0),
                "market_cap": market.get("market_cap", {}).get("usd", 0),
                "circulating_supply": market.get("circulating_supply", 0),
                "top_exchanges": top_exchanges[:5],
                "note": "For real-time whale transaction tracking, integrate Etherscan/Whale Alert API.",
                "suggestion": "Large volume on low-spread exchanges typically indicates institutional/whale activity.",
            }
        except Exception as e:
            return {"error": str(e)}
