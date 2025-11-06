#!/usr/bin/env python3
"""
Raydium Triangular Arbitrage Bot
Focus: Finding profitable triangular arbitrage on Raydium DEX only
"""

import asyncio
import logging
import signal
import sys
import time
import aiohttp
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Any
from collections import defaultdict

from config import Config
from wallet import WalletManager
from telegram_notifier import TelegramNotifier
# Lazy import to avoid hanging - will import only when needed
# from hft_executor import HFTExecutor
from raydium_cache import RaydiumCache

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/raydium_triangular.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("RaydiumTriangular")

class RaydiumTriangularBot:
    def __init__(self):
        logger.info("=" * 60)
        logger.info("🔺 RAYDIUM TRIANGULAR ARBITRAGE BOT")
        logger.info("=" * 60)
        logger.info("Strategy: Triangular arbitrage on Raydium only")
        logger.info("Advantage: Reliable API, all trades on one DEX")
        logger.info("=" * 60)
        
        logger.info("DEBUG: Loading config...")
        self.config = Config()
        logger.info("DEBUG: Config loaded")
        
        logger.info("DEBUG: Initializing wallet manager...")
        self.wallet_manager = WalletManager(self.config)
        logger.info("DEBUG: Wallet manager initialized")
        
        self.executor = None  # Will initialize in async context
        
        logger.info("DEBUG: Setting up Telegram notifications...")
        # Telegram notifications
        self.telegram = TelegramNotifier(
            token=self.config.TELEGRAM_BOT_TOKEN,
            chat_id=self.config.TELEGRAM_CHAT_ID,
            disabled=not self.config.TELEGRAM_NOTIFICATIONS_ENABLED
        )
        logger.info("DEBUG: Telegram notifier initialized")
        
        # Performance tracking
        self.start_time = time.time()
        self.start_balance = 0.0
        self.trades_executed = 0
        self.successful_trades = 0
        self.total_profit = 0.0
        
        logger.info("DEBUG: Creating Raydium cache...")
        # Raydium data with smart caching
        self.raydium_cache = RaydiumCache()
        logger.info("DEBUG: Raydium cache created")
        
        self.raydium_pairs = []
        self.price_cache = {}
        self.last_update = 0
        self.update_interval = 300  # Refresh cache every 5 minutes
        
        self._shutdown = False
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        logger.info("DEBUG: __init__ complete")
        
    def _signal_handler(self, sig, frame):
        logger.info("Shutdown signal received...")
        self._shutdown = True
        
    async def initialize(self):
        """Initialize bot components"""
        try:
            logger.info("Initializing bot components...")
            
            # Check wallet balance with timeout
            logger.info("Fetching wallet balance...")
            try:
                balance = await asyncio.wait_for(
                    self._get_wallet_balance(), 
                    timeout=10.0
                )
                logger.info(f"Current wallet balance: {balance:.4f} SOL")
                
                if balance < 0.02:
                    raise ValueError("Insufficient balance for trading (minimum 0.02 SOL required)")
                
                self.start_balance = balance
                logger.info(f"Starting balance: {self.start_balance:.4f} SOL")
            except asyncio.TimeoutError:
                logger.warning("Balance fetch timed out - using fallback balance of 0.0 SOL")
                self.start_balance = 0.0
            except Exception as e:
                logger.warning(f"Balance fetch failed: {e} - continuing anyway")
                self.start_balance = 0.0
            
            # Initialize executor (must be done in async context) - OPTIONAL
            logger.info("Skipping HFT executor (simulation mode)...")
            self.executor = None
            # Lazy import disabled to avoid hanging during imports
            # try:
            #     from hft_executor import HFTExecutor
            #     self.executor = HFTExecutor(self.config, self.wallet_manager)
            #     executor_ready = await asyncio.wait_for(
            #         self.executor.initialize(),
            #         timeout=15.0
            #     )
            #     logger.info(f"✅ HFT executor initialized (ready={executor_ready})")
            # except asyncio.TimeoutError:
            #     logger.warning("⚠️ HFT executor initialization timed out - will use simulation mode")
            #     self.executor = None
            # except Exception as e:
            #     logger.warning(f"⚠️ HFT executor initialization failed: {e} - will use simulation mode")
            #     self.executor = None
            
            # Load Raydium pairs from cache (instant if cached)
            logger.info("Loading Raydium pairs from cache...")
            await self._load_raydium_pairs()
            logger.info(f"✅ Loaded {len(self.raydium_pairs)} Raydium pairs")
            
            # Send startup notification
            self.telegram.send_message(
                f"🔺 *Raydium Triangular Bot Started*\\n\\n"
                f"💰 Balance: {self.start_balance:.4f} SOL\\n"
                f"📊 Pairs Loaded: {len(self.raydium_pairs)}\\n"
                f"⚡ Strategy: Triangular Arbitrage\\n"
                f"🎯 Trade Size: {self.config.MAX_BUY_SOL} SOL"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            self.telegram.send_error(f"Failed to start: {e}")
            return False
    
    async def _get_wallet_balance(self):
        """Get current SOL balance with timeout protection"""
        try:
            logger.info("DEBUG: Calling get_balance on RPC...")
            balance_response = await asyncio.wait_for(
                self.wallet_manager.client.get_balance(
                    self.wallet_manager.keypair.pubkey()
                ),
                timeout=8.0
            )
            logger.info(f"DEBUG: Balance response received: {balance_response}")
            return balance_response.value / 1e9
        except asyncio.TimeoutError:
            logger.error("Balance fetch timed out after 8 seconds")
            return 0.0
        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            return 0.0
    
    async def _load_raydium_pairs(self):
        """Load pairs using smart cache - always prefer cache over download"""
        try:
            logger.info("Attempting to load from cache...")
            # Try to load from cache first (even if stale)
            pairs = await asyncio.get_event_loop().run_in_executor(
                None,
                self.raydium_cache.load_cache
            )
            
            logger.info(f"Cache load result: {len(pairs) if pairs else 'None'}")
            
            # Only download if no cache exists at all
            if not pairs:
                logger.info("No cache found, downloading from API...")
                pairs = await asyncio.get_event_loop().run_in_executor(
                    None,
                    self.raydium_cache.get_pairs
                )
            else:
                logger.info(f"✅ Successfully loaded {len(pairs)} pairs from cache")
            
            if not pairs:
                logger.error("Failed to load pairs from cache or API")
                return
            
            self.raydium_pairs = pairs
            
            # Build price cache for fast lookups
            self.price_cache = {}
            for pair in self.raydium_pairs:
                key = (pair['baseMint'], pair['quoteMint'])
                self.price_cache[key] = {
                    'price': pair.get('price', 0),
                    'liquidity': pair.get('liquidity', 0),
                    'ammId': pair.get('ammId', '')
                }
            
            self.last_update = time.time()
                        
        except Exception as e:
            logger.error(f"Error loading Raydium pairs: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def _update_prices(self):
        """Smart background refresh - tries to update but doesn't break if it fails"""
        cache_age_minutes = (time.time() - self.last_update) / 60
        
        if cache_age_minutes > (self.update_interval / 60):
            logger.info(f"Cache is {cache_age_minutes:.1f} min old - attempting background refresh...")
            
            try:
                # Start background refresh (non-blocking, fire-and-forget)
                # If it fails, we keep using old cache - no problem
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    self.raydium_cache.refresh_in_background
                )
                logger.info("Background refresh initiated (will complete in background)")
            except Exception as e:
                logger.warning(f"Background refresh failed (continuing with cached data): {e}")
            
            # Reset timer regardless of success/failure
            self.last_update = time.time()
    
    def _find_triangular_opportunities(self) -> List[Dict[str, Any]]:
        """Find triangular arbitrage opportunities"""
        opportunities = []
        
        # Build token graph
        token_graph = defaultdict(list)
        for pair in self.raydium_pairs:
            base = pair['baseMint']
            quote = pair['quoteMint']
            price = pair.get('price', 0)
            liquidity = pair.get('liquidity', 0)
            
            if price > 0:
                token_graph[base].append((quote, price, liquidity, pair))
                token_graph[quote].append((base, 1/price, liquidity, pair))
        
        # Find triangles
        checked = set()
        for token_a in token_graph:
            for token_b, price_ab, liq_ab, pair_ab in token_graph[token_a]:
                for token_c, price_bc, liq_bc, pair_bc in token_graph[token_b]:
                    if token_c == token_a:
                        continue
                    
                    # Check if we can complete the triangle
                    for token_back, price_ca, liq_ca, pair_ca in token_graph[token_c]:
                        if token_back == token_a:
                            # Found a triangle: A -> B -> C -> A
                            triangle_id = tuple(sorted([token_a, token_b, token_c]))
                            if triangle_id in checked:
                                continue
                            checked.add(triangle_id)
                            
                            # Calculate profit
                            combined_rate = price_ab * price_bc * price_ca
                            
                            if combined_rate > 1.0:
                                profit_pct = (combined_rate - 1.0) * 100
                                
                                # Calculate with realistic costs
                                trade_size = min(self.config.MAX_BUY_SOL, 0.08)
                                gross_profit = trade_size * profit_pct / 100
                                
                                # Costs for 3 swaps
                                gas_cost = 0.0003  # 3 transactions
                                slippage_cost = trade_size * 0.02  # 2% total slippage
                                dex_fees = trade_size * 0.0075  # 0.25% * 3 swaps
                                
                                net_profit = gross_profit - gas_cost - slippage_cost - dex_fees
                                
                                if net_profit > 0:
                                    # Check minimum liquidity
                                    min_liq = min(liq_ab, liq_bc, liq_ca)
                                    if min_liq > 100000:  # At least $100k liquidity
                                        opportunities.append({
                                            'type': 'TRIANGULAR',
                                            'tokens': [token_a, token_b, token_c],
                                            'pairs': [pair_ab, pair_bc, pair_ca],
                                            'combined_rate': combined_rate,
                                            'profit_pct': profit_pct,
                                            'net_profit_sol': net_profit,
                                            'net_profit_usd': net_profit * 200,  # Approx
                                            'min_liquidity': min_liq,
                                            'gas_cost': gas_cost,
                                            'trade_size': trade_size
                                        })
        
        return sorted(opportunities, key=lambda x: x['net_profit_sol'], reverse=True)
    
    async def run(self):
        """Main bot loop"""
        if not await self.initialize():
            return
        
        logger.info("Starting triangular arbitrage monitoring...")
        
        scan_count = 0
        last_progress_update = time.time()
        last_hourly_update = time.time()
        
        while not self._shutdown:
            try:
                scan_count += 1
                logger.info(f"\n{'='*60}")
                logger.info(f"Scan #{scan_count} - {datetime.now().strftime('%H:%M:%S')}")
                logger.info(f"{'='*60}")
                
                # Update prices if needed
                await self._update_prices()
                
                # Find opportunities
                opportunities = self._find_triangular_opportunities()
                
                if opportunities:
                    logger.info(f"✅ Found {len(opportunities)} triangular opportunities!")
                    
                    # Execute best opportunity
                    for opp in opportunities[:1]:  # Execute top 1 at a time
                        if self._shutdown:
                            break
                        
                        await self._execute_opportunity(opp)
                        
                        # Check if we've reached target
                        current_balance = await self._get_wallet_balance()
                        logger.info(f"Current balance: {current_balance:.4f} SOL")
                else:
                    logger.info("⏳ No profitable opportunities found, continuing scan...")
                
                # Hourly status update
                if time.time() - last_hourly_update > 3600:  # 1 hour
                    await self._send_hourly_status(scan_count)
                    last_hourly_update = time.time()
                
                # Progress update every 5 minutes
                if time.time() - last_progress_update > 300:
                    await self._send_progress_update()
                    last_progress_update = time.time()
                
                # Wait before next scan
                await asyncio.sleep(10)
                
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                import traceback
                logger.debug(traceback.format_exc())
                await asyncio.sleep(10)
        
        logger.info("Bot stopped.")
        await self._send_final_report()
    
    async def _execute_opportunity(self, opportunity):
        """Execute triangular arbitrage opportunity"""
        self.trades_executed += 1
        
        try:
            logger.info(f"\n🔺 Executing triangular arbitrage #{self.trades_executed}")
            logger.info(f"   Path: {' → '.join([t[:8] + '...' for t in opportunity['tokens']])} → {opportunity['tokens'][0][:8]}...")
            logger.info(f"   Combined Rate: {opportunity['combined_rate']:.4f}")
            logger.info(f"   Profit %: {opportunity['profit_pct']:.2f}%")
            logger.info(f"   Net Profit: {opportunity['net_profit_sol']:.6f} SOL (${opportunity['net_profit_usd']:.2f})")
            logger.info(f"   Min Liquidity: ${opportunity['min_liquidity']:,.0f}")
            logger.info(f"   Trade Size: {opportunity['trade_size']} SOL")
            
            # TODO: Implement actual execution with 3 swaps
            # For now, log the opportunity
            logger.info("   ⏳ Trade execution not yet implemented - logging opportunity")
            
            # Track as potential success
            # self.successful_trades += 1
            # self.total_profit += opportunity['net_profit_sol']
            
        except Exception as e:
            logger.error(f"❌ Trade execution failed: {e}")
    
    async def _send_hourly_status(self, scan_count: int):
        """Send hourly status update via Telegram"""
        try:
            current_balance = await self._get_wallet_balance()
            
            self.telegram.send_message(
                f"🔺 *Hourly Status Update*\\n\\n"
                f"✅ Loaded {len(self.raydium_pairs)} Raydium pairs\\n"
                f"📊 Completed {scan_count} scans\\n"
                f"💰 Balance: {current_balance:.4f} SOL\\n"
                f"📈 Opportunities found: {self.trades_executed}\\n"
                f"⏱️ Runtime: {self._get_runtime()}\\n"
                f"🤖 Status: Active"
            )
        except Exception as e:
            logger.error(f"Error sending hourly status: {e}")
    
    async def _send_progress_update(self):
        """Send progress update via Telegram"""
        try:
            current_balance = await self._get_wallet_balance()
            
            self.telegram.send_message(
                f"📊 *Progress Update*\\n\\n"
                f"💰 Balance: {current_balance:.4f} SOL\\n"
                f"✅ Trades: {self.successful_trades}/{self.trades_executed}\\n"
                f"📈 Profit: {self.total_profit:.4f} SOL\\n"
                f"⏱️ Runtime: {self._get_runtime()}"
            )
        except Exception as e:
            logger.error(f"Error sending progress update: {e}")
    
    async def _send_final_report(self):
        """Send final performance report"""
        try:
            current_balance = await self._get_wallet_balance()
            total_profit = current_balance - self.start_balance
            
            self.telegram.send_message(
                f"📊 *Final Report*\\n\\n"
                f"💰 Final Balance: {current_balance:.4f} SOL\\n"
                f"📈 Total Profit: {total_profit:+.4f} SOL\\n"
                f"✅ Successful Trades: {self.successful_trades}/{self.trades_executed}\\n"
                f"⏱️ Total Runtime: {self._get_runtime()}"
            )
        except Exception as e:
            logger.error(f"Error sending final report: {e}")
    
    def _get_runtime(self):
        """Get formatted runtime"""
        elapsed = time.time() - self.start_time
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        return f"{hours}h {minutes}m"

async def main():
    bot = RaydiumTriangularBot()
    await bot.run()

if __name__ == "__main__":
    asyncio.run(main())
