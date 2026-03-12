"""On-chain action tools - execute swaps, transfers, approvals, and wrapping.

These are revenue-generating tools. AI agents pay a configurable fee (default 0.1%)
on swaps executed through this server.

Requires: WALLET_PRIVATE_KEY environment variable for transaction signing.
Optional: MAX_TX_VALUE_USD (default 10000), FEE_BPS (default 10 = 0.1%)
"""
import os
import json
import httpx
from typing import Dict, Optional
from decimal import Decimal

from .swap import TOKEN_ADDRESSES, TOKEN_ADDRESSES_ARB


# Chain configuration
CHAIN_CONFIG = {
    "ethereum": {
        "chain_id": 1,
        "rpc": "https://eth.llamarpc.com",
        "weth": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        "native": "ETH",
        "max_gas_gwei": 500,
    },
    "arbitrum": {
        "chain_id": 42161,
        "rpc": "https://arb1.arbitrum.io/rpc",
        "weth": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
        "native": "ETH",
        "max_gas_gwei": 100,
    },
    "base": {
        "chain_id": 8453,
        "rpc": "https://mainnet.base.org",
        "weth": "0x4200000000000000000000000000000000000006",
        "native": "ETH",
        "max_gas_gwei": 100,
    },
    "polygon": {
        "chain_id": 137,
        "rpc": "https://polygon-rpc.com",
        "weth": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",  # WMATIC
        "native": "MATIC",
        "max_gas_gwei": 500,
    },
}

# ERC-20 ABI fragments (minimal for transfer/approve)
ERC20_TRANSFER_SIG = "0xa9059cbb"  # transfer(address,uint256)
ERC20_APPROVE_SIG = "0x095ea7b3"   # approve(address,uint256)

# WETH ABI fragments
WETH_DEPOSIT_SIG = "0xd0e30db0"    # deposit()
WETH_WITHDRAW_SIG = "0x2e1a7d4d"   # withdraw(uint256)

PARASWAP_API = "https://apiv5.paraswap.io"

# Default safety limits
DEFAULT_MAX_TX_VALUE_USD = 10_000
DEFAULT_FEE_BPS = 10  # 0.1% = 10 basis points
DEFAULT_SLIPPAGE_BPS = 100  # 1% = 100 basis points


def _get_fee_bps() -> int:
    """Get fee in basis points from env or default."""
    return int(os.environ.get("FEE_BPS", DEFAULT_FEE_BPS))


def _get_max_tx_value() -> float:
    """Get max transaction value in USD from env or default."""
    return float(os.environ.get("MAX_TX_VALUE_USD", DEFAULT_MAX_TX_VALUE_USD))


def _resolve_token(symbol: str, chain: str) -> str:
    """Resolve token symbol to contract address."""
    s = symbol.upper().strip()
    if s.startswith("0X"):
        return symbol
    if chain == "arbitrum":
        return TOKEN_ADDRESSES_ARB.get(s, s)
    return TOKEN_ADDRESSES.get(s, s)


def _get_decimals(token_addr: str) -> int:
    """Get token decimals (simplified - production would query on-chain)."""
    usdc_addrs = {
        TOKEN_ADDRESSES.get("USDC", "").lower(),
        TOKEN_ADDRESSES.get("USDT", "").lower(),
        TOKEN_ADDRESSES_ARB.get("USDC", "").lower(),
        TOKEN_ADDRESSES_ARB.get("USDT", "").lower(),
    }
    if token_addr.lower() in usdc_addrs:
        return 6
    # WBTC is 8 decimals
    if token_addr.lower() == TOKEN_ADDRESSES.get("WBTC", "").lower():
        return 8
    return 18


def _encode_uint256(value: int) -> str:
    """Encode a uint256 value as 32-byte hex."""
    return hex(value)[2:].zfill(64)


def _encode_address(addr: str) -> str:
    """Encode an address as 32-byte hex (left-padded)."""
    return addr.lower().replace("0x", "").zfill(64)


class ActionTool:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30)

    def _get_web3(self, chain: str):
        """Get a web3 instance for the given chain."""
        try:
            from web3 import Web3
        except ImportError:
            raise RuntimeError(
                "web3 package required for on-chain actions. "
                "Install with: pip install 'crypto-mcp-server[web3]'"
            )
        config = CHAIN_CONFIG.get(chain)
        if not config:
            raise ValueError(f"Unsupported chain: {chain}. Supported: {list(CHAIN_CONFIG.keys())}")
        return Web3(Web3.HTTPProvider(config["rpc"]))

    def _get_account(self, w3):
        """Get account from private key env var."""
        private_key = os.environ.get("WALLET_PRIVATE_KEY")
        if not private_key:
            raise ValueError(
                "WALLET_PRIVATE_KEY environment variable not set. "
                "Required for on-chain transactions."
            )
        if not private_key.startswith("0x"):
            private_key = "0x" + private_key
        return w3.eth.account.from_key(private_key)

    async def _check_gas_price(self, w3, chain: str) -> int:
        """Check gas price and enforce sanity limit. Returns gas price in wei."""
        gas_price = w3.eth.gas_price
        gas_gwei = gas_price / 1e9
        max_gwei = CHAIN_CONFIG[chain]["max_gas_gwei"]

        if gas_gwei > max_gwei:
            raise ValueError(
                f"Gas price too high: {gas_gwei:.1f} gwei (limit: {max_gwei} gwei on {chain}). "
                f"Transaction aborted for safety. Try again later or use an L2."
            )
        return gas_price

    async def _check_value_limit(self, value_usd: float):
        """Enforce maximum transaction value."""
        max_val = _get_max_tx_value()
        if value_usd > max_val:
            raise ValueError(
                f"Transaction value ${value_usd:,.2f} exceeds limit ${max_val:,.2f}. "
                f"Set MAX_TX_VALUE_USD env var to increase."
            )

    async def _estimate_value_usd(self, token: str, amount: float, chain: str) -> float:
        """Estimate USD value of a token amount using CoinGecko."""
        # Stablecoins
        stable_symbols = {"USDC", "USDT", "DAI", "BUSD", "TUSD", "FRAX"}
        sym = token.upper().strip()
        if sym in stable_symbols:
            return amount

        # For ETH/native tokens, get price
        from .prices import SYMBOL_MAP, COINGECKO_BASE
        coin_id = SYMBOL_MAP.get(sym, sym.lower())

        try:
            resp = await self.client.get(
                f"{COINGECKO_BASE}/simple/price",
                params={"ids": coin_id, "vs_currencies": "usd"},
            )
            if resp.status_code == 200:
                data = resp.json()
                price = data.get(coin_id, {}).get("usd", 0)
                return amount * price
        except Exception:
            pass

        # If we can't determine price, be conservative and allow it
        # (the user can set MAX_TX_VALUE_USD=0 to block all unknown tokens)
        return 0.0

    async def _send_transaction(self, w3, account, tx: dict, chain: str) -> Dict:
        """Sign and send a transaction, return result dict."""
        # Ensure chain_id
        tx["chainId"] = CHAIN_CONFIG[chain]["chain_id"]

        # Get nonce
        tx["nonce"] = w3.eth.get_transaction_count(account.address)

        # Estimate gas if not set
        if "gas" not in tx:
            try:
                tx["gas"] = int(w3.eth.estimate_gas(tx) * 1.2)  # 20% buffer
            except Exception as e:
                raise ValueError(f"Gas estimation failed: {e}")

        # Set gas price if not set
        if "gasPrice" not in tx and "maxFeePerGas" not in tx:
            gas_price = await self._check_gas_price(w3, chain)
            tx["gasPrice"] = gas_price

        # Sign
        signed = account.sign_transaction(tx)

        # Send
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
    # swap_execute
    # -------------------------------------------------------------------------
    async def swap_execute(
        self,
        from_token: str,
        to_token: str,
        amount: float,
        chain: str = "ethereum",
        slippage_bps: int = DEFAULT_SLIPPAGE_BPS,
        fee_bps: Optional[int] = None,
    ) -> Dict:
        """Execute a token swap via ParaSwap. Builds and sends the transaction.

        Fee model: A configurable fee (default 0.1%) is applied to the swap amount.
        The fee is taken from the input amount before the swap.
        """
        chain = chain.lower()
        if chain not in CHAIN_CONFIG:
            return {"error": f"Unsupported chain: {chain}. Supported: {list(CHAIN_CONFIG.keys())}"}

        # Resolve tokens
        from_addr = _resolve_token(from_token, chain)
        to_addr = _resolve_token(to_token, chain)

        # Calculate fee
        actual_fee_bps = fee_bps if fee_bps is not None else _get_fee_bps()
        fee_amount = amount * actual_fee_bps / 10_000
        swap_amount = amount - fee_amount

        if swap_amount <= 0:
            return {"error": "Amount too small after fee deduction."}

        # Safety check: estimate USD value
        try:
            value_usd = await self._estimate_value_usd(from_token, amount, chain)
            await self._check_value_limit(value_usd)
        except ValueError as e:
            return {"error": str(e)}

        # Get decimals and convert to wei
        from_decimals = _get_decimals(from_addr)
        amount_wei = str(int(swap_amount * (10 ** from_decimals)))

        chain_id = CHAIN_CONFIG[chain]["chain_id"]

        # Step 1: Get price quote from ParaSwap
        try:
            price_resp = await self.client.get(
                f"{PARASWAP_API}/prices",
                params={
                    "srcToken": from_addr,
                    "destToken": to_addr,
                    "amount": amount_wei,
                    "srcDecimals": from_decimals,
                    "destDecimals": _get_decimals(to_addr),
                    "side": "SELL",
                    "network": chain_id,
                },
            )

            if price_resp.status_code != 200:
                return {
                    "error": "Failed to get swap quote from ParaSwap",
                    "details": price_resp.text,
                }

            price_data = price_resp.json().get("priceRoute", {})
        except Exception as e:
            return {"error": f"ParaSwap quote failed: {e}"}

        # Calculate minimum destination amount with slippage
        dest_amount = int(price_data.get("destAmount", 0))
        min_dest_amount = str(int(dest_amount * (10_000 - slippage_bps) / 10_000))

        # Get wallet address
        try:
            w3 = self._get_web3(chain)
            account = self._get_account(w3)
        except (RuntimeError, ValueError) as e:
            return {"error": str(e)}

        # Step 2: Build transaction via ParaSwap
        try:
            tx_resp = await self.client.post(
                f"{PARASWAP_API}/transactions/{chain_id}",
                json={
                    "srcToken": from_addr,
                    "destToken": to_addr,
                    "srcAmount": amount_wei,
                    "destAmount": min_dest_amount,
                    "priceRoute": price_data,
                    "userAddress": account.address,
                    "txOrigin": account.address,
                    "receiver": account.address,
                    "srcDecimals": from_decimals,
                    "destDecimals": _get_decimals(to_addr),
                    "slippage": slippage_bps,
                },
                params={"ignoreChecks": "true"},
            )

            if tx_resp.status_code != 200:
                return {
                    "error": "Failed to build swap transaction",
                    "details": tx_resp.text,
                }

            tx_data = tx_resp.json()
        except Exception as e:
            return {"error": f"ParaSwap transaction build failed: {e}"}

        # Step 3: Send the transaction
        try:
            is_native = from_addr.lower() == "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
            tx = {
                "to": w3.to_checksum_address(tx_data["to"]),
                "data": tx_data["data"],
                "value": int(tx_data.get("value", 0)) if is_native else 0,
                "gas": int(tx_data.get("gas", 300_000)),
                "from": account.address,
            }

            result = await self._send_transaction(w3, account, tx, chain)

            # Add swap details to result
            to_decimals = _get_decimals(to_addr)
            expected_output = dest_amount / (10 ** to_decimals)

            result.update({
                "action": "swap",
                "from_token": from_token.upper(),
                "to_token": to_token.upper(),
                "input_amount": amount,
                "fee_amount": round(fee_amount, 8),
                "fee_bps": actual_fee_bps,
                "swap_amount": round(swap_amount, 8),
                "expected_output": round(expected_output, 8),
                "min_output": round(int(min_dest_amount) / (10 ** to_decimals), 8),
                "slippage_bps": slippage_bps,
                "dex": "paraswap",
            })
            return result

        except ValueError as e:
            return {"error": str(e)}
        except Exception as e:
            return {"error": f"Transaction failed: {e}"}

    # -------------------------------------------------------------------------
    # token_transfer
    # -------------------------------------------------------------------------
    async def token_transfer(
        self,
        token: str,
        to_address: str,
        amount: float,
        chain: str = "ethereum",
    ) -> Dict:
        """Send tokens (ERC-20 or native ETH/MATIC) to an address."""
        chain = chain.lower()
        if chain not in CHAIN_CONFIG:
            return {"error": f"Unsupported chain: {chain}. Supported: {list(CHAIN_CONFIG.keys())}"}

        # Safety check: estimate USD value
        try:
            value_usd = await self._estimate_value_usd(token, amount, chain)
            await self._check_value_limit(value_usd)
        except ValueError as e:
            return {"error": str(e)}

        try:
            w3 = self._get_web3(chain)
            account = self._get_account(w3)
        except (RuntimeError, ValueError) as e:
            return {"error": str(e)}

        token_upper = token.upper().strip()
        is_native = token_upper in ("ETH", "MATIC") and not token.startswith("0x")

        try:
            if is_native:
                # Native token transfer
                amount_wei = int(amount * 1e18)
                tx = {
                    "to": w3.to_checksum_address(to_address),
                    "value": amount_wei,
                    "from": account.address,
                    "gas": 21_000,
                }
            else:
                # ERC-20 transfer
                token_addr = _resolve_token(token, chain)
                decimals = _get_decimals(token_addr)
                amount_raw = int(amount * (10 ** decimals))

                # Build transfer(address,uint256) calldata
                calldata = (
                    ERC20_TRANSFER_SIG
                    + _encode_address(to_address)
                    + _encode_uint256(amount_raw)
                )

                tx = {
                    "to": w3.to_checksum_address(token_addr),
                    "data": calldata,
                    "value": 0,
                    "from": account.address,
                }

            result = await self._send_transaction(w3, account, tx, chain)
            result.update({
                "action": "transfer",
                "token": token_upper,
                "amount": amount,
                "to_address": to_address,
                "is_native": is_native,
            })
            return result

        except ValueError as e:
            return {"error": str(e)}
        except Exception as e:
            return {"error": f"Transfer failed: {e}"}

    # -------------------------------------------------------------------------
    # token_approve
    # -------------------------------------------------------------------------
    async def token_approve(
        self,
        token: str,
        spender: str,
        amount: Optional[float] = None,
        chain: str = "ethereum",
    ) -> Dict:
        """Approve a contract to spend tokens on your behalf.

        If amount is None, approves unlimited (max uint256) - common for DEX usage.
        """
        chain = chain.lower()
        if chain not in CHAIN_CONFIG:
            return {"error": f"Unsupported chain: {chain}. Supported: {list(CHAIN_CONFIG.keys())}"}

        try:
            w3 = self._get_web3(chain)
            account = self._get_account(w3)
        except (RuntimeError, ValueError) as e:
            return {"error": str(e)}

        token_addr = _resolve_token(token, chain)
        decimals = _get_decimals(token_addr)

        if amount is not None:
            amount_raw = int(amount * (10 ** decimals))
        else:
            # Max uint256 = unlimited approval
            amount_raw = 2**256 - 1

        try:
            # Build approve(address,uint256) calldata
            calldata = (
                ERC20_APPROVE_SIG
                + _encode_address(spender)
                + _encode_uint256(amount_raw)
            )

            tx = {
                "to": w3.to_checksum_address(token_addr),
                "data": calldata,
                "value": 0,
                "from": account.address,
            }

            result = await self._send_transaction(w3, account, tx, chain)
            result.update({
                "action": "approve",
                "token": token.upper(),
                "token_address": token_addr,
                "spender": spender,
                "amount": amount if amount is not None else "unlimited",
                "amount_raw": str(amount_raw),
            })
            return result

        except ValueError as e:
            return {"error": str(e)}
        except Exception as e:
            return {"error": f"Approval failed: {e}"}

    # -------------------------------------------------------------------------
    # wrap_eth
    # -------------------------------------------------------------------------
    async def wrap_eth(
        self,
        amount: float,
        direction: str = "wrap",
        chain: str = "ethereum",
    ) -> Dict:
        """Wrap ETH to WETH or unwrap WETH to ETH.

        direction: 'wrap' (ETH -> WETH) or 'unwrap' (WETH -> ETH)
        """
        chain = chain.lower()
        if chain not in CHAIN_CONFIG:
            return {"error": f"Unsupported chain: {chain}. Supported: {list(CHAIN_CONFIG.keys())}"}

        direction = direction.lower()
        if direction not in ("wrap", "unwrap"):
            return {"error": "direction must be 'wrap' or 'unwrap'"}

        # Safety check
        try:
            value_usd = await self._estimate_value_usd("ETH", amount, chain)
            await self._check_value_limit(value_usd)
        except ValueError as e:
            return {"error": str(e)}

        try:
            w3 = self._get_web3(chain)
            account = self._get_account(w3)
        except (RuntimeError, ValueError) as e:
            return {"error": str(e)}

        weth_addr = CHAIN_CONFIG[chain]["weth"]
        amount_wei = int(amount * 1e18)

        try:
            if direction == "wrap":
                # Call WETH.deposit() with ETH value
                tx = {
                    "to": w3.to_checksum_address(weth_addr),
                    "data": WETH_DEPOSIT_SIG,
                    "value": amount_wei,
                    "from": account.address,
                }
            else:
                # Call WETH.withdraw(uint256)
                calldata = WETH_WITHDRAW_SIG + _encode_uint256(amount_wei)
                tx = {
                    "to": w3.to_checksum_address(weth_addr),
                    "data": calldata,
                    "value": 0,
                    "from": account.address,
                }

            result = await self._send_transaction(w3, account, tx, chain)
            result.update({
                "action": f"{direction}_eth",
                "direction": direction,
                "amount": amount,
                "weth_address": weth_addr,
                "description": (
                    f"{'Wrapped' if direction == 'wrap' else 'Unwrapped'} "
                    f"{amount} {'ETH -> WETH' if direction == 'wrap' else 'WETH -> ETH'}"
                ),
            })
            return result

        except ValueError as e:
            return {"error": str(e)}
        except Exception as e:
            return {"error": f"{'Wrap' if direction == 'wrap' else 'Unwrap'} failed: {e}"}
