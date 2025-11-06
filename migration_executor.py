from typing import List, Optional, Tuple, Dict
from dataclasses import dataclass
from decimal import Decimal
import logging
import asyncio
import time
import json
from datetime import datetime, timedelta
from solders.pubkey import Pubkey
from solders.transaction import Transaction, VersionedTransaction
from solders.signature import Signature

from config import Config
from raydium_pair import RaydiumPair
from api_client import BlockchainAPIClient, PoolData
from pool_analyzer import PoolAnalyzer
from migration_sniper import MigrationContract

logger = logging.getLogger("MigrationExecutor")

@dataclass
class MigrationResult:
    success: bool
    tx_signature: Optional[str]
    execution_time: float  # In seconds
    amount_in: Decimal
    amount_out: Decimal
    effective_price: Decimal
    fees_paid: Decimal
    error_message: Optional[str] = None

class MigrationExecutor:
    """Handles the execution of migration trades between Raydium V3 and V4 pools"""
    
    def __init__(self, config: Config, pool_analyzer: PoolAnalyzer, api_client: BlockchainAPIClient):
        self.config = config
        self.pool_analyzer = pool_analyzer
        self.api_client = api_client
        
        # Migration configuration (use safe defaults if missing in Config)
        self.max_priority_fee = getattr(self.config, "MAX_PRIORITY_FEE", 2_000_000)  # lamports
        self.min_priority_fee = getattr(self.config, "MIN_PRIORITY_FEE", 100_000)    # lamports
        self.fee_adjustment_factor = 1.25  # Increase fee by 25% for each failed attempt
        
        # Execution parameters
        self.max_retries = 3
        self.retry_delay = 2  # seconds
        
        # Circuit breaker parameters
        self.max_daily_loss = getattr(self.config, "MAX_DAILY_LOSS_SOL", Decimal("0.1"))  # 0.1 SOL
        self.max_daily_trades = getattr(self.config, "MAX_DAILY_TRADES", 5)
        self.blacklist_after_fails = getattr(self.config, "BLACKLIST_AFTER_FAILS", 2)
        
        # Trade tracking
        self.trade_history: List[Dict] = []
        self.token_failures: Dict[str, int] = {}  # Track failures per token
        self.blacklisted_tokens: set = set()
        self.circuit_breaker_active = False
        
        # Load trade history
        self._load_trade_history()
        
    def _load_trade_history(self):
        """Load trade history from disk"""
        try:
            with open('data/trade_history.json', 'r') as f:
                data = json.load(f)
                self.trade_history = data.get('trades', [])
                self.token_failures = data.get('token_failures', {})
                self.blacklisted_tokens = set(data.get('blacklisted_tokens', []))
        except FileNotFoundError:
            logger.info("No trade history found, starting fresh")
        except Exception as e:
            logger.error(f"Error loading trade history: {e}")
    
    def _save_trade_history(self):
        """Save trade history to disk"""
        try:
            with open('data/trade_history.json', 'w') as f:
                json.dump({
                    'trades': self.trade_history[-100:],  # Keep last 100 trades
                    'token_failures': self.token_failures,
                    'blacklisted_tokens': list(self.blacklisted_tokens)
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving trade history: {e}")
    
    async def check_circuit_breaker(self) -> bool:
        """Check if circuit breaker should be triggered"""
        try:
            # Check if manually triggered
            if self.circuit_breaker_active:
                logger.error("Circuit breaker ACTIVE - trading halted")
                return False
            
            # Calculate daily P&L
            daily_pnl = await self._calculate_daily_pnl()
            
            # Check daily loss limit
            if daily_pnl < -self.max_daily_loss:
                logger.error(f"🚨 CIRCUIT BREAKER: Daily loss {float(daily_pnl):.4f} SOL exceeds limit {float(self.max_daily_loss):.4f} SOL")
                self.circuit_breaker_active = True
                await self._send_emergency_alert(f"Daily loss limit exceeded: {float(daily_pnl):.4f} SOL")
                return False
            
            # Check daily trade limit
            daily_trades = self._count_daily_trades()
            if daily_trades >= self.max_daily_trades:
                logger.warning(f"Daily trade limit reached: {daily_trades}/{self.max_daily_trades}")
                return False
            
            # Check recent failure rate
            recent_failures = self._count_recent_failures()
            if recent_failures >= 3:
                logger.error(f"🚨 CIRCUIT BREAKER: {recent_failures} consecutive failures detected")
                self.circuit_breaker_active = True
                await self._send_emergency_alert(f"Too many failures: {recent_failures} consecutive")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking circuit breaker: {e}")
            return False
    
    async def _calculate_daily_pnl(self) -> Decimal:
        """Calculate profit/loss for the last 24 hours"""
        try:
            cutoff = datetime.now() - timedelta(hours=24)
            cutoff_ts = cutoff.timestamp()
            
            daily_trades = [t for t in self.trade_history if t.get('timestamp', 0) > cutoff_ts]
            
            total_pnl = Decimal('0')
            for trade in daily_trades:
                if trade.get('success'):
                    # Calculate net: (amount_out - amount_in - fees)
                    amount_in = Decimal(str(trade.get('amount_in', 0)))
                    amount_out = Decimal(str(trade.get('amount_out', 0)))
                    fees = Decimal(str(trade.get('fees_paid', 0)))
                    total_pnl += (amount_out - amount_in - fees)
                else:
                    # Failed trades lose fees
                    fees = Decimal(str(trade.get('fees_paid', 0.001)))  # Estimate 0.001 SOL if not recorded
                    total_pnl -= fees
            
            return total_pnl
            
        except Exception as e:
            logger.error(f"Error calculating daily P&L: {e}")
            return Decimal('0')
    
    def _count_daily_trades(self) -> int:
        """Count trades in the last 24 hours"""
        try:
            cutoff = datetime.now() - timedelta(hours=24)
            cutoff_ts = cutoff.timestamp()
            return sum(1 for t in self.trade_history if t.get('timestamp', 0) > cutoff_ts)
        except Exception as e:
            logger.error(f"Error counting daily trades: {e}")
            return 0
    
    def _count_recent_failures(self, window: int = 5) -> int:
        """Count consecutive failures in recent trades"""
        try:
            recent = self.trade_history[-window:]
            consecutive_failures = 0
            
            for trade in reversed(recent):
                if not trade.get('success', False):
                    consecutive_failures += 1
                else:
                    break  # Stop at first success
            
            return consecutive_failures
            
        except Exception as e:
            logger.error(f"Error counting failures: {e}")
            return 0
    
    async def _send_emergency_alert(self, message: str):
        """Send emergency alert (could integrate with Telegram/email)"""
        logger.critical(f"🚨 EMERGENCY: {message}")
        # TODO: Add Telegram/email notification here
    
    def _record_trade(self, migration_info: MigrationContract, result: MigrationResult):
        """Record trade result for circuit breaker tracking"""
        try:
            trade_record = {
                'timestamp': time.time(),
                'token': migration_info.target_pool,
                'success': result.success,
                'amount_in': str(result.amount_in),
                'amount_out': str(result.amount_out),
                'fees_paid': str(result.fees_paid),
                'tx_signature': result.tx_signature,
                'error': result.error_message
            }
            
            self.trade_history.append(trade_record)
            
            # Track token failures
            if not result.success:
                token = migration_info.target_pool
                self.token_failures[token] = self.token_failures.get(token, 0) + 1
                
                # Blacklist token if too many failures
                if self.token_failures[token] >= self.blacklist_after_fails:
                    self.blacklisted_tokens.add(token)
                    logger.warning(f"Blacklisted token {token} after {self.token_failures[token]} failures")
            
            # Save updated history
            self._save_trade_history()
            
        except Exception as e:
            logger.error(f"Error recording trade: {e}")
    
    def is_token_blacklisted(self, token: str) -> bool:
        """Check if token is blacklisted"""
        return token in self.blacklisted_tokens
    
    async def execute_migration(self,
                              migration_info: MigrationContract,
                              amount: Decimal,
                              slippage_tolerance: Decimal = Decimal('0.02')) -> MigrationResult:
        """Execute a migration trade with retry logic and dynamic fee adjustment"""
        import time
        start_time = time.time()
        
        # Check circuit breaker FIRST
        if not await self.check_circuit_breaker():
            return MigrationResult(
                success=False,
                tx_signature=None,
                execution_time=0,
                amount_in=amount,
                amount_out=Decimal(0),
                effective_price=Decimal(0),
                fees_paid=Decimal(0),
                error_message="Circuit breaker active - trading halted"
            )
        
        # Check if token is blacklisted
        if self.is_token_blacklisted(migration_info.target_pool):
            return MigrationResult(
                success=False,
                tx_signature=None,
                execution_time=0,
                amount_in=amount,
                amount_out=Decimal(0),
                effective_price=Decimal(0),
                fees_paid=Decimal(0),
                error_message="Token is blacklisted due to previous failures"
            )
        
        try:
            # Initial validation
            if not await self._validate_migration_state(migration_info):
                return MigrationResult(
                    success=False,
                    tx_signature=None,
                    execution_time=0,
                    amount_in=amount,
                    amount_out=Decimal(0),
                    effective_price=Decimal(0),
                    fees_paid=Decimal(0),
                    error_message="Invalid migration state"
                )
                
            # Prepare pools
            v3_pool = RaydiumPair(migration_info.source_pool)
            v4_pool = RaydiumPair(migration_info.target_pool)
            
            # Calculate optimal execution path
            execution_plan = await self._plan_execution(
                v3_pool,
                v4_pool,
                amount,
                slippage_tolerance
            )
            
            if not execution_plan:
                return MigrationResult(
                    success=False,
                    tx_signature=None,
                    execution_time=time.time() - start_time,
                    amount_in=amount,
                    amount_out=Decimal(0),
                    effective_price=Decimal(0),
                    fees_paid=Decimal(0),
                    error_message="Failed to create execution plan"
                )
                
            # Execute with retries
            priority_fee = self.min_priority_fee
            for attempt in range(self.max_retries):
                try:
                    result = await self._execute_transaction(
                        execution_plan,
                        priority_fee
                    )
                    
                    if result.success:
                        # Record successful trade
                        self._record_trade(migration_info, result)
                        return result
                        
                    # Increase priority fee for next attempt
                    priority_fee = min(
                        self.max_priority_fee,
                        priority_fee * self.fee_adjustment_factor
                    )
                    
                    await asyncio.sleep(self.retry_delay)
                    
                except Exception as e:
                    logger.error(f"Execution attempt {attempt + 1} failed: {str(e)}")
                    if attempt == self.max_retries - 1:
                        raise
                        
            result = MigrationResult(
                success=False,
                tx_signature=None,
                execution_time=time.time() - start_time,
                amount_in=amount,
                amount_out=Decimal(0),
                effective_price=Decimal(0),
                fees_paid=Decimal(0),
                error_message=f"Failed after {self.max_retries} attempts"
            )
            self._record_trade(migration_info, result)
            return result
            
        except Exception as e:
            logger.error(f"Migration execution failed: {str(e)}")
            result = MigrationResult(
                success=False,
                tx_signature=None,
                execution_time=time.time() - start_time,
                amount_in=amount,
                amount_out=Decimal(0),
                effective_price=Decimal(0),
                fees_paid=Decimal(0),
                error_message=str(e)
            )
            self._record_trade(migration_info, result)
            return result
            
    async def _validate_migration_state(self, migration_info: MigrationContract) -> bool:
        """Validate that migration is still valid and active"""
        try:
            # Check migration deadline
            current_time = int(time.time())
            if current_time > migration_info.migration_deadline:
                logger.error("Migration deadline has passed")
                return False
                
            # Verify contract is still active
            contract = await self.api_client.get_migration_contract(
                migration_info.address
            )
            if not contract or not contract.is_active:
                logger.error("Migration contract is no longer active")
                return False
                
            return True
            
        except Exception as e:
            logger.error(f"Error validating migration state: {str(e)}")
            return False
            
    async def _plan_execution(self,
                            v3_pool: RaydiumPair,
                            v4_pool: RaydiumPair,
                            amount: Decimal,
                            slippage_tolerance: Decimal) -> Optional[Transaction]:
        """Create an optimal execution plan for the migration"""
        try:
            # Get latest pool states
            await v3_pool.update_reserves_from_chain()
            await v4_pool.update_reserves_from_chain()
            
            # Calculate optimal route
            base_token = v3_pool.tokens[0]
            quote_token = v3_pool.tokens[1]
            
            # Get price impact analysis
            v3_impact = v3_pool.get_price_impact(base_token, amount)
            v4_impact = v4_pool.get_depth_impact(base_token, amount)
            
            # If V4 depth impact is too high, consider splitting
            if v4_impact > Decimal('0.1'):  # 10% depth impact threshold
                split_amounts = self._calculate_split_amounts(amount, v3_pool, v4_pool)
                return await self._create_split_migration_tx(
                    v3_pool,
                    v4_pool,
                    split_amounts,
                    slippage_tolerance
                )
            else:
                return await self._create_single_migration_tx(
                    v3_pool,
                    v4_pool,
                    amount,
                    slippage_tolerance
                )
                
        except Exception as e:
            logger.error(f"Error planning execution: {str(e)}")
            return None
            
    def _calculate_split_amounts(self,
                               total_amount: Decimal,
                               v3_pool: RaydiumPair,
                               v4_pool: RaydiumPair) -> List[Decimal]:
        """Calculate optimal amounts for split execution"""
        # Start with simple split strategy
        num_splits = 2
        base_amount = total_amount / num_splits
        
        # Adjust splits based on liquidity
        v4_liquidity = v4_pool.get_balance(v4_pool.tokens[0])
        optimal_size = v4_liquidity * Decimal('0.05')  # 5% of liquidity
        
        if base_amount > optimal_size:
            num_splits = min(5, int(total_amount / optimal_size) + 1)
            base_amount = total_amount / num_splits
            
        return [base_amount for _ in range(num_splits)]
        
    async def _create_split_migration_tx(self,
                                       v3_pool: RaydiumPair,
                                       v4_pool: RaydiumPair,
                                       amounts: List[Decimal],
                                       slippage_tolerance: Decimal) -> Optional[Transaction]:
        """Create transaction for split execution"""
        try:
            migrations = []
            for amount in amounts:
                migration_ix = await self._create_migration_instruction(
                    v3_pool,
                    v4_pool,
                    amount,
                    slippage_tolerance
                )
                migrations.append(migration_ix)
                
            tx = Transaction()
            for migration in migrations:
                tx.add(migration)
                
            return tx
            
        except Exception as e:
            logger.error(f"Error creating split migration tx: {str(e)}")
            return None
            
    async def _create_single_migration_tx(self,
                                        v3_pool: RaydiumPair,
                                        v4_pool: RaydiumPair,
                                        amount: Decimal,
                                        slippage_tolerance: Decimal) -> Optional[Transaction]:
        """Create transaction for single execution"""
        try:
            migration_ix = await self._create_migration_instruction(
                v3_pool,
                v4_pool,
                amount,
                slippage_tolerance
            )
            
            tx = Transaction()
            tx.add(migration_ix)
            return tx
            
        except Exception as e:
            logger.error(f"Error creating single migration tx: {str(e)}")
            return None
            
    async def _execute_transaction(self,
                                 transaction: Transaction,
                                 priority_fee: int) -> MigrationResult:
        """Execute the migration transaction"""
        import time
        start_time = time.time()
        
        try:
            # Add priority fee
            transaction.recent_blockhash = await self.api_client.get_recent_blockhash()
            transaction.set_compute_budget_ix(priority_fee)
            
            # Send and confirm transaction
            signature = await self.api_client.send_and_confirm_transaction(
                transaction,
                commitment="confirmed"
            )
            
            # Get transaction result
            tx_result = await self.api_client.get_transaction(signature)
            
            if not tx_result or not tx_result.meta or tx_result.meta.err:
                raise Exception(f"Transaction failed: {tx_result.meta.err if tx_result.meta else 'Unknown error'}")
                
            # Parse execution results
            amount_in, amount_out = self._parse_transfer_amounts(tx_result)
            fees_paid = Decimal(str(tx_result.meta.fee)) / Decimal(1e9)
            
            return MigrationResult(
                success=True,
                tx_signature=str(signature),
                execution_time=time.time() - start_time,
                amount_in=amount_in,
                amount_out=amount_out,
                effective_price=amount_out / amount_in if amount_in > 0 else Decimal(0),
                fees_paid=fees_paid
            )
            
        except Exception as e:
            logger.error(f"Transaction execution failed: {str(e)}")
            return MigrationResult(
                success=False,
                tx_signature=None,
                execution_time=time.time() - start_time,
                amount_in=Decimal(0),
                amount_out=Decimal(0),
                effective_price=Decimal(0),
                fees_paid=Decimal(0),
                error_message=str(e)
            )
            
    def _parse_transfer_amounts(self, tx_result) -> Tuple[Decimal, Decimal]:
        """Parse actual transfer amounts from transaction result"""
        try:
            amount_in = Decimal(0)
            amount_out = Decimal(0)
            
            for ix_result in tx_result.meta.inner_instructions:
                for inner_ix in ix_result.instructions:
                    if "Transfer" in inner_ix.program:
                        # Parse transfer data
                        # This would need proper implementation based on
                        # actual Raydium instruction format
                        pass
                        
            return amount_in, amount_out
            
        except Exception as e:
            logger.error(f"Error parsing transfer amounts: {str(e)}")
            return Decimal(0), Decimal(0)