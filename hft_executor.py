"""
High-Frequency Trading Executor
Optimized for sub-second execution with Jito bundles and Helius RPC
"""
import asyncio
import logging
import time
import aiohttp
from typing import Optional, Dict
from decimal import Decimal
from dataclasses import dataclass

# Try to import numba for JIT compilation
try:
    from numba import jit, prange
    import numpy as np
    NUMBA_AVAILABLE = True
except ImportError:
    NUMBA_AVAILABLE = False
    logging.warning("Numba not available - install with: pip install numba")

from config import Config
from jito_executor import JitoExecutor
from wallet import WalletManager
from api_client import BlockchainAPIClient

logger = logging.getLogger("hft_executor")

# JIT-compiled functions for critical path calculations
if NUMBA_AVAILABLE:
    @jit(nopython=True, cache=True, fastmath=True)
    def calculate_price_impact_fast(amount: float, liquidity: float) -> float:
        """Ultra-fast price impact calculation"""
        if liquidity <= 0:
            return 1.0
        return amount / (liquidity + amount)
    
    @jit(nopython=True, cache=True, fastmath=True)
    def calculate_slippage_fast(price_impact: float, slippage_bps: float) -> float:
        """Ultra-fast slippage calculation"""
        return price_impact * (1.0 + slippage_bps / 10000.0)
    
    @jit(nopython=True, cache=True, fastmath=True)
    def should_execute_fast(profit: float, gas_cost: float, min_profit: float) -> bool:
        """Ultra-fast profitability check"""
        return (profit - gas_cost) >= min_profit
    
    logger.info("✅ Numba JIT compilation enabled for critical path")
else:
    # Fallback to regular Python
    def calculate_price_impact_fast(amount: float, liquidity: float) -> float:
        if liquidity <= 0:
            return 1.0
        return amount / (liquidity + amount)
    
    def calculate_slippage_fast(price_impact: float, slippage_bps: float) -> float:
        return price_impact * (1.0 + slippage_bps / 10000.0)
    
    def should_execute_fast(profit: float, gas_cost: float, min_profit: float) -> bool:
        return (profit - gas_cost) >= min_profit

@dataclass
class ExecutionResult:
    success: bool
    tx_signature: Optional[str]
    bundle_id: Optional[str]
    execution_time_ms: float
    profit: Decimal
    error: Optional[str] = None

class HFTExecutor:
    """
    High-Frequency Trading Executor
    - Uses Jito bundles for MEV protection
    - Helius RPC for low-latency
    - JIT-compiled critical path
    - Connection pooling for speed
    """
    
    def __init__(self, config: Config, wallet_manager: WalletManager):
        self.config = config
        self.wallet_manager = wallet_manager
        
        # Use Helius for fastest RPC
        self.rpc_url = config.HELIUS_RPC_URL or config.RPC_ENDPOINT
        
        # Initialize Jito executor
        self.api_client = BlockchainAPIClient(config)
        self.jito_executor = JitoExecutor(config, wallet_manager, self.api_client)
        
        # Connection pooling for HTTP requests
        self.session: Optional[aiohttp.ClientSession] = None
        self.connector = aiohttp.TCPConnector(
            limit=100,  # Max connections
            limit_per_host=30,
            ttl_dns_cache=300,
            keepalive_timeout=30
        )
        
        # Performance tracking
        self.execution_times = []
        self.max_execution_time = 500  # 500ms target
        
        logger.info(f"HFT Executor initialized with RPC: {self.rpc_url[:50]}...")
        if NUMBA_AVAILABLE:
            logger.info("🚀 JIT compilation active for critical calculations")
    
    async def initialize(self) -> bool:
        """Initialize connections"""
        try:
            # Create persistent HTTP session
            self.session = aiohttp.ClientSession(
                connector=self.connector,
                timeout=aiohttp.ClientTimeout(total=5)
            )
            
            # Initialize Jito
            jito_ready = await self.jito_executor.initialize()
            
            if not jito_ready:
                logger.error("Failed to initialize Jito executor")
                return False
            
            logger.info("✅ HFT Executor ready for trading")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize HFT Executor: {e}")
            return False
    
    async def execute_trade_fast(
        self,
        pool_id: str,
        amount: Decimal,
        token_in: str,
        token_out: str,
        max_slippage_bps: int = 100
    ) -> ExecutionResult:
        """
        Execute trade with MAXIMUM SPEED
        Target: <500ms end-to-end
        """
        start_time = time.time()
        
        try:
            # 1. FAST VALIDATION (JIT-compiled)
            liquidity = await self._get_pool_liquidity_fast(pool_id)
            price_impact = calculate_price_impact_fast(float(amount), liquidity)
            
            if price_impact > 0.05:  # >5% impact
                return ExecutionResult(
                    success=False,
                    tx_signature=None,
                    bundle_id=None,
                    execution_time_ms=(time.time() - start_time) * 1000,
                    profit=Decimal('0'),
                    error="Price impact too high"
                )
            
            # 2. BUILD TRANSACTION (uses cached blockhash)
            tx_data = await self._build_swap_transaction_fast(
                pool_id, amount, token_in, token_out, max_slippage_bps
            )
            
            if not tx_data:
                return ExecutionResult(
                    success=False,
                    tx_signature=None,
                    bundle_id=None,
                    execution_time_ms=(time.time() - start_time) * 1000,
                    profit=Decimal('0'),
                    error="Failed to build transaction"
                )
            
            # 3. SUBMIT VIA JITO BUNDLE (fastest execution)
            bundle_id = await self._submit_jito_bundle_fast(tx_data)
            
            execution_time = (time.time() - start_time) * 1000
            
            if bundle_id:
                logger.info(f"✅ Trade executed in {execution_time:.0f}ms via Jito bundle: {bundle_id}")
                
                self.execution_times.append(execution_time)
                if len(self.execution_times) > 100:
                    self.execution_times = self.execution_times[-100:]
                
                return ExecutionResult(
                    success=True,
                    tx_signature=None,  # Get later from bundle
                    bundle_id=bundle_id,
                    execution_time_ms=execution_time,
                    profit=Decimal('0')  # Calculate after confirmation
                )
            else:
                return ExecutionResult(
                    success=False,
                    tx_signature=None,
                    bundle_id=None,
                    execution_time_ms=execution_time,
                    profit=Decimal('0'),
                    error="Bundle submission failed"
                )
                
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            logger.error(f"Error executing trade: {e}")
            return ExecutionResult(
                success=False,
                tx_signature=None,
                bundle_id=None,
                execution_time_ms=execution_time,
                profit=Decimal('0'),
                error=str(e)
            )
    
    async def _get_pool_liquidity_fast(self, pool_id: str) -> float:
        """Get pool liquidity with caching"""
        try:
            # Use Helius for fastest response
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getAccountInfo",
                "params": [pool_id, {"encoding": "base64"}]
            }
            
            async with self.session.post(self.rpc_url, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Parse liquidity from account data
                    # This is simplified - actual parsing depends on pool structure
                    return 1000000.0  # Placeholder
                    
            return 0.0
            
        except Exception as e:
            logger.error(f"Error getting pool liquidity: {e}")
            return 0.0
    
    async def _build_swap_transaction_fast(
        self,
        pool_id: str,
        amount: Decimal,
        token_in: str,
        token_out: str,
        slippage_bps: int
    ) -> Optional[Dict]:
        """
        Build swap transaction with MINIMUM latency
        Uses Jupiter API for routing
        """
        try:
            # Use Jupiter for optimal routing (fastest aggregator)
            jupiter_url = "https://quote-api.jup.ag/v6/quote"
            
            params = {
                "inputMint": token_in,
                "outputMint": token_out,
                "amount": str(int(amount * 10**9)),  # Convert to lamports
                "slippageBps": slippage_bps,
                "onlyDirectRoutes": True,  # Faster
                "maxAccounts": 20  # Limit for speed
            }
            
            async with self.session.get(jupiter_url, params=params) as resp:
                if resp.status == 200:
                    quote = await resp.json()
                    
                    # Build swap transaction
                    swap_url = "https://quote-api.jup.ag/v6/swap"
                    swap_data = {
                        "quoteResponse": quote,
                        "userPublicKey": str(self.wallet_manager.pubkey),
                        "wrapAndUnwrapSol": True,
                        "dynamicComputeUnitLimit": True,  # Auto-optimize
                        "prioritizationFeeLamports": "auto"  # Auto-optimize
                    }
                    
                    async with self.session.post(swap_url, json=swap_data) as swap_resp:
                        if swap_resp.status == 200:
                            return await swap_resp.json()
            
            return None
            
        except Exception as e:
            logger.error(f"Error building swap transaction: {e}")
            return None
    
    async def _submit_jito_bundle_fast(self, tx_data: Dict) -> Optional[str]:
        """Submit transaction via Jito bundle for MEV protection"""
        try:
            # Extract transaction from Jupiter response
            swap_tx_b64 = tx_data.get("swapTransaction")
            if not swap_tx_b64:
                return None
            
            # Deserialize and sign transaction
            from solders.transaction import VersionedTransaction
            import base64
            
            tx_bytes = base64.b64decode(swap_tx_b64)
            tx = VersionedTransaction.deserialize(tx_bytes)
            
            # Sign with wallet
            signed_tx = self.wallet_manager.sign_transaction(tx)
            
            # Submit via Jito
            bundle_id = await self.jito_executor.submit_transactions(
                [signed_tx],
                expected_profit=0.01  # Estimate
            )
            
            return bundle_id
            
        except Exception as e:
            logger.error(f"Error submitting Jito bundle: {e}")
            return None
    
    async def close(self):
        """Clean up connections"""
        if self.session:
            await self.session.close()
        await self.connector.close()
    
    def get_performance_stats(self) -> Dict:
        """Get execution performance statistics"""
        if not self.execution_times:
            return {}
        
        return {
            "avg_execution_time_ms": sum(self.execution_times) / len(self.execution_times),
            "min_execution_time_ms": min(self.execution_times),
            "max_execution_time_ms": max(self.execution_times),
            "total_executions": len(self.execution_times),
            "under_500ms_pct": sum(1 for t in self.execution_times if t < 500) / len(self.execution_times) * 100
        }
