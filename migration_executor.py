from typing import List, Optional, Tuple
from dataclasses import dataclass
from decimal import Decimal
import logging
import asyncio
import time
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
        
    async def execute_migration(self,
                              migration_info: MigrationContract,
                              amount: Decimal,
                              slippage_tolerance: Decimal = Decimal('0.02')) -> MigrationResult:
        """Execute a migration trade with retry logic and dynamic fee adjustment"""
        import time
        start_time = time.time()
        
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
                        
            return MigrationResult(
                success=False,
                tx_signature=None,
                execution_time=time.time() - start_time,
                amount_in=amount,
                amount_out=Decimal(0),
                effective_price=Decimal(0),
                fees_paid=Decimal(0),
                error_message=f"Failed after {self.max_retries} attempts"
            )
            
        except Exception as e:
            logger.error(f"Migration execution failed: {str(e)}")
            return MigrationResult(
                success=False,
                tx_signature=None,
                execution_time=time.time() - start_time,
                amount_in=amount,
                amount_out=Decimal(0),
                effective_price=Decimal(0),
                fees_paid=Decimal(0),
                error_message=str(e)
            )
            
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