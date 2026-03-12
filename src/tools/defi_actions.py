"""DeFi management tools - deposit, withdraw, positions, and auto-yield optimization.

Premium features that interact with Aave V3 on supported EVM chains.
Requires: WALLET_PRIVATE_KEY env var for transaction signing.
"""
import os
import json
from typing import Dict, Optional

from .actions import CHAIN_CONFIG, _resolve_token, _get_decimals, _encode_address, _encode_uint256, ERC20_APPROVE_SIG
from .fee_manager import FeeManager


# Aave V3 Pool addresses per chain
AAVE_V3_POOL = {
    "ethereum": "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2",
    "arbitrum": "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
    "base": "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5",
    "polygon": "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
}

# Minimal Aave V3 Pool ABI - only the functions we need
AAVE_V3_POOL_ABI = [
    {
        "name": "supply",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "asset", "type": "address"},
            {"name": "amount", "type": "uint256"},
            {"name": "onBehalfOf", "type": "address"},
            {"name": "referralCode", "type": "uint16"},
        ],
        "outputs": [],
    },
    {
        "name": "withdraw",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "asset", "type": "address"},
            {"name": "amount", "type": "uint256"},
            {"name": "to", "type": "address"},
        ],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "getUserAccountData",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "user", "type": "address"}],
        "outputs": [
            {"name": "totalCollateralBase", "type": "uint256"},
            {"name": "totalDebtBase", "type": "uint256"},
            {"name": "availableBorrowsBase", "type": "uint256"},
            {"name": "currentLiquidationThreshold", "type": "uint256"},
            {"name": "ltv", "type": "uint256"},
            {"name": "healthFactor", "type": "uint256"},
        ],
    },
]

# Supported chains for DeFi actions
DEFI_SUPPORTED_CHAINS = list(AAVE_V3_POOL.keys())


class DefiActionTool:
    """Handles DeFi deposits, withdrawals, position queries, and auto-yield."""

    def __init__(self, fee_manager: Optional[FeeManager] = None):
        self.fee_manager = fee_manager or FeeManager()

    def _get_web3(self, chain: str):
        """Get a web3 instance for the given chain (lazy import)."""
        try:
            from web3 import Web3
        except ImportError:
            raise RuntimeError(
                "web3 package required for DeFi actions. "
                "Install with: pip install 'crypto-mcp-server[web3]'"
            )
        config = CHAIN_CONFIG.get(chain)
        if not config:
            raise ValueError(f"Unsupported chain: {chain}. Supported: {DEFI_SUPPORTED_CHAINS}")
        return Web3(Web3.HTTPProvider(config["rpc"]))

    def _get_account(self, w3):
        """Get account from private key env var."""
        private_key = os.environ.get("WALLET_PRIVATE_KEY")
        if not private_key:
            raise ValueError(
                "WALLET_PRIVATE_KEY environment variable not set. "
                "Required for DeFi transactions."
            )
        if not private_key.startswith("0x"):
            private_key = "0x" + private_key
        return w3.eth.account.from_key(private_key)

    def _get_pool_contract(self, w3, chain: str):
        """Get Aave V3 Pool contract instance."""
        pool_addr = AAVE_V3_POOL.get(chain)
        if not pool_addr:
            raise ValueError(
                f"Aave V3 not supported on {chain}. "
                f"Supported chains: {DEFI_SUPPORTED_CHAINS}"
            )
        return w3.eth.contract(
            address=w3.to_checksum_address(pool_addr),
            abi=AAVE_V3_POOL_ABI,
        )

    async def _send_transaction(self, w3, account, tx: dict, chain: str) -> Dict:
        """Sign and send a transaction, return result dict."""
        tx["chainId"] = CHAIN_CONFIG[chain]["chain_id"]
        tx["nonce"] = w3.eth.get_transaction_count(account.address)

        if "gas" not in tx:
            try:
                tx["gas"] = int(w3.eth.estimate_gas(tx) * 1.2)
            except Exception as e:
                raise ValueError(f"Gas estimation failed: {e}")

        if "gasPrice" not in tx and "maxFeePerGas" not in tx:
            tx["gasPrice"] = w3.eth.gas_price

        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        tx_hash_hex = tx_hash.hex()

        return {
            "status": "submitted",
            "tx_hash": f"0x{tx_hash_hex}" if not tx_hash_hex.startswith("0x") else tx_hash_hex,
            "from": account.address,
            "chain": chain,
            "chain_id": CHAIN_CONFIG[chain]["chain_id"],
            "gas_limit": tx.get("gas"),
            "note": "Transaction submitted. Use tx_hash to check status on block explorer.",
        }

    # -------------------------------------------------------------------------
    # defi_deposit
    # -------------------------------------------------------------------------
    async def defi_deposit(
        self,
        token: str,
        amount: float,
        chain: str = "ethereum",
        fee_bps: Optional[int] = None,
    ) -> Dict:
        """Deposit tokens into Aave V3 to earn yield.

        Approves Aave V3 Pool to spend the token, then calls supply().
        A fee is deducted before depositing.
        """
        chain = chain.lower()
        if chain not in DEFI_SUPPORTED_CHAINS:
            return {"error": f"Unsupported chain for DeFi: {chain}. Supported: {DEFI_SUPPORTED_CHAINS}"}

        # Calculate fee
        fee_amount, net_amount = self.fee_manager.calculate_fee(amount, fee_bps)

        if net_amount <= 0:
            return {"error": "Amount too small after fee deduction."}

        try:
            w3 = self._get_web3(chain)
            account = self._get_account(w3)
        except (RuntimeError, ValueError) as e:
            return {"error": str(e)}

        token_addr = _resolve_token(token, chain)
        is_native = token_addr.lower() == "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"

        if is_native:
            return {
                "error": "Cannot deposit native ETH directly into Aave V3. "
                "Wrap to WETH first using wrap_eth, then deposit WETH."
            }

        decimals = _get_decimals(token_addr)
        amount_raw = int(net_amount * (10 ** decimals))
        pool_addr = AAVE_V3_POOL[chain]

        try:
            pool = self._get_pool_contract(w3, chain)

            # Step 1: Approve Aave V3 Pool to spend tokens
            approve_calldata = (
                ERC20_APPROVE_SIG
                + _encode_address(pool_addr)
                + _encode_uint256(amount_raw)
            )
            approve_tx = {
                "to": w3.to_checksum_address(token_addr),
                "data": approve_calldata,
                "value": 0,
                "from": account.address,
            }
            approve_result = await self._send_transaction(w3, account, approve_tx, chain)

            # Step 2: Build supply() transaction
            supply_tx = pool.functions.supply(
                w3.to_checksum_address(token_addr),
                amount_raw,
                account.address,
                0,  # referralCode
            ).build_transaction({
                "from": account.address,
                "value": 0,
            })

            supply_result = await self._send_transaction(w3, account, supply_tx, chain)

            # Collect fee if FEE_WALLET is set
            fee_result = await self.fee_manager.collect_fee_erc20(
                chain, token_addr, fee_amount, w3=w3, account=account,
            )

            supply_result.update({
                "action": "defi_deposit",
                "protocol": "aave_v3",
                "token": token.upper(),
                "token_address": token_addr,
                "deposit_amount": round(net_amount, 8),
                "fee_amount": round(fee_amount, 8),
                "fee_bps": fee_bps if fee_bps is not None else self.fee_manager.default_fee_bps,
                "pool_address": pool_addr,
                "approve_tx": approve_result.get("tx_hash"),
                "fee_collection": fee_result.get("status", "skipped"),
            })
            return supply_result

        except ValueError as e:
            return {"error": str(e)}
        except Exception as e:
            return {"error": f"Deposit failed: {e}"}

    # -------------------------------------------------------------------------
    # defi_withdraw
    # -------------------------------------------------------------------------
    async def defi_withdraw(
        self,
        token: str,
        amount: float,
        chain: str = "ethereum",
    ) -> Dict:
        """Withdraw tokens from Aave V3.

        Calls withdraw() on the Aave V3 Pool. Use amount=-1 to withdraw max.
        """
        chain = chain.lower()
        if chain not in DEFI_SUPPORTED_CHAINS:
            return {"error": f"Unsupported chain for DeFi: {chain}. Supported: {DEFI_SUPPORTED_CHAINS}"}

        try:
            w3 = self._get_web3(chain)
            account = self._get_account(w3)
        except (RuntimeError, ValueError) as e:
            return {"error": str(e)}

        token_addr = _resolve_token(token, chain)
        is_native = token_addr.lower() == "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"

        if is_native:
            return {"error": "Use WETH address for withdrawal from Aave V3."}

        decimals = _get_decimals(token_addr)

        # amount == -1 means withdraw max (uint256 max)
        if amount == -1:
            amount_raw = 2**256 - 1
        else:
            amount_raw = int(amount * (10 ** decimals))

        try:
            pool = self._get_pool_contract(w3, chain)

            withdraw_tx = pool.functions.withdraw(
                w3.to_checksum_address(token_addr),
                amount_raw,
                account.address,
            ).build_transaction({
                "from": account.address,
                "value": 0,
            })

            result = await self._send_transaction(w3, account, withdraw_tx, chain)
            result.update({
                "action": "defi_withdraw",
                "protocol": "aave_v3",
                "token": token.upper(),
                "token_address": token_addr,
                "withdraw_amount": "max" if amount == -1 else round(amount, 8),
                "pool_address": AAVE_V3_POOL[chain],
            })
            return result

        except ValueError as e:
            return {"error": str(e)}
        except Exception as e:
            return {"error": f"Withdrawal failed: {e}"}

    # -------------------------------------------------------------------------
    # defi_positions
    # -------------------------------------------------------------------------
    async def defi_positions(
        self,
        address: Optional[str] = None,
        chain: str = "ethereum",
    ) -> Dict:
        """Check current Aave V3 positions for a wallet.

        Queries getUserAccountData() to get supplied/borrowed amounts,
        health factor, and liquidation threshold.
        """
        chain = chain.lower()
        if chain not in DEFI_SUPPORTED_CHAINS:
            return {"error": f"Unsupported chain for DeFi: {chain}. Supported: {DEFI_SUPPORTED_CHAINS}"}

        try:
            w3 = self._get_web3(chain)
        except (RuntimeError, ValueError) as e:
            return {"error": str(e)}

        # Use provided address or derive from private key
        if address:
            user_address = w3.to_checksum_address(address)
        else:
            try:
                account = self._get_account(w3)
                user_address = account.address
            except ValueError as e:
                return {"error": str(e)}

        try:
            pool = self._get_pool_contract(w3, chain)

            data = pool.functions.getUserAccountData(user_address).call()
            # Aave V3 returns values in base currency (USD with 8 decimals)
            total_collateral = data[0] / 1e8
            total_debt = data[1] / 1e8
            available_borrows = data[2] / 1e8
            liquidation_threshold = data[3] / 100  # percentage in bps
            ltv = data[4] / 100  # percentage in bps
            health_factor = data[5] / 1e18

            return {
                "address": user_address,
                "chain": chain,
                "protocol": "aave_v3",
                "pool_address": AAVE_V3_POOL[chain],
                "positions": {
                    "total_collateral_usd": round(total_collateral, 2),
                    "total_debt_usd": round(total_debt, 2),
                    "available_borrows_usd": round(available_borrows, 2),
                    "net_worth_usd": round(total_collateral - total_debt, 2),
                    "liquidation_threshold_pct": round(liquidation_threshold, 2),
                    "ltv_pct": round(ltv, 2),
                    "health_factor": round(health_factor, 4) if health_factor < 1e10 else "safe (no debt)",
                },
            }

        except Exception as e:
            return {"error": f"Failed to fetch positions: {e}"}

    # -------------------------------------------------------------------------
    # auto_yield
    # -------------------------------------------------------------------------
    async def auto_yield(
        self,
        token: str,
        amount: float,
        chain: str = "ethereum",
        min_apy_improvement: float = 0.5,
        fee_bps: Optional[int] = None,
    ) -> Dict:
        """Automatically move funds to the highest yield opportunity.

        This is the killer feature: AI agents auto-optimizing yield.

        Steps:
        1. Query DeFiLlama for the best yield for this token.
        2. Check current Aave V3 position on this chain.
        3. If a better yield is found (by min_apy_improvement), withdraw and re-deposit.
        4. If Aave V3 on the current chain is already the best, just deposit.

        Note: Cross-chain moves require bridging (not yet supported), so auto_yield
        currently optimizes within the same chain or recommends cross-chain moves.
        """
        chain = chain.lower()

        # Step 1: Find best yield for this token
        from .defi import DeFiTool
        defi_tool = DeFiTool()

        try:
            yields_data = await defi_tool.get_yields(
                token=token,
                min_tvl=100_000,
                limit=20,
            )
        except Exception as e:
            return {"error": f"Failed to fetch yield data: {e}"}

        yields = yields_data.get("yields", [])
        if not yields:
            return {
                "error": f"No yield opportunities found for {token}.",
                "suggestion": "Try a more common token like USDC, ETH, or WBTC.",
            }

        # Find best yield on the same chain
        best_same_chain = None
        best_any_chain = yields[0] if yields else None
        current_aave_apy = None

        for y in yields:
            if y.get("chain", "").lower() == chain:
                if best_same_chain is None:
                    best_same_chain = y
                if y.get("protocol", "").lower() in ("aave-v3", "aave v3", "aavev3"):
                    current_aave_apy = y.get("apy", 0)

        # Step 2: Check current position
        try:
            positions = await self.defi_positions(chain=chain)
        except Exception:
            positions = {}

        current_collateral = 0.0
        if "positions" in positions:
            current_collateral = positions["positions"].get("total_collateral_usd", 0.0)

        # Step 3: Decide action
        best_yield = best_same_chain or best_any_chain
        best_apy = best_yield.get("apy", 0) if best_yield else 0
        aave_apy = current_aave_apy or 0

        action_taken = "none"
        result = {
            "action": "auto_yield",
            "token": token.upper(),
            "chain": chain,
            "current_aave_apy": aave_apy,
            "best_yield": best_yield,
            "current_collateral_usd": current_collateral,
        }

        # If best yield is on Aave V3 on this chain, or it's the best same-chain option
        is_aave_best = (
            best_same_chain
            and best_same_chain.get("protocol", "").lower() in ("aave-v3", "aave v3", "aavev3")
        )

        if is_aave_best or (not best_same_chain and best_any_chain):
            # Aave V3 is already best on this chain, or no same-chain option exists
            if best_same_chain and not is_aave_best:
                # Better option exists on same chain but not on Aave
                result["recommendation"] = (
                    f"Better yield found: {best_same_chain['protocol']} at "
                    f"{best_same_chain['apy']}% APY on {best_same_chain['chain']}. "
                    f"Manual migration recommended (protocol not yet supported for auto-deposit)."
                )
                action_taken = "recommendation"
            elif not best_same_chain and best_any_chain:
                result["recommendation"] = (
                    f"Best yield for {token} is on {best_any_chain['chain']}: "
                    f"{best_any_chain['protocol']} at {best_any_chain['apy']}% APY. "
                    f"Cross-chain bridging required (not yet automated). "
                    f"Depositing into Aave V3 on {chain} instead."
                )

            # Deposit into Aave V3 on this chain
            if chain in DEFI_SUPPORTED_CHAINS:
                deposit_result = await self.defi_deposit(
                    token=token, amount=amount, chain=chain, fee_bps=fee_bps,
                )
                result["deposit_result"] = deposit_result
                action_taken = "deposited"
            else:
                result["error"] = f"Aave V3 not available on {chain}."
                action_taken = "failed"

        else:
            # best_same_chain exists and is NOT Aave V3
            improvement = best_apy - aave_apy

            if improvement >= min_apy_improvement:
                result["recommendation"] = (
                    f"Better yield found: {best_same_chain['protocol']} at "
                    f"{best_same_chain['apy']}% APY vs Aave V3 at {aave_apy}% APY "
                    f"(+{improvement:.2f}% improvement). "
                    f"Manual migration to {best_same_chain['protocol']} recommended."
                )
                action_taken = "recommendation"

                # Still deposit to Aave V3 as it's the only protocol we support on-chain
                if chain in DEFI_SUPPORTED_CHAINS:
                    deposit_result = await self.defi_deposit(
                        token=token, amount=amount, chain=chain, fee_bps=fee_bps,
                    )
                    result["deposit_result"] = deposit_result
                    action_taken = "deposited_with_recommendation"
            else:
                # Aave is close enough, just deposit
                if chain in DEFI_SUPPORTED_CHAINS:
                    deposit_result = await self.defi_deposit(
                        token=token, amount=amount, chain=chain, fee_bps=fee_bps,
                    )
                    result["deposit_result"] = deposit_result
                    action_taken = "deposited"

        result["action_taken"] = action_taken
        return result
