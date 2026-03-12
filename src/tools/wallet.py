"""Wallet analysis tools - powered by public blockchain APIs."""
import httpx
from typing import Dict, List

# Free public APIs per chain
EXPLORER_APIS = {
    "ethereum": "https://api.etherscan.io/api",
    "arbitrum": "https://api.arbiscan.io/api",
    "base": "https://api.basescan.org/api",
    "polygon": "https://api.polygonscan.com/api",
    "optimism": "https://api-optimistic.etherscan.io/api",
}

# Fallback: use Ankr's free multichain API
ANKR_API = "https://rpc.ankr.com/multichain"


class WalletTool:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=15)

    async def get_balance(self, address: str, chain: str = "ethereum") -> Dict:
        """Get wallet balances using free public APIs."""
        chain = chain.lower()

        # Try Ankr multichain API (no key needed for basic calls)
        try:
            resp = await self.client.post(
                ANKR_API,
                json={
                    "jsonrpc": "2.0",
                    "method": "ankr_getAccountBalance",
                    "params": {
                        "blockchain": [chain],
                        "walletAddress": address,
                    },
                    "id": 1,
                },
            )
            resp.raise_for_status()
            data = resp.json()

            if "result" in data:
                assets = data["result"].get("assets", [])
                total_usd = float(data["result"].get("totalBalanceUsd", 0))

                tokens = []
                for a in assets[:20]:  # Top 20 tokens
                    tokens.append({
                        "symbol": a.get("tokenSymbol", "?"),
                        "name": a.get("tokenName", ""),
                        "balance": a.get("balance", "0"),
                        "balance_usd": round(float(a.get("balanceUsd", 0)), 2),
                        "price": round(float(a.get("tokenPrice", 0)), 6),
                        "token_type": a.get("tokenType", ""),
                    })

                tokens.sort(key=lambda x: x["balance_usd"], reverse=True)

                return {
                    "address": address,
                    "chain": chain,
                    "total_balance_usd": round(total_usd, 2),
                    "token_count": len(assets),
                    "tokens": tokens,
                }
        except Exception:
            pass

        # Fallback: basic ETH balance via public RPC
        try:
            return await self._get_native_balance(address, chain)
        except Exception as e:
            return {
                "address": address,
                "chain": chain,
                "error": f"Could not fetch balance: {str(e)}",
                "hint": "For full token balances, an API key may be needed for high-volume use.",
            }

    async def _get_native_balance(self, address: str, chain: str) -> Dict:
        """Get native token balance via JSON-RPC."""
        rpc_urls = {
            "ethereum": "https://eth.llamarpc.com",
            "arbitrum": "https://arb1.arbitrum.io/rpc",
            "base": "https://mainnet.base.org",
            "polygon": "https://polygon-rpc.com",
            "optimism": "https://mainnet.optimism.io",
        }
        rpc = rpc_urls.get(chain, rpc_urls["ethereum"])

        resp = await self.client.post(
            rpc,
            json={
                "jsonrpc": "2.0",
                "method": "eth_getBalance",
                "params": [address, "latest"],
                "id": 1,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        balance_wei = int(data.get("result", "0x0"), 16)
        balance_eth = balance_wei / 1e18

        native = {"ethereum": "ETH", "arbitrum": "ETH", "base": "ETH",
                   "polygon": "MATIC", "optimism": "ETH"}

        return {
            "address": address,
            "chain": chain,
            "native_token": native.get(chain, "ETH"),
            "balance": round(balance_eth, 6),
            "note": "Native token balance only. Full portfolio requires API key.",
        }

    async def get_transactions(self, address: str, chain: str = "ethereum", limit: int = 10) -> Dict:
        """Get recent transactions."""
        explorer = EXPLORER_APIS.get(chain.lower())
        if not explorer:
            return {"error": f"Chain '{chain}' not supported"}

        try:
            resp = await self.client.get(
                explorer,
                params={
                    "module": "account",
                    "action": "txlist",
                    "address": address,
                    "startblock": 0,
                    "endblock": 99999999,
                    "page": 1,
                    "offset": limit,
                    "sort": "desc",
                },
            )
            resp.raise_for_status()
            data = resp.json()

            txs = []
            for tx in data.get("result", [])[:limit]:
                if isinstance(tx, str):
                    continue
                value_eth = int(tx.get("value", "0")) / 1e18
                txs.append({
                    "hash": tx.get("hash", "")[:20] + "...",
                    "from": tx.get("from", ""),
                    "to": tx.get("to", ""),
                    "value_eth": round(value_eth, 6),
                    "gas_used": tx.get("gasUsed", "0"),
                    "timestamp": tx.get("timeStamp", ""),
                    "status": "success" if tx.get("isError") == "0" else "failed",
                })

            return {
                "address": address,
                "chain": chain,
                "transaction_count": len(txs),
                "transactions": txs,
            }
        except Exception as e:
            return {
                "address": address,
                "chain": chain,
                "error": str(e),
                "hint": "Free tier may be rate-limited. Try again shortly.",
            }
