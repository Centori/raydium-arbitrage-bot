#!/usr/bin/env python3
"""
Universal Arbitrage Hunter
Leverages existing enhanced liquidity monitoring to find arbitrage across ALL tokens and DEXes
"""

import asyncio
import time
import json
from typing import Dict, List, Set, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import aiohttp
from datetime import datetime, timedelta
import numpy as np

from config import Config, DEX_CONFIG, MONITORED_PAIRS
from monitor_arbitrage_opportunities import ArbitrageMonitor, ArbitrageOpportunity, DEXPoolData
from pool_analyzer import PoolAnalyzer
from risk_analyzer import RiskAnalyzer
from api_client import BlockchainAPIClient

@dataclass
class TokenMetadata:
    """Enhanced token information with ML scoring"""
    address: str
    symbol: str
    name: str
    decimals: int
    volume_24h: float = 0
    liquidity_usd: float = 0
    price_change_24h: float = 0
    holder_count: int = 0
    creation_time: float = 0
    risk_score: float = 50  # 0-100, lower is better
    opportunity_score: float = 0  # ML-derived score
    last_updated: float = field(default_factory=time.time)

@dataclass 
class UniversalPool:
    """Pool data with cross-DEX compatibility"""
    dex: str
    pool_address: str
    token_a: TokenMetadata
    token_b: TokenMetadata
    reserves: Tuple[float, float]
    liquidity_usd: float
    volume_24h: float
    fee_rate: float
    last_trade_time: float
    price_impact_1_sol: float = 0  # Price impact for 1 SOL trade
    
class UniversalArbitrageHunter(ArbitrageMonitor):
    """
    Enhanced arbitrage hunter that discovers opportunities across ALL tokens and DEXes
    Builds on existing monitoring infrastructure with ML-like pattern recognition
    """
    
    def __init__(self, config: Config):
        super().__init__(config)
        
        # Enhanced components
        self.pool_analyzer = PoolAnalyzer(config, self.risk_analyzer)
        
        # Universal token/pool tracking
        self.all_tokens: Dict[str, TokenMetadata] = {}
        self.universal_pools: Dict[str, List[UniversalPool]] = defaultdict(list)
        self.token_pair_map: Dict[Tuple[str, str], List[UniversalPool]] = defaultdict(list)
        
        # ML-like pattern tracking
        self.opportunity_patterns = defaultdict(list)  # Track successful patterns
        self.token_scores = defaultdict(float)  # ML-derived token scores
        
        # API clients for comprehensive data
        self.dexscreener_url = "https://api.dexscreener.com/latest/dex"
        self.birdeye_url = "https://public-api.birdeye.so/public"
        
        # Configuration for universal monitoring
        self.min_liquidity_usd = 5000  # Minimum liquidity to consider
        self.min_volume_24h = 1000     # Minimum 24h volume
        self.max_pools_per_update = 1000  # Process in batches
        self.new_token_boost = 2.0     # Score multiplier for new tokens
        
    async def start_universal_monitoring(self):
        """Enhanced monitoring that discovers ALL opportunities"""
        self.is_running = True
        print("🌍 Starting Universal Arbitrage Hunter...")
        print(f"Monitoring {len(DEX_CONFIG)} DEXes for opportunities across ALL tokens")
        
        # Start concurrent monitoring tasks
        tasks = [
            self._universal_discovery_loop(),      # Discover all pools/tokens
            self._opportunity_mining_loop(),       # Mine for arbitrage
            self._ml_pattern_learning_loop(),      # Learn from successful patterns
            self._new_token_detection_loop(),      # Catch new launches
            self._display_loop(),                  # Display results
            self._cleanup_loop()                   # Cleanup old data
        ]
        
        try:
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            print("\n🛑 Stopping Universal Hunter...")
            self.is_running = False
    
    async def _universal_discovery_loop(self):
        """Discover ALL active pools across ALL DEXes"""
        while self.is_running:
            try:
                print(f"\n🔍 Discovering pools... [{datetime.now().strftime('%H:%M:%S')}]")
                
                # Method 1: Use DexScreener API for broad coverage
                await self._discover_via_dexscreener()
                
                # Method 2: Query each DEX directly
                await self._discover_via_direct_query()
                
                # Method 3: Monitor new pool events
                await self._discover_via_events()
                
                # Update token metadata and scores
                await self._update_token_metadata()
                
                print(f"✅ Discovered {len(self.all_tokens)} tokens across {sum(len(pools) for pools in self.universal_pools.values())} pools")
                
                await asyncio.sleep(30)  # Full scan every 30 seconds
                
            except Exception as e:
                print(f"❌ Discovery error: {str(e)}")
                await asyncio.sleep(10)
    
    async def _discover_via_dexscreener(self):
        """Use DexScreener API to discover pools"""
        try:
            # Get trending pairs
            async with aiohttp.ClientSession() as session:
                # Fetch multiple categories
                endpoints = [
                    f"{self.dexscreener_url}/trending",
                    f"{self.dexscreener_url}/gainers",
                    f"{self.dexscreener_url}/latest"
                ]
                
                for endpoint in endpoints:
                    async with session.get(endpoint) as response:
                        if response.status == 200:
                            data = await response.json()
                            await self._process_dexscreener_data(data)
                            
        except Exception as e:
            print(f"DexScreener error: {str(e)}")
    
    async def _process_dexscreener_data(self, data: dict):
        """Process DexScreener response data"""
        pairs = data.get("pairs", [])
        
        for pair in pairs:
            # Filter by chain (Solana)
            if pair.get("chainId") != "solana":
                continue
                
            # Extract token metadata
            base_token = TokenMetadata(
                address=pair["baseToken"]["address"],
                symbol=pair["baseToken"]["symbol"],
                name=pair["baseToken"]["name"],
                decimals=9,  # Default for Solana
                volume_24h=float(pair.get("volume", {}).get("h24", 0)),
                liquidity_usd=float(pair.get("liquidity", {}).get("usd", 0)),
                price_change_24h=float(pair.get("priceChange", {}).get("h24", 0))
            )
            
            quote_token = TokenMetadata(
                address=pair["quoteToken"]["address"],
                symbol=pair["quoteToken"]["symbol"],
                name=pair["quoteToken"]["name"],
                decimals=9
            )
            
            # Store tokens
            self.all_tokens[base_token.address] = base_token
            self.all_tokens[quote_token.address] = quote_token
            
            # Create pool
            pool = UniversalPool(
                dex=pair.get("dexId", "unknown"),
                pool_address=pair["pairAddress"],
                token_a=base_token,
                token_b=quote_token,
                reserves=(0, 0),  # Would need to fetch on-chain
                liquidity_usd=base_token.liquidity_usd,
                volume_24h=base_token.volume_24h,
                fee_rate=0.003,  # Default 0.3%
                last_trade_time=time.time()
            )
            
            # Store pool by DEX and token pair
            self.universal_pools[pool.dex].append(pool)
            pair_key = tuple(sorted([base_token.address, quote_token.address]))
            self.token_pair_map[pair_key].append(pool)
    
    async def _discover_via_direct_query(self):
        """Query each DEX program directly for pools"""
        # This would implement direct on-chain queries similar to
        # the Solana DEX pair finder logic, discovering pools via PDAs
        pass
    
    async def _discover_via_events(self):
        """Monitor pool creation events"""
        # Subscribe to new pool events from each DEX
        pass
    
    async mysterious_opportunity_mining_loop(self):
        """Mine for arbitrage opportunities across discovered pools"""
        while self.is_running:
            try:
                opportunities = []
                
                # Check each token pair that exists on multiple DEXes
                for pair_key, pools in self.token_pair_map.items():
                    if len(pools) < 2:
                        continue
                    
                    # Find price differences
                    for i in range(len(pools)):
                        for j in range(i + 1, len(pools)):
                            opp = await self._check_arbitrage(pools[i], pools[j])
                            if opp:
                                opportunities.append(opp)
                
                # Sort by profit potential
                opportunities.sort(key=lambda x: x.expected_profit_sol, reverse=True)
                
                # Apply ML scoring to filter
                filtered_opps = self._apply_ml_filtering(opportunities)
                
                # Update active opportunities
                self.active_opportunities = filtered_opps[:50]  # Top 50
                
                # Track patterns for ML learning
                for opp in self.active_opportunities:
                    self._track_opportunity_pattern(opp)
                
                await asyncio.sleep(2)  # Fast scanning
                
            except Exception as e:
                print(f"Mining error: {str(e)}")
                await asyncio.sleep(5)
    
    async def _check_arbitrage(self, pool1: UniversalPool, pool2: UniversalPool) -> Optional[ArbitrageOpportunity]:
        """Check for arbitrage between two pools"""
        # Calculate price on each DEX
        price1 = pool1.reserves[1] / pool1.reserves[0] if pool1.reserves[0] > 0 else 0
        price2 = pool2.reserves[1] / pool2.reserves[0] if pool2.reserves[0] > 0 else 0
        
        if price1 == 0 or price2 == 0:
            return None
        
        # Calculate price difference
        price_diff_pct = abs(price1 - price2) / min(price1, price2) * 100
        
        # Need significant difference to cover fees and gas
        if price_diff_pct < 0.5:  # 0.5% minimum
            return None
        
        # Determine direction
        if price1 < price2:
            buy_pool, sell_pool = pool1, pool2
        else:
            buy_pool, sell_pool = pool2, pool1
        
        # Calculate profit (simplified)
        trade_amount = min(self.config.MAX_BUY_SOL, 0.5)
        expected_profit = trade_amount * price_diff_pct / 100
        
        # Factor in fees
        total_fees = (buy_pool.fee_rate + sell_pool.fee_rate) * trade_amount
        net_profit = expected_profit - total_fees - 0.001  # Gas estimate
        
        if net_profit <= 0:
            return None
        
        # Calculate confidence based on liquidity and volume
        liquidity_score = min(100, (min(buy_pool.liquidity_usd, sell_pool.liquidity_usd) / 10000) * 100)
        volume_score = min(100, (min(buy_pool.volume_24h, sell_pool.volume_24h) / 5000) * 100)
        token_score = (self.token_scores.get(pool1.token_a.address, 50) + 
                      self.token_scores.get(pool1.token_b.address, 50)) / 2
        
        confidence = (liquidity_score * 0.4 + volume_score * 0.3 + token_score * 0.3)
        
        return ArbitrageOpportunity(
            opportunity_id=f"CROSS_{buy_pool.dex}_{sell_pool.dex}_{int(time.time())}",
            pattern_type="CROSS_DEX",
            dexes=[buy_pool.dex, sell_pool.dex],
            token_path=[pool1.token_a.address, pool1.token_b.address],
            expected_profit_sol=net_profit,
            expected_profit_usd=net_profit * self.sol_price,
            price_impact=0.1,  # Would calculate based on liquidity
            confidence_score=confidence / 100,
            timestamp=time.time(),
            execution_path=[
                {"dex": buy_pool.dex, "action": "BUY", "pool": buy_pool.pool_address},
                {"dex": sell_pool.dex, "action": "SELL", "pool": sell_pool.pool_address}
            ]
        )
    
    def _apply_ml_filtering(self, opportunities: List[ArbitrageOpportunity]) -> List[ArbitrageOpportunity]:
        """Apply ML-like filtering based on learned patterns"""
        filtered = []
        
        for opp in opportunities:
            # Calculate ML score based on historical patterns
            pattern_score = self._calculate_pattern_score(opp)
            
            # Boost new tokens
            token_age_boost = 1.0
            for token_addr in opp.token_path:
                token = self.all_tokens.get(token_addr)
                if token and (time.time() - token.creation_time < 3600):  # Less than 1 hour old
                    token_age_boost = self.new_token_boost
                    break
            
            # Adjust confidence with ML score
            opp.confidence_score = min(1.0, opp.confidence_score * pattern_score * token_age_boost)
            
            # Filter based on enhanced confidence
            if opp.confidence_score > 0.6:
                filtered.append(opp)
        
        return filtered
    
    def _calculate_pattern_score(self, opp: ArbitrageOpportunity) -> float:
        """Calculate pattern score based on historical success"""
        # Simplified ML scoring - in production would use actual ML model
        pattern_key = f"{opp.pattern_type}_{'-'.join(opp.dexes)}"
        historical_patterns = self.opportunity_patterns.get(pattern_key, [])
        
        if not historical_patterns:
            return 0.8  # Default score for new patterns
        
        # Calculate success rate from historical data
        success_rate = sum(1 for p in historical_patterns if p.get("successful", False)) / len(historical_patterns)
        avg_profit = np.mean([p.get("profit", 0) for p in historical_patterns])
        
        # Combine into pattern score
        pattern_score = (success_rate * 0.7 + min(1.0, avg_profit / 0.01) * 0.3)
        return pattern_score
    
    async def _ml_pattern_learning_loop(self):
        """Learn from successful patterns to improve detection"""
        while self.is_running:
            try:
                # Analyze recent opportunities
                recent_opps = self.opportunity_history[-100:]
                
                # Group by pattern type
                pattern_analysis = defaultdict(list)
                for opp in recent_opps:
                    pattern_key = f"{opp.pattern_type}_{'-'.join(opp.dexes)}"
                    pattern_analysis[pattern_key].append({
                        "profit": opp.expected_profit_sol,
                        "confidence": opp.confidence_score,
                        "tokens": opp.token_path,
                        "timestamp": opp.timestamp
                    })
                
                # Update pattern scores
                for pattern_key, instances in pattern_analysis.items():
                    avg_profit = np.mean([i["profit"] for i in instances])
                    avg_confidence = np.mean([i["confidence"] for i in instances])
                    
                    # Store pattern performance
                    self.opportunity_patterns[pattern_key].append({
                        "avg_profit": avg_profit,
                        "avg_confidence": avg_confidence,
                        "instance_count": len(instances),
                        "timestamp": time.time()
                    })
                
                # Update token scores based on opportunity participation
                token_opportunity_count = defaultdict(int)
                token_total_profit = defaultdict(float)
                
                for opp in recent_opps:
                    for token in opp.token_path:
                        token_opportunity_count[token] += 1
                        token_total_profit[token] += opp.expected_profit_sol
                
                # Calculate new token scores
                for token_addr, count in token_opportunity_count.items():
                    avg_profit = token_total_profit[token_addr] / count
                    # Exponential moving average for token score
                    old_score = self.token_scores.get(token_addr, 50)
                    new_score = min(100, max(0, 50 + (avg_profit * 1000)))  # Scale profit to score
                    self.token_scores[token_addr] = old_score * 0.7 + new_score * 0.3
                
                await asyncio.sleep(60)  # Learn every minute
                
            except Exception as e:
                print(f"ML learning error: {str(e)}")
                await asyncio.sleep(60)
    
    async def _new_token_detection_loop(self):
        """Specifically monitor for new token launches"""
        while self.is_running:
            try:
                # Check for tokens created in last 5 minutes
                cutoff_time = time.time() - 300
                new_tokens = [
                    token for token in self.all_tokens.values() 
                    if token.creation_time > cutoff_time
                ]
                
                if new_tokens:
                    print(f"\n🚀 Found {len(new_tokens)} new tokens!")
                    for token in new_tokens[:5]:  # Show top 5
                        print(f"  • {token.symbol} - Liquidity: ${token.liquidity_usd:,.0f}")
                    
                    # Boost monitoring for pools with new tokens
                    for token in new_tokens:
                        # Find all pools with this token
                        for pools in self.token_pair_map.values():
                            for pool in pools:
                                if pool.token_a.address == token.address or pool.token_b.address == token.address:
                                    # Add to priority monitoring
                                    await self._check_new_token_arbitrage(pool, token)
                
                await asyncio.sleep(5)  # Fast checking for new tokens
                
            except Exception as e:
                print(f"New token detection error: {str(e)}")
                await asyncio.sleep(10)
    
    async def _check_new_token_arbitrage(self, pool: UniversalPool, new_token: TokenMetadata):
        """Special handling for new token arbitrage opportunities"""
        # New tokens often have higher volatility and price discrepancies
        # Apply different thresholds and strategies
        pass
    
    def _track_opportunity_pattern(self, opp: ArbitrageOpportunity):
        """Track opportunity patterns for ML learning"""
        pattern_data = {
            "pattern_type": opp.pattern_type,
            "dexes": opp.dexes,
            "tokens": opp.token_path,
            "expected_profit": opp.expected_profit_sol,
            "confidence": opp.confidence_score,
            "timestamp": opp.timestamp,
            "successful": None  # Would be updated after execution
        }
        
        pattern_key = f"{opp.pattern_type}_{'-'.join(opp.dexes)}"
        self.opportunity_patterns[pattern_key].append(pattern_data)

async def main():
    """Run the Universal Arbitrage Hunter"""
    config = Config()
    
    # Override config for universal monitoring
    config.ACCEPT_ALL_TOKEN_PAIRS = True  # Monitor everything
    config.MIN_LIQUIDITY_TVL = 5000       # Lower threshold
    config.MAX_RISK_SCORE = 100           # Accept all risk levels (filter later)
    
    hunter = UniversalArbitrageHunter(config)
    
    try:
        await hunter.start_universal_monitoring()
    except KeyboardInterrupt:
        print("\n✋ Universal Hunter stopped")

if __name__ == "__main__":
    asyncio.run(main())
