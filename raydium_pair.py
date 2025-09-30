from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from dataclasses import dataclass
import asyncio
import logging
from solana.rpc.commitment import Commitment
from solana.rpc.async_api import AsyncClient as Client
from solders.transaction import Transaction
from solders.pubkey import Pubkey

logger = logging.getLogger("RaydiumPair")

@dataclass
class TokenBalances:
    token_a: Decimal
    token_b: Decimal

class RaydiumPair:
    """Represents a Raydium trading pair with balance tracking and swap calculations"""
    
    # Raydium constants
    TRADE_FEE_NUMERATOR = 25      # 0.25% fee
    TRADE_FEE_DENOMINATOR = 10000
    
    def __init__(self, market_address: str, tokens: List[str], protocol: str = "raydium"):
        self.market_address = market_address
        self.tokens = tokens  # [token_a_address, token_b_address]
        self.protocol = protocol
        self._token_balances = {
            tokens[0]: Decimal('0'),
            tokens[1]: Decimal('0')
        }
        
        # Initialize RPC client (should be injected in production)
        self.rpc_client = Client("https://api.mainnet-beta.solana.com")
        
    def get_balance(self, token_address: str) -> Decimal:
        """Get the current balance of a token in the pool"""
        if token_address not in self._token_balances:
            raise ValueError(f"Token {token_address} not found in pair")
        return self._token_balances[token_address]

    def set_reserves(self, token_a_amount: Decimal, token_b_amount: Decimal):
        """Update pool reserves with new balance information"""
        self._token_balances[self.tokens[0]] = token_a_amount
        self._token_balances[self.tokens[1]] = token_b_amount

    def get_tokens_out(self, token_in: str, token_out: str, amount_in: Decimal) -> Decimal:
        """Calculate output amount for a given input amount"""
        if token_in not in self.tokens or token_out not in self.tokens:
            raise ValueError("Invalid token addresses")
            
        reserve_in = self._token_balances[token_in]
        reserve_out = self._token_balances[token_out]
        
        return self._calculate_output_amount(amount_in, reserve_in, reserve_out)

    def get_tokens_in(self, token_in: str, token_out: str, amount_out: Decimal) -> Decimal:
        """Calculate required input amount for a desired output amount"""
        if token_in not in self.tokens or token_out not in self.tokens:
            raise ValueError("Invalid token addresses")
            
        reserve_in = self._token_balances[token_in]
        reserve_out = self._token_balances[token_out]
        
        return self._calculate_input_amount(amount_out, reserve_in, reserve_out)

    def _calculate_output_amount(self, amount_in: Decimal, reserve_in: Decimal, reserve_out: Decimal) -> Decimal:
        """Calculate output amount based on Raydium's AMM formula"""
        if amount_in <= 0 or reserve_in <= 0 or reserve_out <= 0:
            return Decimal('0')
            
        # Calculate fee-adjusted input
        amount_in_with_fee = amount_in * (10000 - self.TRADE_FEE_NUMERATOR)
        
        # Calculate output amount using constant product formula
        numerator = amount_in_with_fee * reserve_out
        denominator = (reserve_in * self.TRADE_FEE_DENOMINATOR) + amount_in_with_fee
        
        return numerator / denominator

    def _calculate_input_amount(self, amount_out: Decimal, reserve_in: Decimal, reserve_out: Decimal) -> Decimal:
        """Calculate required input amount for desired output"""
        if amount_out <= 0 or reserve_in <= 0 or reserve_out <= 0 or amount_out >= reserve_out:
            return Decimal('0')
            
        # Using reverse constant product formula with fees
        numerator = reserve_in * amount_out * self.TRADE_FEE_DENOMINATOR
        denominator = (reserve_out - amount_out) * (10000 - self.TRADE_FEE_NUMERATOR)
        
        return (numerator / denominator) + Decimal('1')

    async def prepare_swap_transaction(self, 
                                     token_in: str, 
                                     token_out: str, 
                                     amount_in: Decimal,
                                     user_wallet: Pubkey,
                                     slippage_tolerance: Decimal = Decimal('0.005')) -> Optional[Transaction]:
        """Prepare a swap transaction"""
        try:
            # Calculate expected output
            amount_out = self.get_tokens_out(token_in, token_out, amount_in)
            if amount_out <= 0:
                logger.error("Invalid swap amount calculated")
                return None
                
            # Apply slippage tolerance
            min_amount_out = amount_out * (1 - slippage_tolerance)
            
            # Create Raydium swap instruction (simplified version)
            # In production, you'd need to add proper Raydium program calls
            swap_ix = self._create_swap_instruction(
                user_wallet,
                token_in,
                token_out,
                amount_in,
                min_amount_out
            )
            
            # Create and return transaction
            transaction = Transaction()
            transaction.add(swap_ix)
            
            return transaction
            
        except Exception as e:
            logger.error(f"Error preparing swap transaction: {str(e)}")
            return None
            
    def _create_swap_instruction(self,
                             user_wallet: Pubkey,
                             token_in: str,
                             token_out: str,
                             amount_in: Decimal,
                             min_amount_out: Decimal):
        """Create a Raydium swap instruction"""
        # This is a placeholder - in production, implement actual Raydium swap instruction
        # You'll need to implement proper Raydium program call here
        raise NotImplementedError("Swap instruction creation not implemented")

    def get_price_impact(self, token_in: str, amount_in: Decimal) -> Decimal:
        """Calculate price impact of a trade using sophisticated modeling
        
        This implementation uses advanced AMM modeling that accounts for:
        1. Slippage from trade size relative to pool depth
        2. Price impact from removing liquidity
        3. Protocol fees and their effect on final execution
        4. Non-linear slippage increases for large trades
        """
        if token_in not in self.tokens:
            raise ValueError("Invalid token address")
            
        token_out = self.tokens[1] if token_in == self.tokens[0] else self.tokens[0]
        
        # Get current state
        reserve_in = self._token_balances[token_in]
        reserve_out = self._token_balances[token_out]
        
        if reserve_in <= 0 or reserve_out <= 0:
            return Decimal(1)  # 100% impact for empty pools
            
        # Calculate spot price (pre-trade)
        spot_price = reserve_out / reserve_in
        
        # Calculate output with fees
        amount_out = self.get_tokens_out(token_in, token_out, amount_in)
        
        if amount_out <= 0:
            return Decimal(1)
            
        # Calculate execution price
        execution_price = amount_out / amount_in
        
        # Base impact from price movement
        base_impact = (spot_price - execution_price) / spot_price
        
        # Additional impact factors
        size_factor = amount_in / reserve_in  # Relative size of trade
        depth_factor = Decimal(min(1, (reserve_in * reserve_out).sqrt() / amount_in))
        
        # Combine factors with non-linear scaling for large trades
        total_impact = base_impact * (1 + size_factor) / depth_factor
        
        # Add protocol fee impact
        fee_impact = Decimal(self.TRADE_FEE_NUMERATOR) / Decimal(self.TRADE_FEE_DENOMINATOR)
        
        # Normalize and cap total impact
        final_impact = min(Decimal(1), total_impact + fee_impact)
        
        return max(Decimal(0), final_impact)  # Ensure non-negative
        
    def get_depth_impact(self, token_in: str, amount_in: Decimal) -> Decimal:
        """Calculate the impact on pool depth
        
        This measures how much the trade will affect the pool's ability to facilitate
        future trades at similar sizes.
        """
        if token_in not in self.tokens:
            raise ValueError("Invalid token address")
            
        reserve_in = self._token_balances[token_in]
        
        if reserve_in <= 0:
            return Decimal(1)
            
        # Impact increases non-linearly with size relative to reserves
        relative_size = amount_in / reserve_in
        depth_impact = relative_size * (1 + relative_size)
        
        return min(Decimal(1), depth_impact)
        
    def get_slippage_bounds(self, 
                         token_in: str, 
                         amount_in: Decimal,
                         confidence_interval: Decimal = Decimal('0.95')) -> Tuple[Decimal, Decimal]:
        """Calculate expected slippage bounds with given confidence interval
        
        Returns (min_output, max_output) tuple representing the expected range
        """
        token_out = self.tokens[1] if token_in == self.tokens[0] else self.tokens[0]
        base_output = self.get_tokens_out(token_in, token_out, amount_in)
        impact = self.get_price_impact(token_in, amount_in)
        
        # Wider bounds for larger trades due to increased uncertainty
        uncertainty = impact * (1 - confidence_interval)
        
        min_output = base_output * (1 - uncertainty)
        max_output = base_output * (1 + uncertainty * Decimal('0.5'))  # Upside is less likely
        
        return (min_output, max_output)

    def should_update_reserves(self, last_update_time: float, update_threshold: float = 60) -> bool:
        """Determine if pool reserves should be updated based on time threshold"""
        import time
        current_time = time.time()
        return (current_time - last_update_time) >= update_threshold

    async def update_reserves_from_chain(self) -> bool:
        """Update pool reserves directly from the blockchain"""
        try:
            # Fetch pool data from Raydium program
            # This is a placeholder - implement actual Raydium program account fetching
            pool_data = await self.rpc_client.get_account_info(
                Pubkey.from_string(self.market_address),
                commitment=Commitment.confirmed
            )
            
            if not pool_data or not pool_data.value:
                logger.error("Failed to fetch pool data")
                return False
                
            # Parse pool data and update reserves
            # You'll need to implement proper Raydium pool data parsing here
            # self.set_reserves(token_a_amount, token_b_amount)
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating reserves: {str(e)}")
            return False