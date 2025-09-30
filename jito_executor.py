import asyncio
import json
import time
import random
import logging
import base64
from typing import List, Optional, Dict, Any, Tuple
import requests
from solders.message import VersionedMessage
from solders.transaction import VersionedTransaction

from api_client import BlockchainAPIClient, ArbitrageOpportunity
from wallet import WalletManager
from config import JITO_CONFIG

logger = logging.getLogger(__name__)

class JitoExecutor:
    """
    Executor for Jito bundle submission
    """
    
    def __init__(self, config, wallet_manager: WalletManager, api_client: BlockchainAPIClient = None):
        self.wallet_manager = wallet_manager
        self.config = config
        self.api_client = api_client if api_client else BlockchainAPIClient(config)
        
        # Jito-specific parameters
        self.min_tip_threshold = JITO_CONFIG.get("min_tip_threshold", 0.005)
        self.max_bundle_size = JITO_CONFIG.get("max_bundle_size", 3)
        self.execution_timeout = JITO_CONFIG.get("execution_timeout", 2)
        self.retry_count = JITO_CONFIG.get("retry_count", 3)
        
        # Enhanced parameters from config
        self.max_tip_percentage = JITO_CONFIG.get("max_tip_percentage", 70)
        self.dynamic_tip_scaling = JITO_CONFIG.get("dynamic_tip_scaling", True)
        self.tip_multiplier_base = JITO_CONFIG.get("tip_multiplier_base", 2.0)
        self.max_price_impact = JITO_CONFIG.get("max_price_impact", 0.0052)
        self.dynamic_compute_unit_limit = JITO_CONFIG.get("dynamic_compute_unit_limit", True)
        self.prioritization_fee_mode = JITO_CONFIG.get("prioritization_fee_mode", "auto")
        
        # Socket connection config
        self.max_sockets = JITO_CONFIG.get("max_sockets", 25)
        self.socket_timeout = JITO_CONFIG.get("socket_timeout", 19000)
        self.keepalive_enabled = JITO_CONFIG.get("keepalive_enabled", True)
        
        # Historical tip data for adaptive tipping
        self.recent_tips = []
        self.max_tip_history = 50
        self.tip_success_threshold = 0.8  # 80% success rate
        
        # Track recent success/failures for adaptive strategy
        self.recent_bundle_results = []
        self.max_result_history = 100
        
        # Initialize state
        self.initialized = False
        
    async def initialize(self) -> bool:
        """Initialize the executor"""
        try:
            # Set up connections
            result = await self.api_client.init_jito_connection(
                max_sockets=self.max_sockets,
                socket_timeout=self.socket_timeout,
                keepalive=self.keepalive_enabled
            )
            
            self.initialized = result
            return result
            
        except Exception as e:
            logger.error(f"Failed to initialize Jito executor: {e}")
            return False
    
    def calculate_dynamic_tip(self, expected_profit: float) -> float:
        """Calculate a dynamic tip based on the expected profit and market conditions"""
        if self.dynamic_tip_scaling:
            # Calculate maximum allowable tip based on profit percentage
            max_tip = expected_profit * (self.max_tip_percentage / 100)
            
            # If the minimum tip threshold exceeds what's profitable, just return minimum
            if self.min_tip_threshold > max_tip:
                logger.info(f"Calculated dynamic tip: {self.min_tip_threshold:.6f} SOL for expected profit of {expected_profit:.6f} SOL (minimum threshold applied - trade unprofitable)")
                return self.min_tip_threshold
            
            # For profitable trades, calculate dynamic tip
            # Get base tip amount (default to 40% of profit)
            base_tip = expected_profit * 0.4
            
            # Calculate competitive tip based on recent history
            competitive_tip = self._get_competitive_tip_estimate()
            
            # Apply our multiplier for better chances
            competitive_tip *= self.tip_multiplier_base
            
            # Take the higher of our calculation or base percentage
            tip = max(base_tip, competitive_tip)
            
            # Ensure we don't exceed maximum percentage of profit
            tip = min(tip, max_tip)
            
            # Ensure we meet minimum threshold
            tip = max(tip, self.min_tip_threshold)
            
            # For profitable trades, add slight random variation
            tip *= random.uniform(1.0, 1.05)
            
            # Final enforcement of constraints
            tip = max(tip, self.min_tip_threshold)
            tip = min(tip, max_tip * 1.05)  # Allow slight variance for randomization
            
            logger.info(f"Calculated dynamic tip: {tip:.6f} SOL for expected profit of {expected_profit:.6f} SOL")
            return tip
        else:
            # Static tip logic - also ensure minimum threshold
            static_tip = expected_profit * 0.4  # Default to 40% of profit
            return max(self.min_tip_threshold, static_tip)
    
    def _get_competitive_tip_estimate(self) -> float:
        """Estimate competitive tip amount based on recent history"""
        if not self.recent_tips:
            return self.min_tip_threshold
        
        # Sort tips and get median (more stable than average)
        sorted_tips = sorted(self.recent_tips)
        median_tip = sorted_tips[len(sorted_tips) // 2]
        
        # We want to be above the median
        return max(median_tip, self.min_tip_threshold)
    
    def update_tip_estimates(self, tip_amount: float) -> None:
        """Update the history of tip amounts"""
        self.recent_tips.append(tip_amount)
        
        # Keep history limited to max size
        if len(self.recent_tips) > self.max_tip_history:
            self.recent_tips = self.recent_tips[-self.max_tip_history:]
    
    async def submit_arbitrage_opportunity(self, opportunity: ArbitrageOpportunity) -> bool:
        """Submit an arbitrage opportunity to be executed"""
        if not self.initialized:
            logger.warning("Jito executor not initialized, attempting to initialize now")
            if not await self.initialize():
                logger.error("Failed to initialize Jito executor")
                return False
        
        try:
            # Calculate profit in SOL terms
            sol_profit = opportunity.expected_profit / opportunity.sol_price if opportunity.sol_price else 0
            logger.info(f"Submitting arbitrage opportunity with expected profit: ${opportunity.expected_profit:.4f} (~{sol_profit:.6f} SOL)")
            
            # Check if expected price impact exceeds maximum allowed
            if opportunity.estimated_price_impact > self.max_price_impact:
                # Adjust trade size to bring price impact under limit
                adjustment_ratio = self.max_price_impact / opportunity.estimated_price_impact
                logger.warning(f"Price impact {opportunity.estimated_price_impact:.4%} exceeds maximum {self.max_price_impact:.4%}. Adjusting trade size to {adjustment_ratio:.2%} of original.")
                opportunity.amount = opportunity.amount * adjustment_ratio
                opportunity.estimated_price_impact = self.max_price_impact  # Set to maximum allowed
                # Recalculate expected profit based on new size
                opportunity.expected_profit = opportunity.expected_profit * adjustment_ratio
                sol_profit = sol_profit * adjustment_ratio
                logger.info(f"Adjusted trade size. New expected profit: ${opportunity.expected_profit:.4f} (~{sol_profit:.6f} SOL)")
            
            # Calculate appropriate tip based on profit
            tip_amount = self.calculate_dynamic_tip(sol_profit)
            opportunity.tip_lamports = int(tip_amount * 1_000_000_000)  # Convert SOL to lamports
            
            # Get the next block we can submit to
            try:
                next_block = self.api_client.get_next_block()
                if not next_block:
                    logger.error("Failed to get next block from Jito")
                    return False
                    
                opportunity.target_block = next_block
                
            except Exception as e:
                logger.error(f"Error getting next block: {e}")
                return False
            
            # Build transaction(s)
            tx_result = await self._build_arbitrage_transaction(opportunity)
            if not tx_result:
                logger.error("Failed to build arbitrage transaction")
                return False
                
            transactions, tx_data = tx_result
            
            # Check if we should simulate before sending
            if JITO_CONFIG.get("simulate_before_send", True):
                simulation_result = await self._simulate_transaction_bundle(transactions)
                if not simulation_result.get("success", False):
                    logger.error(f"Bundle simulation failed: {simulation_result.get('error', 'Unknown error')}")
                    return False
            
            # Submit the transaction bundle
            bundle_id = await self.submit_transactions(transactions, opportunity.expected_profit)
            
            if bundle_id:
                # Store result for monitoring
                opportunity.bundle_id = bundle_id
                opportunity.submission_time = time.time()
                
                # Record the result
                self._record_bundle_result(True, sol_profit, tip_amount)
                
                logger.info(f"Successfully submitted arbitrage opportunity with bundle ID {bundle_id}")
                return True
            else:
                # Record the failure
                self._record_bundle_result(False, sol_profit, tip_amount)
                
                logger.error("Failed to submit arbitrage opportunity bundle")
                return False
                
        except Exception as e:
            logger.error(f"Error submitting arbitrage opportunity: {e}")
            return False
    
    def _record_bundle_result(self, success: bool, profit: float, tip: float) -> None:
        """Record bundle submission result for adaptive strategy"""
        self.recent_bundle_results.append({
            "timestamp": time.time(),
            "success": success,
            "profit": profit,
            "tip": tip,
            "tip_ratio": tip / profit if profit > 0 else 0
        })
        
        # Keep history limited
        if len(self.recent_bundle_results) > self.max_result_history:
            self.recent_bundle_results = self.recent_bundle_results[-self.max_result_history:]
    
    async def _build_arbitrage_transaction(self, opportunity) -> Optional[Tuple[List[VersionedTransaction], Dict[str, Any]]]:
        """Build the transaction(s) for executing the arbitrage opportunity"""
        try:
            # Build the appropriate transaction based on the opportunity type
            tx_data = {}
            
            if opportunity.type == "triangle":
                # For triangular arbitrage, generate swap sequence
                tx_data = await self.api_client.build_triangle_arbitrage_tx(
                    opportunity.tokens,
                    opportunity.pools,
                    opportunity.amount,
                    slippage_bps=self.config.SLIPPAGE_BPS,
                    priority_fee="auto" if self.prioritization_fee_mode == "auto" else None,
                    dynamic_compute_limit=self.dynamic_compute_unit_limit
                )
            elif opportunity.type == "cross_dex":
                # For cross-DEX arbitrage
                tx_data = await self.api_client.build_cross_dex_arbitrage_tx(
                    opportunity.source_dex,
                    opportunity.target_dex,
                    opportunity.token_pair,
                    opportunity.amount,
                    slippage_bps=self.config.SLIPPAGE_BPS,
                    priority_fee="auto" if self.prioritization_fee_mode == "auto" else None,
                    dynamic_compute_limit=self.dynamic_compute_unit_limit
                )
            elif opportunity.type == "flash_loan":
                # For flash loan arbitrage
                tx_data = await self.api_client.build_flash_loan_arbitrage_tx(
                    opportunity.tokens,
                    opportunity.pools,
                    opportunity.amount,
                    opportunity.flash_loan_market,
                    slippage_bps=self.config.SLIPPAGE_BPS,
                    priority_fee="auto" if self.prioritization_fee_mode == "auto" else None,
                    dynamic_compute_limit=self.dynamic_compute_unit_limit
                )
            else:
                logger.error(f"Unsupported opportunity type: {opportunity.type}")
                return None
                
            if not tx_data or "transactions" not in tx_data:
                logger.error("Failed to generate transaction data")
                return None
                
            # Convert transaction data to VersionedTransaction objects
            transactions = []
            for tx_base64 in tx_data["transactions"]:
                tx_bytes = base64.b64decode(tx_base64)
                tx = VersionedTransaction.deserialize(tx_bytes)
                transactions.append(tx)
                
            return transactions, tx_data
                
        except Exception as e:
            logger.error(f"Error building arbitrage transaction: {e}")
            return None
    
    async def _simulate_transaction_bundle(self, transactions: List[VersionedTransaction]) -> Dict[str, Any]:
        """Simulate a bundle of transactions to ensure it will execute correctly"""
        try:
            # Prepare simulation request
            tx_base64_list = []
            for tx in transactions:
                tx_base64_list.append(base64.b64encode(tx.serialize()).decode('ascii'))
                
            # Call the API client to simulate
            simulation_result = await self.api_client.simulate_transactions(tx_base64_list)
            
            return simulation_result
                
        except Exception as e:
            logger.error(f"Error simulating transaction bundle: {e}")
            return {"success": False, "error": str(e)}
            
    async def submit_transactions(self, transactions: List[VersionedTransaction], expected_profit: float = 0) -> Optional[str]:
        """Submit a bundle of transactions through Jito"""
        try:
            # Calculate appropriate tip
            tip_amount = self.calculate_dynamic_tip(expected_profit)
            
            # Submit the bundle
            bundle_id = await self.api_client.submit_bundle(
                transactions,
                tip_lamports=int(tip_amount * 1_000_000_000)
            )
            
            if bundle_id:
                logger.info(f"Successfully submitted bundle with ID: {bundle_id} and tip of {tip_amount:.6f} SOL")
                # Update tip estimates for future calculations
                self.update_tip_estimates(tip_amount)
                return bundle_id
            else:
                logger.error("Failed to submit bundle")
                return None
                
        except Exception as e:
            logger.error(f"Error submitting transactions: {e}")
            return None
    
    async def get_bundle_status(self, bundle_id: str) -> Dict[str, Any]:
        """Get the status of a submitted bundle"""
        try:
            status = await self.api_client.get_bundle_status(bundle_id)
            return status
            
        except Exception as e:
            logger.error(f"Error getting bundle status: {e}")
            return {"status": "error", "error": str(e)}
    
    async def check_expected_profit(self, opportunity) -> float:
        """Re-check the expected profit for an opportunity considering current market conditions"""
        try:
            # Re-calculate the profit expectation based on current prices
            updated_profit = await self.api_client.calculate_arbitrage_profit(
                opportunity.type,
                opportunity.tokens if hasattr(opportunity, 'tokens') else [],
                opportunity.pools if hasattr(opportunity, 'pools') else [],
                opportunity.amount,
            )
            
            return updated_profit
            
        except Exception as e:
            logger.error(f"Error checking expected profit: {e}")
            return 0.0
            
    def get_optimal_backrun_config(self) -> Dict[str, Any]:
        """Get optimal configuration for backrunning based on current market conditions"""
        return {
            "slippage_bps": self.config.SLIPPAGE_BPS,  # 1.00% slippage
            "max_price_impact": self.max_price_impact,  # 0.52% max price impact
            "dynamic_compute_limit": self.dynamic_compute_unit_limit,  # True
            "priority_fee": self.prioritization_fee_mode,  # "auto"
            "current_sol_balance": 0.5,  # Current SOL balance
            "max_trade_size": 0.5,  # Maximum trade size based on balance
        }
