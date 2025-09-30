import asyncio
import time
import logging
from typing import List, Dict, Any, Optional
import json
from datetime import datetime, timezone
import os
import signal

from config import Config
from api_client import BlockchainAPIClient, ArbitrageOpportunity
from raydium_pools import RaydiumPoolFetcher
from token_detector import TokenDetector
from risk_analyzer import RiskAnalyzer
from jito_executor import JitoExecutor
from telegram_notifier import TelegramNotifier

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("arbitrage_bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("ArbitrageBot")

class ArbitrageBot:
    def __init__(self, config: Config):
        self.config = config
        self.api_client = BlockchainAPIClient(config)
        self.pool_fetcher = RaydiumPoolFetcher(config)
        self.token_detector = TokenDetector(config)
        self.risk_analyzer = RiskAnalyzer(config)
        
        # Initialize wallet manager
        from wallet import WalletManager
        self.wallet_manager = WalletManager(config)
        
        # Initialize Jito executor with wallet manager
        self.jito_executor = JitoExecutor(self.wallet_manager, config)
        
        # Initialize Telegram notifier
        self.telegram = TelegramNotifier(
            token=config.TELEGRAM_BOT_TOKEN,
            chat_id=config.TELEGRAM_CHAT_ID,
            disabled=not config.TELEGRAM_NOTIFICATIONS_ENABLED
        )
        
        # Keep track of pool data and market state
        self.pools = {}
        self.price_history = {}
        self.last_scan_time = 0
        self.last_full_refresh_time = 0
        self.full_refresh_interval = config.FULL_REFRESH_INTERVAL
        self.recent_opportunities = []
        self.max_recent_opportunities = 50
        
        # Performance tracking
        self.execution_attempts = 0
        self.successful_executions = 0
        self.cumulative_profit = 0.0
        self.execution_times = []
        self.failed_executions_reasons = {}
        
        # Create necessary directories
        os.makedirs("data", exist_ok=True)
        os.makedirs("data/metrics", exist_ok=True)
        
        # Graceful shutdown handling
        self._shutdown_event = asyncio.Event()
        self._is_running = False
        
        logger.info(f"ArbitrageBot initialized with full refresh interval: {self.full_refresh_interval}s")
        
    async def initialize(self) -> bool:
        """Initialize bot and connections"""
        try:
            # Check if API is available
            if not self.api_client.check_api_health():
                error_msg = "API service is not available"
                logger.error(error_msg)
                self.telegram.send_error(error_msg)
                return False
                
            # Initialize Jito executor
            jito_ready = await self.jito_executor.initialize()
            if not jito_ready:
                logger.warning("Jito executor not ready, bundle execution will be unavailable")
                self.telegram.send_message("⚠️ *Warning:* Jito executor not ready, bundle execution will be unavailable")
            
            # Initial data load with full refresh
            await self.update_market_data(force_full_refresh=True)
            return True
            
        except Exception as e:
            error_msg = f"Error during initialization: {str(e)}"
            logger.error(error_msg)
            self.telegram.send_error(error_msg)
            return False
    
    async def update_market_data(self, force_full_refresh=False) -> None:
        """
        Fetch latest pool data from API
        With periodic full refreshes to discover new pools
        """
        try:
            current_time = time.time()
            
            # Determine if we need a full refresh
            need_full_refresh = force_full_refresh or (
                current_time - self.last_full_refresh_time > self.full_refresh_interval
            )
            
            if need_full_refresh:
                logger.info("Performing full pool refresh to discover new pools")
                # Use the new async refresh method for full refresh
                pools = await self.pool_fetcher.refresh_pools_async()
                self.last_full_refresh_time = current_time
            else:
                # Regular update using cached data if available
                pools = self.pool_fetcher.fetch_all_pools()
            
            logger.info(f"Fetched {len(pools)} pools from API")
            
            # Track filtering reasons for debugging
            filtered_counts = {
                "invalid_token_pair": 0,
                "high_risk_score": 0,
                "low_liquidity": 0
            }
            
            # Filter for pools we're interested in
            filtered_pools = {}
            for pool in pools:
                # Apply token filtering logic
                is_valid_token_pair = self.token_detector.check_token_pair(
                    pool.base_token.address, 
                    pool.quote_token.address
                )
                
                if not is_valid_token_pair:
                    filtered_counts["invalid_token_pair"] += 1
                    continue
                
                # Check if pool is eligible (basic liquidity check)
                if not self.risk_analyzer.is_pool_eligible(pool):
                    filtered_counts["low_liquidity"] += 1
                    continue
                
                # Apply risk analysis
                risk_score = self.risk_analyzer.analyze_pool_risk(pool)
                
                if risk_score >= self.config.MAX_RISK_SCORE:
                    filtered_counts["high_risk_score"] += 1
                    continue
                
                # Add valid pool to our tracked pools
                filtered_pools[pool.id] = pool
            
            # Check for new pools compared to previous data
            new_pool_ids = set(filtered_pools.keys()) - set(self.pools.keys())
            if new_pool_ids and self.pools:  # Only if we had previous data
                logger.info(f"Discovered {len(new_pool_ids)} new valid pools")
                new_pool_info = []
                
                for pool_id in new_pool_ids:
                    pool = filtered_pools[pool_id]
                    new_pool_info.append({
                        "id": pool_id[:10] + "...",
                        "base": pool.base_token.symbol,
                        "quote": pool.quote_token.symbol,
                        "liquidity": f"${pool.quote_amount:.2f}" 
                    })
                
                # Notify about new pools that might have arbitrage opportunities
                if new_pool_info and len(new_pool_info) <= 5:  # Limit to avoid spam
                    msg = "🆕 *New Pools Detected*\n\n"
                    for pool in new_pool_info:
                        msg += f"• {pool['base']}/{pool['quote']} - {pool['liquidity']} TVL\n"
                    self.telegram.send_message(msg)
            
            # Log detailed filtering information
            total_filtered = len(pools) - len(filtered_pools
            )
            logger.info(f"Filtered to {len(filtered_pools)} valid pools. Filtered out {total_filtered} pools:")
            for reason, count in filtered_counts.items():
                logger.info(f"  - {reason}: {count} pools")
            
            self.pools = filtered_pools
            self.last_scan_time = current_time
            
        except Exception as e:
            logger.error(f"Error updating market data: {str(e)}")
    
    async def find_pair_arbitrage_opportunities(self) -> List[ArbitrageOpportunity]:
        """Find arbitrage opportunities between pairs of pools"""
        opportunities = []
        pools = list(self.pools.values())
        
        for i in range(len(pools)):
            for j in range(i + 1, len(pools)):
                pool1 = pools[i]
                pool2 = pools[j]
                
                # Check if pools share the same token pair
                if not (pool1.token_a == pool2.token_a and pool1.token_b == pool2.token_b) and \
                   not (pool1.token_a == pool2.token_b and pool1.token_b == pool2.token_a):
                    continue
                
                # Get prices from both pools
                price1 = pool1.get_token_price()
                price2 = pool2.get_token_price()
                
                # Calculate price difference
                price_diff = abs(price1 - price2)
                price_ratio = max(price1, price2) / min(price1, price2)
                
                # Check if difference is significant enough (e.g., >0.5%)
                if price_ratio > 1.005:
                    opportunity = ArbitrageOpportunity(
                        type="pair",
                        pools=[pool1, pool2],
                        expected_profit=price_diff,
                        execution_path=[pool1.address, pool2.address],
                        timestamp=time.time()
                    )
                    opportunities.append(opportunity)
        
        return opportunities
    
    async def find_triangle_arbitrage_opportunities(self) -> List[ArbitrageOpportunity]:
        """Find triangular arbitrage opportunities between three pools"""
        opportunities = []
        pools = list(self.pools.values())
        
        for i in range(len(pools)):
            for j in range(len(pools)):
                if i == j:
                    continue
                    
                for k in range(len(pools)):
                    if k == i or k == j:
                        continue
                        
                    pool1 = pools[i]
                    pool2 = pools[j]
                    pool3 = pools[k]
                    
                    # Check if pools form a triangle (A->B->C->A)
                    if not self._forms_valid_triangle(pool1, pool2, pool3):
                        continue
                    
                    # Calculate prices for the triangle path
                    try:
                        price1 = pool1.get_token_price()
                        price2 = pool2.get_token_price()
                        price3 = pool3.get_token_price()
                        
                        # Calculate the product of exchange rates
                        triangle_rate = price1 * price2 * price3
                        
                        # If triangle_rate > 1, there's an arbitrage opportunity
                        # Adding 0.3% threshold to account for fees
                        if triangle_rate > 1.003:
                            estimated_profit = (triangle_rate - 1.0) * 100  # Convert to percentage
                            
                            opportunity = ArbitrageOpportunity(
                                type="triangle",
                                pools=[pool1, pool2, pool3],
                                expected_profit=estimated_profit,
                                execution_path=[pool1.address, pool2.address, pool3.address],
                                timestamp=time.time()
                            )
                            opportunities.append(opportunity)
                            
                    except Exception as e:
                        logger.debug(f"Error calculating triangle arbitrage: {str(e)}")
                        continue
        
        return opportunities
        
    async def find_cross_dex_opportunities(self) -> List[ArbitrageOpportunity]:
        """Find arbitrage opportunities between Raydium and other DEXes via Jupiter API"""
        opportunities = []
        
        try:
            pools = list(self.pools.values())
            
            for pool in pools:
                # Get Raydium pool price
                raydium_price = pool.get_token_price()
                
                # Get price from Jupiter API for same token pair
                jupiter_price = await self.api_client.get_jupiter_price(
                    input_mint=pool.token_a,
                    output_mint=pool.token_b,
                    amount=1000000  # Use 1 SOL equivalent for price check
                )
                
                if not jupiter_price:
                    continue
                
                # Calculate price difference
                price_diff = abs(raydium_price - jupiter_price)
                price_ratio = max(raydium_price, jupiter_price) / min(raydium_price, jupiter_price)
                
                # Check if difference is significant enough (>0.5%)
                if price_ratio > 1.005:
                    opportunity = ArbitrageOpportunity(
                        type="cross_dex",
                        pools=[pool],
                        expected_profit=price_diff,
                        execution_path=[pool.address],
                        timestamp=time.time()
                    )
                    opportunities.append(opportunity)
            
            return opportunities
            
        except Exception as e:
            logger.error(f"Error finding cross-DEX opportunities: {str(e)}")
            return []

    async def find_flash_loan_opportunities(self) -> List[ArbitrageOpportunity]:
        """Find arbitrage opportunities that can be enhanced with flash loans from lending protocols"""
        opportunities = []
        
        try:
            pools = list(self.pools.values())
            
            # Check for potential token pairs that might benefit from flash loans
            for i in range(len(pools)):
                for j in range(i + 1, len(pools)):
                    pool1 = pools[i]
                    pool2 = pools[j]
                    
                    # Check if these pools share the same tokens but have a price difference
                    if (pool1.base_token.address == pool2.base_token.address and 
                        pool1.quote_token.address == pool2.quote_token.address) or \
                       (pool1.base_token.address == pool2.quote_token.address and 
                        pool1.quote_token.address == pool2.base_token.address):
                        
                        # Get prices from both pools
                        price1 = pool1.get_token_price()
                        price2 = pool2.get_token_price()
                        
                        price_ratio = max(price1, price2) / min(price1, price2)
                        
                        # For flash loans, we need higher threshold due to fees
                        if price_ratio > 1.01:  # 1% minimum difference to account for flash loan fees
                            # Calculate which token would be flash-loaned
                            if price1 > price2:
                                # Flash loan quote token from pool2
                                loan_token = pool2.quote_token
                                flash_loan_amount = min(
                                    pool1.base_reserves * 0.3,  # Don't impact price too much 
                                    pool2.quote_reserves * 0.3
                                )
                            else:
                                # Flash loan base token from pool1
                                loan_token = pool1.base_token
                                flash_loan_amount = min(
                                    pool2.base_reserves * 0.3,
                                    pool1.quote_reserves * 0.3
                                )
                            
                            # Calculate profit after fees (0.3% flash loan fee)
                            estimated_profit = ((price_ratio - 1) * flash_loan_amount) - (0.003 * flash_loan_amount)
                            
                            # Only include if still profitable after fees
                            if estimated_profit > 0:
                                opportunity = ArbitrageOpportunity(
                                    type="flash_loan",
                                    pools=[pool1, pool2],
                                    expected_profit=estimated_profit,
                                    execution_path=[pool1.address, pool2.address],
                                    timestamp=time.time(),
                                    flash_loan_token=loan_token.address,
                                    flash_loan_amount=flash_loan_amount
                                )
                                opportunities.append(opportunity)
            
            return opportunities
            
        except Exception as e:
            logger.error(f"Error finding flash loan opportunities: {str(e)}")
            return []

    def _forms_valid_triangle(self, pool1, pool2, pool3) -> bool:
        """Check if three pools form a valid triangular arbitrage path"""
        # Get all tokens involved
        tokens1 = {pool1.token_a, pool1.token_b}
        tokens2 = {pool2.token_a, pool2.token_b}
        tokens3 = {pool3.token_a, pool3.token_b}
        
        # For a valid triangle:
        # Pool1 and Pool2 must share exactly one token
        # Pool2 and Pool3 must share exactly one token
        # Pool3 and Pool1 must share exactly one token
        # And all three pools must involve exactly three different tokens
        
        shared12 = tokens1.intersection(tokens2)
        shared23 = tokens2.intersection(tokens3)
        shared31 = tokens3.intersection(tokens1)
        
        if len(shared12) != 1 or len(shared23) != 1 or len(shared31) != 1:
            return False
            
        # Check if we have exactly 3 unique tokens
        all_tokens = tokens1.union(tokens2).union(tokens3)
        return len(all_tokens) == 3
    
    async def scan_for_opportunities(self) -> List[ArbitrageOpportunity]:
        """Look for arbitrage opportunities among tracked pools"""
        opportunities = []
        
        try:
            # Ensure we have recent data
            current_time = time.time()
            time_since_update = current_time - self.last_scan_time
            
            # Regular update every 60 seconds
            # Full refresh based on full_refresh_interval
            if time_since_update > 60:
                need_full_refresh = (current_time - self.last_full_refresh_time) > self.full_refresh_interval
                await self.update_market_data(force_full_refresh=need_full_refresh)
            
            # Simple pair-wise arbitrage checks
            pair_opportunities = await self.find_pair_arbitrage_opportunities()
            if pair_opportunities:
                logger.info(f"Found {len(pair_opportunities)} pair arbitrage opportunities")
                opportunities.extend(pair_opportunities)
            
            # Triangle arbitrage checks
            triangle_opportunities = await self.find_triangle_arbitrage_opportunities()
            if triangle_opportunities:
                logger.info(f"Found {len(triangle_opportunities)} triangle arbitrage opportunities")
                opportunities.extend(triangle_opportunities)
            
            # Cross-DEX arbitrage opportunities via Jupiter
            if self.config.ENABLE_CROSS_DEX:
                cross_dex_opportunities = await self.find_cross_dex_opportunities()
                if cross_dex_opportunities:
                    logger.info(f"Found {len(cross_dex_opportunities)} cross-DEX arbitrage opportunities")
                    opportunities.extend(cross_dex_opportunities)
                    
            # Flash loan arbitrage opportunities with Solend
            flash_loan_opportunities = await self.find_flash_loan_opportunities()
            if flash_loan_opportunities:
                logger.info(f"Found {len(flash_loan_opportunities)} flash loan arbitrage opportunities")
                opportunities.extend(flash_loan_opportunities)
            
            # Apply improved filtering with liquidity depth consideration
            opportunities = self.filter_opportunities_by_liquidity_depth(opportunities)
            
            # Sort by expected profit
            opportunities.sort(
                key=lambda x: float(x.expected_profit), 
                reverse=True
            )
            
            # Identify new opportunities
            new_opportunities = self._find_new_opportunities(opportunities)
            
            # Update recent opportunities cache
            self._update_recent_opportunities(opportunities)
            
            # Notify about new high-value opportunities
            self._notify_about_new_opportunities(new_opportunities)
            
            logger.info(f"Found {len(opportunities)} total arbitrage opportunities")
            return opportunities
            
        except Exception as e:
            logger.error(f"Error scanning for opportunities: {str(e)}")
            return []
    
    def filter_opportunities_by_liquidity_depth(self, opportunities: List[ArbitrageOpportunity]) -> List[ArbitrageOpportunity]:
        """
        Filter arbitrage opportunities based on liquidity depth analysis
        
        This ensures we only execute trades that have sufficient depth to absorb our trade
        without excessive price impact.
        """
        if not opportunities:
            return []
        
        filtered_opportunities = []
        
        for opportunity in opportunities:
            # Skip if no pools data
            if not opportunity.pools or len(opportunity.pools) == 0:
                continue
            
            # Get opportunity details
            opportunity_type = opportunity.type
            expected_profit = float(opportunity.expected_profit)
            
            # Calculate trade size based on opportunity type
            if opportunity_type == "flash_loan":
                # For flash loans, use the provided flash loan amount
                trade_size = opportunity.flash_loan_amount if hasattr(opportunity, 'flash_loan_amount') else 0
            else:
                # For regular arbitrage, calculate optimal trade size based on liquidity
                trade_size = self._calculate_optimal_trade_size(opportunity)
            
            # Skip if trade size is too small
            if trade_size <= 0:
                logger.debug(f"Skipping opportunity with insufficient trade size")
                continue
                
            # Calculate expected price impact
            price_impact_percentage = self._calculate_price_impact(opportunity, trade_size)
            
            # Skip if price impact is too high relative to expected profit
            if price_impact_percentage >= expected_profit * 0.5:  # Price impact should be < 50% of profit
                logger.debug(f"Skipping opportunity with excessive price impact {price_impact_percentage}% vs profit {expected_profit}%")
                continue
            
            # Calculate effective profit after accounting for price impact
            effective_profit = expected_profit * (1 - price_impact_percentage / 100)
            
            # Update opportunity with additional analysis
            opportunity.trade_size = trade_size
            opportunity.price_impact = price_impact_percentage
            opportunity.effective_profit = effective_profit
            
            # Include opportunity if it still offers positive profit after impact
            if effective_profit > 0:
                filtered_opportunities.append(opportunity)
        
        logger.info(f"Filtered {len(opportunities)} opportunities to {len(filtered_opportunities)} with sufficient liquidity depth")
        return filtered_opportunities
        
    def _calculate_optimal_trade_size(self, opportunity: ArbitrageOpportunity) -> float:
        """
        Calculate optimal trade size based on pool liquidity and configuration
        
        Returns the amount in USD
        """
        try:
            # Default to configuration minimum
            min_trade = self.config.MIN_TRADE_SIZE_USD
            max_trade = self.config.MAX_TRADE_SIZE_USD
            
            # Get liquidity from pools
            pool_liquidity = []
            for pool in opportunity.pools:
                # For each pool, get the smaller of base/quote liquidity as the constraining factor
                # This is a simplified approach - in practice you'd use the specific reserve that'll be affected
                pool_liq = min(pool.base_amount, pool.quote_amount)
                pool_liquidity.append(pool_liq)
            
            # Cannot trade more than a fraction of the smallest pool's liquidity
            smallest_pool_liquidity = min(pool_liquidity) if pool_liquidity else 0
            max_size_by_liquidity = smallest_pool_liquidity * 0.1  # 10% of smallest pool's liquidity
            
            # Adjust based on opportunity type
            if opportunity.type == "triangle":
                # Triangle arbitrage typically needs more conservative sizing
                max_size_by_liquidity *= 0.7
            elif opportunity.type == "cross_dex":
                # Cross-DEX might allow slightly larger trades due to separate liquidity pools
                max_size_by_liquidity *= 1.2
            
            # Calculate optimal trade size
            optimal_size = min(max_size_by_liquidity, max_trade)
            
            # Ensure we meet minimum threshold
            if optimal_size < min_trade:
                logger.debug(f"Optimal trade size {optimal_size} below minimum {min_trade}")
                return 0
            
            return optimal_size
            
        except Exception as e:
            logger.error(f"Error calculating optimal trade size: {e}")
            return 0
            
    def _calculate_price_impact(self, opportunity: ArbitrageOpportunity, trade_size: float) -> float:
        """
        Estimate price impact of a trade on the pools involved
        
        Returns estimated price impact percentage
        """
        try:
            # If this is a tiny trade, impact will be minimal
            if trade_size < 10:
                return 0.1  # 0.1% minimum impact
            
            # Get impact for each pool involved
            pool_impacts = []
            
            for pool in opportunity.pools:
                # Get relevant pool data
                pool_size = pool.base_amount + pool.quote_amount
                
                if pool_size <= 0:
                    pool_impacts.append(100.0)  # Max impact for empty pool
                    continue
                
                # Calculate Uniswap/AMM-style price impact
                # impact = x / (x + L) where x is trade size and L is pool liquidity
                impact_percentage = (trade_size / (pool_size + trade_size)) * 100
                pool_impacts.append(impact_percentage)
            
            # For arbitrage, we care about the highest impact across all pools
            max_impact = max(pool_impacts) if pool_impacts else 0
            
            # Add a safety margin
            return max_impact * 1.2
            
        except Exception as e:
            logger.error(f"Error calculating price impact: {e}")
            return 100.0  # Assume maximum impact on error
    
    async def shutdown(self):
        """Gracefully shutdown the bot"""
        logger.info("Initiating graceful shutdown...")
        self._shutdown_event.set()
        self._is_running = False
        await asyncio.sleep(0.1)  # Allow pending tasks to complete

    async def run(self):
        """Main bot loop with graceful shutdown handling"""
        try:
            initialized = await self.initialize()
            if not initialized:
                return
                
            self._is_running = True
            
            while self._is_running:
                try:
                    # Check for shutdown signal
                    if self._shutdown_event.is_set():
                        break
                        
                    loop_start = time.time()
                    
                    # Scan for opportunities
                    opportunities = await self.scan_for_opportunities()
                    
                    # If profitable opportunities exist, execute the best one
                    if opportunities and len(opportunities) > 0:
                        best_opportunity = opportunities[0]
                        logger.info(f"Best opportunity: {best_opportunity.expected_profit} USD profit, "
                                   f"{best_opportunity.profit_percentage:.2f}% difference")
                        
                        # Enhanced execution criteria
                        min_profit = self.config.MIN_PROFIT_USD
                        gas_multiplier = self.config.GAS_COST_MULTIPLIER
                        gas_cost = float(best_opportunity.estimated_gas_cost)
                        
                        # Calculate profit threshold with gas consideration
                        profit_threshold = gas_cost * gas_multiplier
                        effective_min_profit = max(min_profit, profit_threshold)
                        
                        if float(best_opportunity.expected_profit) > effective_min_profit:
                            await self.execute_best_opportunity([best_opportunity])
                    
                    # Calculate how long this iteration took
                    loop_duration = time.time() - loop_start
                    
                    # Save performance metrics every hour
                    if time.time() - self.last_scan_time > 3600:  # 1 hour
                        self._save_performance_metrics()
                        self.last_scan_time = time.time()
                    
                    # Adaptive sleep based on loop duration to maintain ~5 second cadence
                    sleep_time = max(0.1, 5.0 - loop_duration)
                    
                    # Use wait_for with timeout to allow interruption
                    try:
                        await asyncio.wait_for(self._shutdown_event.wait(), timeout=sleep_time)
                        if self._shutdown_event.is_set():
                            break
                    except asyncio.TimeoutError:
                        continue
                        
                except asyncio.CancelledError:
                    logger.info("Received cancellation request")
                    break
                except Exception as e:
                    logger.error(f"Error in main loop: {str(e)}")
                    await asyncio.sleep(1)
                    
        finally:
            await self.shutdown()
            logger.info("Bot stopped")

async def main():
    """Main entry point with signal handling"""
    config = Config()
    bot = ArbitrageBot(config)
    
    def handle_signal(signum, frame):
        logger.info(f"Received signal {signum}")
        asyncio.create_task(bot.shutdown())
    
    # Register signal handlers
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, handle_signal)
    
    try:
        await bot.run()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
        await bot.shutdown()
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        await bot.shutdown()
        raise

if __name__ == "__main__":
    asyncio.run(main())
