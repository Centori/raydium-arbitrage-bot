from typing import Dict, List, Optional
import numpy as np
from dataclasses import dataclass
from decimal import Decimal
import logging
from config import Config
from risk_analyzer import RiskAnalyzer
from api_client import PoolData
from raydium_pair import RaydiumPair

logger = logging.getLogger(__name__)

@dataclass
class PoolAnalysis:
    pool_id: str
    liquidity_score: float  # 0-100
    volume_score: float     # 0-100
    stability_score: float  # 0-100
    risk_score: float      # 0-100
    overall_score: float   # Weighted average

class PoolAnalyzer:
    def __init__(self, config: Config, risk_analyzer: RiskAnalyzer):
        self.config = config
        self.risk_analyzer = risk_analyzer
        self.min_liquidity = 70000  # Minimum USD liquidity
        self.min_daily_volume = 50000  # Minimum daily volume in USD
        
        # Scoring weights
        self.weights = {
            'liquidity': 0.3,
            'volume': 0.2,
            'stability': 0.2,
            'risk': 0.3
        }
        
        # Whitelisted token addresses
        self.whitelist = set([
            "So11111111111111111111111111111111111111112",  # SOL
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
            # Add more trusted tokens
        ])

    def analyze_pool(self, pool: PoolData, volume_data: Dict) -> Optional[PoolAnalysis]:
        """Analyze a single pool and return detailed metrics"""
        try:
            # Skip if tokens aren't whitelisted
            if not (pool.base_token.address in self.whitelist or 
                   pool.quote_token.address in self.whitelist):
                return None

            # Create RaydiumPair instance for balance calculations
            pair = RaydiumPair(
                market_address=pool.id,
                tokens=[pool.base_token.address, pool.quote_token.address]
            )
            # Set current reserves
            pair.set_reserves(
                Decimal(pool.base_amount),
                Decimal(pool.quote_amount)
            )

            # Calculate liquidity score
            total_liquidity_usd = float(pool.quote_amount) * 2  # Simplified USD estimation
            liquidity_score = min(100, (total_liquidity_usd / self.min_liquidity) * 100)

            # Calculate volume score
            daily_volume = volume_data.get(pool.id, 0)
            volume_score = min(100, (daily_volume / self.min_daily_volume) * 100)

            # Get risk score from risk analyzer
            risk_score = 100 - self.risk_analyzer.analyze_pool_risk(pool)

            # Calculate stability score based on price impact
            stability_score = self._calculate_stability_score(pool, pair)

            # Calculate overall score
            overall_score = (
                liquidity_score * self.weights['liquidity'] +
                volume_score * self.weights['volume'] +
                stability_score * self.weights['stability'] +
                risk_score * self.weights['risk']
            )

            return PoolAnalysis(
                pool_id=pool.id,
                liquidity_score=liquidity_score,
                volume_score=volume_score,
                stability_score=stability_score,
                risk_score=risk_score,
                overall_score=overall_score
            )
        except Exception as e:
            print(f"Error analyzing pool {pool.id}: {str(e)}")
            return None

    def _calculate_stability_score(self, pool: PoolData, pair: RaydiumPair) -> float:
        """Calculate pool stability score based on price impact and liquidity depth"""
        try:
            # Test price impact with a moderate trade size (1% of pool liquidity)
            test_amount = Decimal(pool.base_amount) / Decimal('100')
            price_impact = pair.get_price_impact(pool.base_token.address, test_amount)
            
            # Convert price impact to stability score (lower impact = higher stability)
            # Price impact of 0% = 100 score, 5% impact = 0 score
            max_acceptable_impact = Decimal('0.05')  # 5%
            if price_impact >= max_acceptable_impact:
                return 0
            
            stability_score = float((max_acceptable_impact - price_impact) / max_acceptable_impact * 100)
            return stability_score
            
        except Exception as e:
            logger.error(f"Error calculating stability score: {str(e)}")
            return 0

    def filter_pools(self, pools: List[PoolData], 
                    volume_data: Dict) -> List[PoolData]:
        """Filter and sort pools based on analysis"""
        analyzed_pools = []
        
        for pool in pools:
            analysis = self.analyze_pool(pool, volume_data)
            if analysis and analysis.overall_score >= 70:  # Only pools with good scores
                analyzed_pools.append((pool, analysis))
        
        # Sort by overall score
        analyzed_pools.sort(key=lambda x: x[1].overall_score, reverse=True)
        
        return [pool for pool, _ in analyzed_pools]

    def get_swap_quote(self, pool: PoolData, token_in: str, amount_in: Decimal) -> Optional[Dict]:
        """Get a swap quote for a given pool and input amount"""
        try:
            # Create RaydiumPair instance
            pair = RaydiumPair(
                market_address=pool.id,
                tokens=[pool.base_token.address, pool.quote_token.address]
            )
            
            # Set current reserves
            pair.set_reserves(
                Decimal(pool.base_amount),
                Decimal(pool.quote_amount)
            )
            
            # Determine output token
            token_out = pool.quote_token.address if token_in == pool.base_token.address else pool.base_token.address
            
            # Calculate output amount
            amount_out = pair.get_tokens_out(token_in, token_out, amount_in)
            
            # Calculate price impact
            price_impact = pair.get_price_impact(token_in, amount_in)
            
            return {
                "pool_id": pool.id,
                "token_in": token_in,
                "token_out": token_out,
                "amount_in": str(amount_in),
                "amount_out": str(amount_out),
                "price_impact": float(price_impact),
                "fee": float(pair.TRADE_FEE_NUMERATOR) / float(pair.TRADE_FEE_DENOMINATOR)
            }
            
        except Exception as e:
            logger.error(f"Error getting swap quote: {str(e)}")
            return None

    def get_pool_recommendation(self, pools: List[PoolData], 
                              volume_data: Dict) -> List[Dict]:
        """Get detailed recommendations for pools"""
        recommendations = []
        
        for pool in pools:
            analysis = self.analyze_pool(pool, volume_data)
            if analysis:
                recommendations.append({
                    'pool_id': pool.id,
                    'base_token': pool.base_token.symbol,
                    'quote_token': pool.quote_token.symbol,
                    'overall_score': analysis.overall_score,
                    'liquidity_score': analysis.liquidity_score,
                    'volume_score': analysis.volume_score,
                    'stability_score': analysis.stability_score,
                    'risk_score': analysis.risk_score,
                    'recommendation': 'High Priority' if analysis.overall_score >= 80
                                    else 'Medium Priority' if analysis.overall_score >= 70
                                    else 'Low Priority'
                })
        
        return sorted(recommendations, 
                     key=lambda x: x['overall_score'], 
                     reverse=True)