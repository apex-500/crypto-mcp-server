"""DeFi protocol tools - powered by DeFiLlama (100% free, no key needed)."""
import httpx
from typing import Dict, List, Optional


DEFILLAMA_BASE = "https://yields.llama.fi"
DEFILLAMA_API = "https://api.llama.fi"


class DeFiTool:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=20)

    async def get_yields(
        self,
        token: Optional[str] = None,
        chain: Optional[str] = None,
        min_apy: Optional[float] = None,
        min_tvl: float = 100_000,
        limit: int = 10,
    ) -> Dict:
        """Find best yield opportunities across all DeFi protocols."""
        resp = await self.client.get(f"{DEFILLAMA_BASE}/pools")
        resp.raise_for_status()
        pools = resp.json().get("data", [])

        # Filter
        filtered = []
        for p in pools:
            tvl = p.get("tvlUsd", 0) or 0
            apy = p.get("apy", 0) or 0

            if tvl < min_tvl:
                continue
            if min_apy and apy < min_apy:
                continue
            if token and token.upper() not in (p.get("symbol", "") or "").upper():
                continue
            if chain and chain.lower() != (p.get("chain", "") or "").lower():
                continue
            if apy > 1000:  # Filter out obviously fake APYs
                continue

            filtered.append(p)

        # Sort by APY descending
        filtered.sort(key=lambda x: x.get("apy", 0), reverse=True)

        results = []
        for p in filtered[:limit]:
            results.append({
                "protocol": p.get("project", ""),
                "chain": p.get("chain", ""),
                "pool": p.get("symbol", ""),
                "apy": round(p.get("apy", 0), 2),
                "apy_base": round(p.get("apyBase", 0) or 0, 2),
                "apy_reward": round(p.get("apyReward", 0) or 0, 2),
                "tvl_usd": round(p.get("tvlUsd", 0)),
                "stable": p.get("stablecoin", False),
                "il_risk": p.get("ilRisk", "unknown"),
            })

        return {
            "yields": results,
            "total_pools_scanned": len(pools),
            "matching_pools": len(filtered),
            "filters": {
                "token": token,
                "chain": chain,
                "min_apy": min_apy,
                "min_tvl": min_tvl,
            },
        }

    async def get_protocol_tvl(self, limit: int = 20) -> Dict:
        """Get top DeFi protocols ranked by TVL."""
        resp = await self.client.get(f"{DEFILLAMA_API}/protocols")
        resp.raise_for_status()
        protocols = resp.json()

        # Already sorted by TVL in API response
        results = []
        for p in protocols[:limit]:
            results.append({
                "name": p.get("name", ""),
                "chain": p.get("chain", ""),
                "category": p.get("category", ""),
                "tvl": round(p.get("tvl", 0)),
                "change_1d": round(p.get("change_1d", 0) or 0, 2),
                "change_7d": round(p.get("change_7d", 0) or 0, 2),
                "mcap_tvl": round(p.get("mcap/tvl", 0) or 0, 2),
            })

        return {"protocols": results, "total_protocols": len(protocols)}
