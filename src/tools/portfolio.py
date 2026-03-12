"""Portfolio tools - aggregate wallet data across chains for a complete overview."""
import httpx
from typing import Dict, List, Optional

from .wallet import WalletTool


# Chains to scan for portfolio summary
SUPPORTED_CHAINS = ["ethereum", "arbitrum", "base", "polygon", "optimism"]


class PortfolioTool:
    def __init__(self, wallet_tool: Optional[WalletTool] = None):
        self.wallet_tool = wallet_tool or WalletTool()
        self.client = httpx.AsyncClient(timeout=20)

    async def portfolio_summary(
        self,
        address: str,
        chains: Optional[List[str]] = None,
    ) -> Dict:
        """Get complete portfolio overview across all chains.

        Returns total value, per-chain breakdown, token allocation percentages,
        and top holdings.
        """
        scan_chains = chains or SUPPORTED_CHAINS
        scan_chains = [c.lower() for c in scan_chains]

        chain_results = {}
        total_usd = 0.0
        all_tokens = []
        errors = []

        for chain in scan_chains:
            try:
                balance = await self.wallet_tool.get_balance(address, chain)

                if "error" in balance:
                    errors.append({"chain": chain, "error": balance["error"]})
                    continue

                chain_total = balance.get("total_balance_usd", 0.0)
                tokens = balance.get("tokens", [])

                chain_results[chain] = {
                    "total_usd": round(chain_total, 2),
                    "token_count": len(tokens),
                    "top_tokens": tokens[:5],
                }

                total_usd += chain_total

                # Aggregate tokens across chains
                for t in tokens:
                    all_tokens.append({
                        "symbol": t.get("symbol", "?"),
                        "name": t.get("name", ""),
                        "balance": t.get("balance", "0"),
                        "balance_usd": t.get("balance_usd", 0),
                        "price": t.get("price", 0),
                        "chain": chain,
                    })

            except Exception as e:
                errors.append({"chain": chain, "error": str(e)})

        # Sort all tokens by USD value
        all_tokens.sort(key=lambda x: x.get("balance_usd", 0), reverse=True)

        # Calculate allocation percentages
        allocations = []
        for t in all_tokens[:20]:
            usd_val = t.get("balance_usd", 0)
            pct = (usd_val / total_usd * 100) if total_usd > 0 else 0
            allocations.append({
                "symbol": t["symbol"],
                "chain": t["chain"],
                "balance_usd": round(usd_val, 2),
                "allocation_pct": round(pct, 2),
            })

        # Per-chain allocation
        chain_allocation = {}
        for chain, data in chain_results.items():
            chain_usd = data["total_usd"]
            pct = (chain_usd / total_usd * 100) if total_usd > 0 else 0
            chain_allocation[chain] = {
                "total_usd": round(chain_usd, 2),
                "allocation_pct": round(pct, 2),
            }

        result = {
            "address": address,
            "total_balance_usd": round(total_usd, 2),
            "chains_scanned": len(scan_chains),
            "chain_allocation": chain_allocation,
            "top_holdings": allocations[:10],
            "total_unique_tokens": len(all_tokens),
        }

        if errors:
            result["warnings"] = errors

        return result

    async def portfolio_history(
        self,
        address: str,
        days: int = 30,
        chain: str = "ethereum",
    ) -> Dict:
        """Track portfolio value over time.

        Uses on-chain transfer history to estimate historical portfolio value.
        Note: This is an approximation based on transaction history and current prices.
        Full historical tracking would require an indexing service.
        """
        # Get current portfolio snapshot
        current = await self.wallet_tool.get_balance(address, chain)

        if "error" in current:
            return current

        current_total = current.get("total_balance_usd", 0)
        tokens = current.get("tokens", [])

        # Get transaction history to estimate activity
        tx_data = await self.wallet_tool.get_transactions(address, chain, limit=50)
        transactions = tx_data.get("transactions", [])

        # Calculate basic metrics from transaction history
        total_inflow_eth = 0.0
        total_outflow_eth = 0.0
        tx_count = len(transactions)

        for tx in transactions:
            value = tx.get("value_eth", 0)
            if tx.get("to", "").lower() == address.lower():
                total_inflow_eth += value
            elif tx.get("from", "").lower() == address.lower():
                total_outflow_eth += value

        # Get ETH price for USD conversion
        eth_price_usd = 0.0
        try:
            from .prices import COINGECKO_BASE
            resp = await self.client.get(
                f"{COINGECKO_BASE}/simple/price",
                params={"ids": "ethereum", "vs_currencies": "usd"},
            )
            if resp.status_code == 200:
                eth_price_usd = resp.json().get("ethereum", {}).get("usd", 0)
        except Exception:
            pass

        return {
            "address": address,
            "chain": chain,
            "period_days": days,
            "current_value_usd": round(current_total, 2),
            "token_count": len(tokens),
            "activity": {
                "total_transactions": tx_count,
                "total_inflow_eth": round(total_inflow_eth, 6),
                "total_outflow_eth": round(total_outflow_eth, 6),
                "net_flow_eth": round(total_inflow_eth - total_outflow_eth, 6),
                "net_flow_usd": round(
                    (total_inflow_eth - total_outflow_eth) * eth_price_usd, 2
                ),
            },
            "top_holdings": [
                {
                    "symbol": t.get("symbol", "?"),
                    "balance_usd": t.get("balance_usd", 0),
                }
                for t in tokens[:10]
            ],
            "note": (
                "Historical portfolio tracking is approximate based on recent transactions. "
                "For precise historical NAV, an indexing service (e.g., Covalent, Moralis) is recommended."
            ),
        }
