from typing import Dict, List, Optional
import logging
import time
from config import Config
from api_client import PoolData

logger = logging.getLogger("RiskAnalyzer")

class RiskAnalyzer:
    """
    Analyze pools for risk and determine suitability for arbitrage
    Updated to be less restrictive for cross-DEX arbitrage opportunities
    """
    
    def __init__(self, config: Config):
        self.config = config
        # Risk tolerance settings - set less restrictive thresholds
        self.min_liquidity = 10000  # Reduced from 70k to 10k
        self.max_insider_holding = 30.0  # Increased from 15% to 30%
        self.imbalance_threshold = 0.8  # Reduced imbalance requirement (0.8 means allow 80/20 ratios)
        
        # Keep track of risky pools
        self.high_risk_pools = set()
        
        logger.info(f"Risk analyzer initialized with less restrictive settings")
        logger.info(f"Min liquidity: ${self.min_liquidity}, Max insider: {self.max_insider_holding}%")
    
    def analyze_pool_risk(self, pool: PoolData) -> int:
        """
        Analyze a pool's risk profile and score it
        Lower score = lower risk
        Return risk score (0-100)
        """
        try:
            # Base risk score starts at 0
            risk_score = 0
            
            # === LIQUIDITY RISK ===
            # Calculate total value locked in USD
            # For simplicity, use quoteAmount as TVL for stablecoin pairs
            # In real production, we'd calculate this properly with token prices
            tvl = pool.quote_amount
            
            # Penalize low liquidity pools
            if tvl < self.min_liquidity:
                # Logarithmic penalty based on how far below threshold
                liquidity_ratio = tvl / self.min_liquidity
                risk_score += max(0, int(50 * (1 - liquidity_ratio)))
                logger.debug(f"Pool {pool.id} - Low liquidity risk: +{int(50 * (1 - liquidity_ratio))}")
            
            # === POOL BALANCE RISK ===
            # Check token balance ratio
            # For example: if one side is highly imbalanced, it might be a red flag
            try:
                # Normalize by price to get a rough value ratio
                # This is approximate, ideally we'd use actual token prices
                # Simple balance measure: lower of A/B or B/A ratios
                base_value = pool.base_amount 
                quote_value = pool.quote_amount
                
                if base_value > 0 and quote_value > 0:
                    balance_ratio = min(base_value / quote_value, quote_value / base_value)
                    
                    # Penalize imbalanced pools
                    if balance_ratio < self.imbalance_threshold:
                        imbalance_score = int(25 * (1 - balance_ratio / self.imbalance_threshold))
                        risk_score += imbalance_score
                        logger.debug(f"Pool {pool.id} - Imbalance risk: +{imbalance_score}")
            except Exception as e:
                # If we can't calculate balance, add a small penalty
                risk_score += 5
                logger.warning(f"Pool {pool.id} - Failed to calculate balance ratio: {str(e)}")
            
            # === ACTIVITY STATUS ===
            # Inactive pools are risky (but we'll accept them if they have opportunities)
            if pool.status.lower() != "online":
                risk_score += 10
                logger.debug(f"Pool {pool.id} - Inactive status risk: +10")
            
            # === AGE / HISTORY RISK ===
            # If pool is very new, it might be higher risk
            # (Less of a concern for arbitrage than for investment)
            current_time = int(time.time())
            pool_age_days = (current_time - pool.creation_time) / (60 * 60 * 24)
            
            if pool_age_days < 1:
                risk_score += 10
                logger.debug(f"Pool {pool.id} - New pool risk: +10")
            elif pool_age_days < 7:
                risk_score += 5
                logger.debug(f"Pool {pool.id} - Recent pool risk: +5")
            
            # Cross-DEX pool type may be lower risk for arbitrage specifically
            # We could add logic to lower risk for certain DEX pairs known to be good for arbitrage
            
            # Track high-risk pools
            if risk_score > 75:
                self.high_risk_pools.add(pool.id)
                logger.warning(f"Pool {pool.id} - High risk score: {risk_score}")
            
            return risk_score
            
        except Exception as e:
            logger.error(f"Error analyzing pool risk for {pool.id}: {str(e)}")
            # Return max risk on error
            return 100

    def check_arbitrage_risk(self, source_pool_id: str, target_pool_id: str) -> int:
        """
        Analyze risk for an arbitrage opportunity between two pools
        Lower score = lower risk
        Return risk score (0-100)
        """
        # If either pool is high risk, the arbitrage is high risk
        if source_pool_id in self.high_risk_pools or target_pool_id in self.high_risk_pools:
            return 90
            
        # For cross-DEX arbitrage, we could have special logic here to 
        # assess risk based on known DEX pairs
        
        # Default medium-low risk for arbitrage between tracked pools
        return 40

    def is_pool_eligible(self, pool: PoolData) -> bool:
        """
        Quickly check if a pool meets basic eligibility for arbitrage
        More permissive than before to allow more opportunities
        """
        # Always accept pools with significant liquidity
        if pool.quote_amount >= self.min_liquidity:
            return True
            
        # Accept pools with SOL or USDC (high-quality token pools)
        sol_address = "So11111111111111111111111111111111111111112"
        usdc_address = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        
        has_quality_token = (
            pool.base_token.address == sol_address or 
            pool.quote_token.address == sol_address or
            pool.base_token.address == usdc_address or 
            pool.quote_token.address == usdc_address
        )
        
        if has_quality_token:
            # Accept any pool with SOL or USDC as long as it has some liquidity
            min_threshold = self.min_liquidity * 0.25  # Lower threshold for quality tokens
            return pool.quote_amount >= min_threshold
            
        # For other tokens, use the standard threshold
        return pool.quote_amount >= self.min_liquidity
