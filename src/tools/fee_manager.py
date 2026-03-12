"""Fee management system for revenue collection.

Centralizes fee calculation and collection for all paid operations
(swaps, DeFi actions, etc.). Fees are sent to the operator's FEE_WALLET.

Env vars:
  FEE_WALLET  - Operator wallet address that receives fees
  FEE_BPS     - Default fee in basis points (default: 10 = 0.1%)
"""
import os
from typing import Dict, Optional, Tuple


DEFAULT_FEE_BPS = 10  # 0.1%


class FeeManager:
    """Manages fee calculation, collection, and tracking."""

    def __init__(self):
        self._fee_stats: Dict[str, float] = {}  # token -> total_collected

    @property
    def fee_wallet(self) -> Optional[str]:
        """Operator wallet that receives fees."""
        return os.environ.get("FEE_WALLET")

    @property
    def default_fee_bps(self) -> int:
        """Default fee in basis points."""
        return int(os.environ.get("FEE_BPS", DEFAULT_FEE_BPS))

    def calculate_fee(
        self,
        amount: float,
        fee_bps: Optional[int] = None,
    ) -> Tuple[float, float]:
        """Calculate fee and net amount.

        Args:
            amount: Total input amount.
            fee_bps: Override fee in basis points. Uses default if None.

        Returns:
            (fee_amount, net_amount) tuple.
        """
        bps = fee_bps if fee_bps is not None else self.default_fee_bps
        fee_amount = amount * bps / 10_000
        net_amount = amount - fee_amount
        return (fee_amount, net_amount)

    async def collect_fee_native(self, chain: str, fee_amount: float, w3=None, account=None) -> Dict:
        """Send native token (ETH/MATIC) fee to FEE_WALLET.

        Args:
            chain: Target chain name.
            fee_amount: Amount of native token to send as fee.
            w3: Web3 instance (optional, created if not provided).
            account: Account instance (optional, created if not provided).

        Returns:
            Result dict with tx details or error.
        """
        fee_wallet = self.fee_wallet
        if not fee_wallet:
            return {"status": "skipped", "reason": "FEE_WALLET not configured"}

        if fee_amount <= 0:
            return {"status": "skipped", "reason": "fee_amount is zero or negative"}

        # Lazy import to avoid circular dependency
        from .actions import CHAIN_CONFIG, ActionTool

        chain = chain.lower()
        if chain not in CHAIN_CONFIG:
            return {"error": f"Unsupported chain: {chain}"}

        try:
            if w3 is None or account is None:
                _action = ActionTool()
                w3 = _action._get_web3(chain)
                account = _action._get_account(w3)

            amount_wei = int(fee_amount * 1e18)
            tx = {
                "to": w3.to_checksum_address(fee_wallet),
                "value": amount_wei,
                "from": account.address,
                "gas": 21_000,
                "chainId": CHAIN_CONFIG[chain]["chain_id"],
                "nonce": w3.eth.get_transaction_count(account.address),
                "gasPrice": w3.eth.gas_price,
            }

            signed = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            tx_hash_hex = tx_hash.hex()
            if not tx_hash_hex.startswith("0x"):
                tx_hash_hex = f"0x{tx_hash_hex}"

            # Track stats
            native_symbol = CHAIN_CONFIG[chain]["native"]
            self._track(native_symbol, fee_amount)

            return {
                "status": "collected",
                "tx_hash": tx_hash_hex,
                "token": native_symbol,
                "amount": fee_amount,
                "to": fee_wallet,
                "chain": chain,
            }
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    async def collect_fee_erc20(
        self,
        chain: str,
        token_address: str,
        fee_amount: float,
        w3=None,
        account=None,
    ) -> Dict:
        """Send ERC-20 token fee to FEE_WALLET.

        Args:
            chain: Target chain name.
            token_address: ERC-20 contract address.
            fee_amount: Amount of token to send as fee (human-readable).
            w3: Web3 instance (optional).
            account: Account instance (optional).

        Returns:
            Result dict with tx details or error.
        """
        fee_wallet = self.fee_wallet
        if not fee_wallet:
            return {"status": "skipped", "reason": "FEE_WALLET not configured"}

        if fee_amount <= 0:
            return {"status": "skipped", "reason": "fee_amount is zero or negative"}

        # Lazy import to avoid circular dependency
        from .actions import (
            CHAIN_CONFIG, ActionTool, _get_decimals,
            _encode_address, _encode_uint256, ERC20_TRANSFER_SIG,
        )

        chain = chain.lower()
        if chain not in CHAIN_CONFIG:
            return {"error": f"Unsupported chain: {chain}"}

        try:
            if w3 is None or account is None:
                _action = ActionTool()
                w3 = _action._get_web3(chain)
                account = _action._get_account(w3)

            decimals = _get_decimals(token_address)
            amount_raw = int(fee_amount * (10 ** decimals))

            calldata = (
                ERC20_TRANSFER_SIG
                + _encode_address(fee_wallet)
                + _encode_uint256(amount_raw)
            )

            tx = {
                "to": w3.to_checksum_address(token_address),
                "data": calldata,
                "value": 0,
                "from": account.address,
                "chainId": CHAIN_CONFIG[chain]["chain_id"],
                "nonce": w3.eth.get_transaction_count(account.address),
                "gasPrice": w3.eth.gas_price,
            }

            # Estimate gas
            try:
                tx["gas"] = int(w3.eth.estimate_gas(tx) * 1.2)
            except Exception:
                tx["gas"] = 60_000  # safe default for ERC-20 transfer

            signed = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            tx_hash_hex = tx_hash.hex()
            if not tx_hash_hex.startswith("0x"):
                tx_hash_hex = f"0x{tx_hash_hex}"

            # Track stats
            self._track(token_address, fee_amount)

            return {
                "status": "collected",
                "tx_hash": tx_hash_hex,
                "token_address": token_address,
                "amount": fee_amount,
                "to": fee_wallet,
                "chain": chain,
            }
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    def _track(self, token_key: str, amount: float):
        """Record collected fee in memory."""
        self._fee_stats[token_key] = self._fee_stats.get(token_key, 0.0) + amount

    def get_fee_stats(self) -> Dict:
        """Return total fees collected per token (in-memory, resets on restart)."""
        return {
            "fees_collected": dict(self._fee_stats),
            "fee_wallet": self.fee_wallet,
            "default_fee_bps": self.default_fee_bps,
        }
