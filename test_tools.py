"""Quick test for all MCP tools."""
import asyncio
import json
import sys
sys.path.insert(0, ".")

from src.tools.prices import PriceTool
from src.tools.wallet import WalletTool
from src.tools.defi import DeFiTool
from src.tools.onchain import OnChainTool
from src.tools.swap import SwapTool


async def test_all():
    print("=" * 60)
    print("CRYPTO MCP SERVER - TOOL TESTS")
    print("=" * 60)

    # 1. Price
    print("\n[1] crypto_price (BTC)")
    pt = PriceTool()
    r = await pt.get_price("BTC")
    print(json.dumps(r, indent=2))

    # 2. Batch prices
    print("\n[2] crypto_prices_batch (BTC, ETH, SOL)")
    r = await pt.get_prices_batch(["BTC", "ETH", "SOL"])
    print(json.dumps(r, indent=2))

    # 3. Trending
    print("\n[3] trending_tokens")
    r = await pt.get_trending()
    for t in r.get("trending", [])[:5]:
        print(f"  {t['symbol']} ({t['name']}) - rank #{t['market_cap_rank']}")

    # 4. DeFi yields
    print("\n[4] defi_yields (USDC, min 5% APY)")
    df = DeFiTool()
    r = await df.get_yields(token="USDC", min_apy=5, limit=5)
    for y in r.get("yields", []):
        print(f"  {y['protocol']:20s} | {y['chain']:12s} | APY: {y['apy']:8.2f}% | TVL: ${y['tvl_usd']:>12,}")

    # 5. Gas prices
    print("\n[5] gas_prices (ethereum)")
    oc = OnChainTool()
    r = await oc.get_gas_prices("ethereum")
    print(json.dumps(r, indent=2))

    # 6. Token info
    print("\n[6] token_info (ETH)")
    r = await oc.get_token_info("ETH")
    print(f"  {r.get('name')} | Rank #{r.get('market_cap_rank')} | ${r.get('price_usd'):,.2f}")
    print(f"  MCap: ${r.get('market_cap', 0):,.0f}")

    # 7. Wallet balance (Vitalik's address)
    print("\n[7] wallet_balance (vitalik.eth)")
    wt = WalletTool()
    r = await wt.get_balance("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045", "ethereum")
    if "tokens" in r:
        print(f"  Total: ${r['total_balance_usd']:,.2f}")
        for t in r.get("tokens", [])[:5]:
            print(f"    {t['symbol']:8s} ${t['balance_usd']:>12,.2f}")
    else:
        print(f"  {json.dumps(r, indent=2)}")

    # 8. Swap quote
    print("\n[8] swap_quote (1 ETH -> USDC on ethereum)")
    st = SwapTool()
    r = await st.get_quote("ETH", "USDC", 1.0, "ethereum")
    print(json.dumps(r, indent=2))

    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_all())
