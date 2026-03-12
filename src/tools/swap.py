"""DEX swap tools - quotes and route comparison across DEXes."""
import httpx
from typing import Dict, Optional


# Popular token addresses on Ethereum mainnet
TOKEN_ADDRESSES = {
    "ETH": "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
    "WETH": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
    "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
    "DAI": "0x6B175474E89094C44Da98b954EedeAC495271d0F",
    "WBTC": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",
    "UNI": "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984",
    "LINK": "0x514910771AF9Ca656af840dff83E8264EcF986CA",
    "AAVE": "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9",
    "CRV": "0xD533a949740bb3306d119CC777fa900bA034cd52",
    "LDO": "0x5A98FcBEA516Cf06857215779Fd812CA3beF1B32",
    "PEPE": "0x6982508145454Ce325dDbE47a25d4ec3d2311933",
    "SHIB": "0x95aD61b0a150d79219dCF64E1E6Cc01f0B64C4cE",
    "ARB": "0xB50721BCf8d664c30412Cfbc6cf7a15145234ad1",
    "MKR": "0x9f8F72aA9304c8B593d555F12eF6589cC3A579A2",
    "COMP": "0xc00e94Cb662C3520282E6f5717214004A7f26888",
    "SUSHI": "0x6B3595068778DD592e39A122f4f5a5cF09C90fE2",
    "1INCH": "0x111111111117dC0aa78b770fA6A738034120C302",
    "STETH": "0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84",
    "RETH": "0xae78736Cd615f374D3085123A210448E74Fc6393",
}

# Token addresses on Arbitrum
TOKEN_ADDRESSES_ARB = {
    "ETH": "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
    "WETH": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
    "USDC": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
    "USDT": "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9",
    "ARB": "0x912CE59144191C1204E64559FE8253a0e49E6548",
    "GMX": "0xfc5A1A6EB076a2C7aD06eD22C90d7E710E35ad0a",
    "PENDLE": "0x0c880f6761F1af8d9Aa9C466984b80DAb9a8c9e8",
}


class SwapTool:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=20)

    def _resolve_token(self, symbol: str, chain: str) -> str:
        """Resolve token symbol to contract address."""
        s = symbol.upper().strip()
        if s.startswith("0X"):
            return symbol  # Already an address

        if chain == "arbitrum":
            return TOKEN_ADDRESSES_ARB.get(s, s)
        return TOKEN_ADDRESSES.get(s, s)

    async def get_quote(
        self,
        from_token: str,
        to_token: str,
        amount: float,
        chain: str = "ethereum",
    ) -> Dict:
        """Get best swap quote via 1inch/Paraswap aggregators."""
        from_addr = self._resolve_token(from_token, chain)
        to_addr = self._resolve_token(to_token, chain)

        # Try multiple aggregator APIs
        results = []

        # 1inch quote
        quote_1inch = await self._get_1inch_quote(from_addr, to_addr, amount, chain)
        if quote_1inch:
            results.append(quote_1inch)

        # Paraswap quote
        quote_paraswap = await self._get_paraswap_quote(from_addr, to_addr, amount, chain)
        if quote_paraswap:
            results.append(quote_paraswap)

        if not results:
            return {
                "error": "Could not get swap quotes",
                "from": from_token,
                "to": to_token,
                "amount": amount,
                "hint": "Token may not be supported or amount may be too small.",
            }

        # Return best quote
        results.sort(key=lambda x: x.get("to_amount", 0), reverse=True)
        best = dict(results[0])
        if len(results) > 1:
            best["alternative_quotes"] = [dict(r) for r in results[1:]]

        return best

    async def compare_dexes(
        self,
        from_token: str,
        to_token: str,
        amount: float,
        chain: str = "ethereum",
    ) -> Dict:
        """Compare quotes across multiple DEX aggregators."""
        from_addr = self._resolve_token(from_token, chain)
        to_addr = self._resolve_token(to_token, chain)

        quotes = []

        # Gather quotes from multiple sources
        quote_1inch = await self._get_1inch_quote(from_addr, to_addr, amount, chain)
        if quote_1inch:
            quotes.append(quote_1inch)

        quote_paraswap = await self._get_paraswap_quote(from_addr, to_addr, amount, chain)
        if quote_paraswap:
            quotes.append(quote_paraswap)

        if not quotes:
            return {"error": "No quotes available", "from": from_token, "to": to_token}

        quotes.sort(key=lambda x: x.get("to_amount", 0), reverse=True)

        best_amount = quotes[0].get("to_amount", 0)
        for q in quotes:
            if best_amount > 0:
                q["vs_best_pct"] = round(
                    (q.get("to_amount", 0) - best_amount) / best_amount * 100, 4
                )

        return {
            "from_token": from_token,
            "to_token": to_token,
            "amount": amount,
            "chain": chain,
            "best_dex": quotes[0].get("dex", "unknown"),
            "quotes": quotes,
        }

    async def _get_1inch_quote(
        self, from_addr: str, to_addr: str, amount: float, chain: str
    ) -> Optional[Dict]:
        """Get quote from 1inch API."""
        chain_ids = {
            "ethereum": 1, "arbitrum": 42161, "base": 8453,
            "polygon": 137, "optimism": 10,
        }
        chain_id = chain_ids.get(chain, 1)

        # Convert amount to wei (assume 18 decimals for simplicity)
        # In production, look up actual decimals
        decimals = 6 if from_addr in (
            TOKEN_ADDRESSES.get("USDC"), TOKEN_ADDRESSES.get("USDT"),
            TOKEN_ADDRESSES_ARB.get("USDC"), TOKEN_ADDRESSES_ARB.get("USDT"),
        ) else 18
        amount_wei = str(int(amount * (10 ** decimals)))

        try:
            resp = await self.client.get(
                f"https://api.1inch.dev/swap/v6.0/{chain_id}/quote",
                params={
                    "src": from_addr,
                    "dst": to_addr,
                    "amount": amount_wei,
                },
                headers={"Accept": "application/json"},
            )

            if resp.status_code == 200:
                data = resp.json()
                dst_decimals = int(data.get("dstToken", {}).get("decimals", 18))
                to_amount = int(data.get("dstAmount", 0)) / (10 ** dst_decimals)

                return {
                    "dex": "1inch",
                    "from_amount": amount,
                    "to_amount": round(to_amount, 8),
                    "rate": round(to_amount / amount, 8) if amount > 0 else 0,
                    "gas_estimate": data.get("gas", "N/A"),
                }
        except Exception:
            pass

        return None

    async def _get_paraswap_quote(
        self, from_addr: str, to_addr: str, amount: float, chain: str
    ) -> Optional[Dict]:
        """Get quote from ParaSwap API (free, no key needed)."""
        chain_ids = {
            "ethereum": 1, "arbitrum": 42161, "base": 8453,
            "polygon": 137, "optimism": 10,
        }
        chain_id = chain_ids.get(chain, 1)

        decimals = 6 if from_addr in (
            TOKEN_ADDRESSES.get("USDC"), TOKEN_ADDRESSES.get("USDT"),
            TOKEN_ADDRESSES_ARB.get("USDC"), TOKEN_ADDRESSES_ARB.get("USDT"),
        ) else 18
        amount_wei = str(int(amount * (10 ** decimals)))

        try:
            resp = await self.client.get(
                f"https://apiv5.paraswap.io/prices",
                params={
                    "srcToken": from_addr,
                    "destToken": to_addr,
                    "amount": amount_wei,
                    "srcDecimals": decimals,
                    "destDecimals": 18,
                    "side": "SELL",
                    "network": chain_id,
                },
            )

            if resp.status_code == 200:
                data = resp.json().get("priceRoute", {})
                dst_decimals = int(data.get("destDecimals", 18))
                to_amount = int(data.get("destAmount", 0)) / (10 ** dst_decimals)

                return {
                    "dex": "paraswap",
                    "from_amount": amount,
                    "to_amount": round(to_amount, 8),
                    "rate": round(to_amount / amount, 8) if amount > 0 else 0,
                    "gas_estimate": data.get("gasCost", "N/A"),
                    "best_route": data.get("bestRoute", [{}])[0].get("swaps", [{}])[0].get("swapExchanges", [{}])[0].get("exchange", "N/A") if data.get("bestRoute") else "N/A",
                }
        except Exception:
            pass

        return None
