"""Price data tools - powered by CoinGecko free API."""
import httpx
from typing import Dict, List, Optional


# CoinGecko symbol -> id mapping (top tokens, expandable)
SYMBOL_MAP = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana",
    "BNB": "binancecoin", "XRP": "ripple", "ADA": "cardano",
    "DOGE": "dogecoin", "AVAX": "avalanche-2", "DOT": "polkadot",
    "MATIC": "matic-network", "LINK": "chainlink", "UNI": "uniswap",
    "AAVE": "aave", "MKR": "maker", "LDO": "lido-dao",
    "ARB": "arbitrum", "OP": "optimism", "PEPE": "pepe",
    "SHIB": "shiba-inu", "WIF": "dogwifcoin", "BONK": "bonk",
    "USDC": "usd-coin", "USDT": "tether", "DAI": "dai",
    "WBTC": "wrapped-bitcoin", "WETH": "weth", "STETH": "staked-ether",
    "RETH": "rocket-pool-eth", "CRV": "curve-dao-token",
    "COMP": "compound-governance-token", "SNX": "havven",
    "SUSHI": "sushi", "1INCH": "1inch", "GMX": "gmx",
    "PENDLE": "pendle", "ENA": "ethena", "EIGEN": "eigenlayer",
    "TIA": "celestia", "SUI": "sui", "APT": "aptos",
    "SEI": "sei-network", "INJ": "injective-protocol",
    "FET": "fetch-ai", "RENDER": "render-token", "TAO": "bittensor",
    "NEAR": "near", "ATOM": "cosmos", "FTM": "fantom",
    "TON": "the-open-network", "TRX": "tron",
}

COINGECKO_BASE = "https://api.coingecko.com/api/v3"


class PriceTool:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=15)

    def _resolve_id(self, symbol: str) -> str:
        """Resolve symbol to CoinGecko ID."""
        s = symbol.upper().strip()
        return SYMBOL_MAP.get(s, s.lower())

    async def get_price(self, symbol: str, currency: str = "usd") -> Dict:
        """Get current price + 24h change for a token."""
        coin_id = self._resolve_id(symbol)
        resp = await self.client.get(
            f"{COINGECKO_BASE}/simple/price",
            params={
                "ids": coin_id,
                "vs_currencies": currency,
                "include_24hr_change": "true",
                "include_24hr_vol": "true",
                "include_market_cap": "true",
            },
        )
        resp.raise_for_status()
        data = resp.json()

        if coin_id not in data:
            # Try search
            search = await self._search_coin(symbol)
            if search:
                return await self.get_price(search, currency)
            return {"error": f"Token '{symbol}' not found"}

        info = data[coin_id]
        cur = currency.lower()
        return {
            "symbol": symbol.upper(),
            "price": info.get(cur, 0),
            "market_cap": info.get(f"{cur}_market_cap", 0),
            "volume_24h": info.get(f"{cur}_24h_vol", 0),
            "change_24h_pct": round(info.get(f"{cur}_24h_change", 0), 2),
            "currency": currency.upper(),
        }

    async def get_prices_batch(self, symbols: List[str], currency: str = "usd") -> Dict:
        """Get prices for multiple tokens in one call."""
        coin_ids = [self._resolve_id(s) for s in symbols]
        resp = await self.client.get(
            f"{COINGECKO_BASE}/simple/price",
            params={
                "ids": ",".join(coin_ids),
                "vs_currencies": currency,
                "include_24hr_change": "true",
                "include_market_cap": "true",
            },
        )
        resp.raise_for_status()
        data = resp.json()

        results = {}
        cur = currency.lower()
        for symbol, coin_id in zip(symbols, coin_ids):
            if coin_id in data:
                info = data[coin_id]
                results[symbol.upper()] = {
                    "price": info.get(cur, 0),
                    "market_cap": info.get(f"{cur}_market_cap", 0),
                    "change_24h_pct": round(info.get(f"{cur}_24h_change", 0), 2),
                }
            else:
                results[symbol.upper()] = {"error": "not found"}

        return {"prices": results, "currency": currency.upper()}

    async def get_price_history(self, symbol: str, days: int = 7) -> Dict:
        """Get price history for charting/analysis."""
        coin_id = self._resolve_id(symbol)
        resp = await self.client.get(
            f"{COINGECKO_BASE}/coins/{coin_id}/market_chart",
            params={"vs_currency": "usd", "days": days},
        )
        resp.raise_for_status()
        data = resp.json()

        prices = data.get("prices", [])
        if not prices:
            return {"error": f"No history for '{symbol}'"}

        # Summarize: first, last, high, low, data points
        price_vals = [p[1] for p in prices]
        return {
            "symbol": symbol.upper(),
            "days": days,
            "current": price_vals[-1],
            "open": price_vals[0],
            "high": max(price_vals),
            "low": min(price_vals),
            "change_pct": round((price_vals[-1] - price_vals[0]) / price_vals[0] * 100, 2),
            "data_points": len(prices),
            "prices": [
                {"timestamp": p[0], "price": round(p[1], 6)}
                for p in prices[::max(1, len(prices) // 50)]  # Max 50 points
            ],
        }

    async def get_trending(self) -> Dict:
        """Get trending tokens."""
        resp = await self.client.get(f"{COINGECKO_BASE}/search/trending")
        resp.raise_for_status()
        data = resp.json()

        coins = []
        for item in data.get("coins", [])[:15]:
            c = item.get("item", {})
            coins.append({
                "name": c.get("name"),
                "symbol": c.get("symbol"),
                "market_cap_rank": c.get("market_cap_rank"),
                "price_btc": c.get("price_btc"),
                "score": c.get("score"),
            })

        return {"trending": coins}

    async def _search_coin(self, query: str) -> Optional[str]:
        """Search for a coin ID by name/symbol."""
        resp = await self.client.get(
            f"{COINGECKO_BASE}/search",
            params={"query": query},
        )
        if resp.status_code == 200:
            coins = resp.json().get("coins", [])
            if coins:
                return coins[0]["id"]
        return None
