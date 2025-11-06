#!/usr/bin/env python3
"""
Aggressive Cross-DEX Arbitrage Bot
Optimized for growing 0.48 SOL -> 2.5 SOL rapidly

Focus: Cross-DEX price differences only (no Jito bundles, no expensive backruns)
"""

import asyncio
import logging
import signal
import sys
import time
from datetime import datetime
from config import Config
from api_client import BlockchainAPIClient
from raydium_pools import RaydiumPoolFetcher
from monitor_arbitrage_opportunities import ArbitrageMonitor
from telegram_notifier import TelegramNotifier
from wallet import WalletManager
from hft_executor import HFTExecutor
from decimal import Decimal

# Configure aggressive logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/aggressive_crossdex.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("AggressiveCrossDEX")

class AggressiveCrossDEXBot:
    def __init__(self):
        logger.info("=" * 60)
        logger.info("🚀 AGGRESSIVE CROSS-DEX ARBITRAGE BOT")
        logger.info("=" * 60)
        logger.info("Goal: 0.48 SOL → 2.5 SOL")
        logger.info("Strategy: Cross-DEX arbitrage only")
        logger.info("Risk: Moderate-High (No caps on ROI)")
        logger.info("=" * 60)
        
        self.config = Config()
        self.wallet_manager = WalletManager(self.config)
        self.api_client = BlockchainAPIClient(self.config)
        self.pool_fetcher = RaydiumPoolFetcher(self.config)
        self.monitor = ArbitrageMonitor(self.config)
        self.executor = HFTExecutor(self.config, self.wallet_manager)
        
        # Initialize Telegram for updates
        self.telegram = TelegramNotifier(
            token=self.config.TELEGRAM_BOT_TOKEN,
            chat_id=self.config.TELEGRAM_CHAT_ID,
            disabled=not self.config.TELEGRAM_NOTIFICATIONS_ENABLED
        )
        
        # Performance tracking
        self.start_time = time.time()
        self.start_balance = 0.48  # SOL
        self.target_balance = 2.5   # SOL
        self.trades_executed = 0
        self.successful_trades = 0
        self.total_profit = 0.0
        
        self._shutdown = False
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
    def _signal_handler(self, sig, frame):
        logger.info("Shutdown signal received...")
        self._shutdown = True
        
    async def initialize(self):
        """Initialize bot components"""
        try:
            logger.info("Initializing bot components...")
            
            # Initialize executor
            logger.info("Initializing HFT executor...")
            executor_ready = await self.executor.initialize()
            if not executor_ready:
                logger.warning("HFT executor initialization failed, trades may use fallback method")
            else:
                logger.info("✅ HFT executor ready")
            
            # Check wallet balance
            balance = await self._get_wallet_balance()
            logger.info(f"Current wallet balance: {balance:.4f} SOL")
            
            if balance < 0.02:
                raise ValueError("Insufficient balance for trading (minimum 0.02 SOL required)")
            
            self.start_balance = balance
            logger.info(f"Starting balance: {self.start_balance:.4f} SOL")
            logger.info(f"Target balance: {self.target_balance:.4f} SOL")
            logger.info(f"Required growth: {((self.target_balance/self.start_balance - 1) * 100):.1f}%")
            
            # Send startup notification
            self.telegram.send_message(
                f"🚀 *Aggressive Cross-DEX Bot Started*\n\n"
                f"💰 Start: {self.start_balance:.4f} SOL\n"
                f"🎯 Target: {self.target_balance:.4f} SOL\n"
                f"📈 Growth Needed: {((self.target_balance/self.start_balance - 1) * 100):.1f}%\n\n"
                f"⚡ Strategy: Cross-DEX Arbitrage\n"
                f"🎲 Risk Level: Moderate-High"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            self.telegram.send_error(f"Failed to start: {e}")
            return False
    
    async def _get_wallet_balance(self):
        """Get current SOL balance"""
        try:
            balance_response = await self.wallet_manager.client.get_balance(
                self.wallet_manager.keypair.pubkey()
            )
            return balance_response.value / 1e9  # Convert lamports to SOL
        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            return 0.0
    
    async def run(self):
        """Main bot loop"""
        if not await self.initialize():
            return
        
        logger.info("Starting aggressive cross-DEX arbitrage monitoring...")
        
        scan_count = 0
        last_progress_update = time.time()
        
        while not self._shutdown:
            try:
                scan_count += 1
                logger.info(f"\n{'='*60}")
                logger.info(f"Scan #{scan_count} - {datetime.now().strftime('%H:%M:%S')}")
                logger.info(f"{'='*60}")
                
                # Update pool data
                await self.pool_fetcher.fetch_all_pools()
                
                # Find arbitrage opportunities
                opportunities = await self.monitor.find_cross_dex_opportunities()
                
                if opportunities:
                    logger.info(f"✅ Found {len(opportunities)} opportunities!")
                    
                    # Sort by profit potential
                    opportunities.sort(key=lambda x: x.get('profit_usd', 0), reverse=True)
                    
                    # Execute best opportunities (top 3)
                    for opp in opportunities[:3]:
                        if self._shutdown:
                            break
                        
                        await self._execute_opportunity(opp)
                        
                        # Check if we've reached target
                        current_balance = await self._get_wallet_balance()
                        if current_balance >= self.target_balance:
                            logger.info(f"🎉 TARGET REACHED! Balance: {current_balance:.4f} SOL")
                            self.telegram.send_message(
                                f"🎉 *TARGET ACHIEVED!*\n\n"
                                f"💰 Final Balance: {current_balance:.4f} SOL\n"
                                f"📈 Profit: {(current_balance - self.start_balance):.4f} SOL\n"
                                f"✅ Trades: {self.successful_trades}/{self.trades_executed}\n"
                                f"⏱️ Time: {self._get_runtime()}"
                            )
                            return
                else:
                    logger.info("⏳ No opportunities found, continuing scan...")
                
                # Progress update every 5 minutes
                if time.time() - last_progress_update > 300:
                    await self._send_progress_update()
                    last_progress_update = time.time()
                
                # Wait before next scan (faster scanning for more opportunities)
                await asyncio.sleep(5)
                
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(10)
        
        logger.info("Bot stopped.")
        await self._send_final_report()
    
    async def _execute_opportunity(self, opportunity):
        """Execute arbitrage opportunity with real trades"""
        self.trades_executed += 1
        
        try:
            logger.info(f"\n💰 Executing opportunity #{self.trades_executed}")
            logger.info(f"   Pair: {opportunity.get('pair', 'Unknown')}")
            logger.info(f"   DEXes: {' → '.join(opportunity.get('dexes', []))}")
            logger.info(f"   Price diff: {opportunity.get('price_diff_pct', 0):.2f}%")
            logger.info(f"   ")
            logger.info(f"   💵 Profit Breakdown:")
            logger.info(f"      Net Profit: {opportunity.get('net_profit_sol', 0):.6f} SOL (${opportunity.get('profit_usd', 0):.2f})")
            logger.info(f"      Gas Cost: {opportunity.get('gas_cost', 0.0002):.6f} SOL")
            logger.info(f"      Price Impact: {opportunity.get('price_impact', 0):.4f}%")
            
            # Extract trade parameters
            dexes = opportunity.get('dexes', [])
            if len(dexes) < 2:
                logger.error("Invalid opportunity: requires at least 2 DEXes")
                return
            
            # Determine trade size based on confidence and balance
            current_balance = await self._get_wallet_balance()
            confidence = opportunity.get('confidence', 0.7)
            
            # Use conservative trade size: min(config, 10% of balance, scaled by confidence)
            max_trade = min(self.config.MAX_BUY_SOL, current_balance * 0.1)
            trade_size = max_trade * confidence
            trade_size = max(self.config.MIN_BUY_SOL, min(trade_size, 0.1))  # Cap at 0.1 SOL for safety
            
            logger.info(f"   Trade size: {trade_size:.4f} SOL (confidence: {confidence:.1%})")
            
            # For cross-DEX arbitrage, we need to:
            # 1. Buy on cheaper DEX
            # 2. Sell on more expensive DEX
            # For now, use Jupiter aggregator which handles routing
            
            # Get token addresses from opportunity
            # This is simplified - in production you'd track actual token mints
            sol_mint = "So11111111111111111111111111111111111111112"
            usdc_mint = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
            
            logger.info(f"   Executing swap via Jupiter aggregator...")
            
            # Execute the swap using HFTExecutor
            result = await self.executor.execute_trade_fast(
                pool_id="",  # Jupiter handles routing
                amount=Decimal(str(trade_size)),
                token_in=sol_mint,
                token_out=usdc_mint,
                max_slippage_bps=self.config.SLIPPAGE_BPS
            )
            
            if result.success:
                # Track success
                self.successful_trades += 1
                actual_profit = float(result.profit) if result.profit else 0.0
                self.total_profit += actual_profit
                
                logger.info(f"✅ Trade executed successfully!")
                logger.info(f"   Bundle ID: {result.bundle_id}")
                logger.info(f"   Execution time: {result.execution_time_ms:.0f}ms")
                logger.info(f"   Actual profit: {actual_profit:.4f} SOL")
                
                # Send Telegram notification for successful trades
                self.telegram.send_message(
                    f"✅ *Trade Executed*\n\n"
                    f"Pair: {opportunity.get('pair', 'Unknown')}\n"
                    f"Size: {trade_size:.4f} SOL\n"
                    f"Profit: {actual_profit:.4f} SOL\n"
                    f"Time: {result.execution_time_ms:.0f}ms\n"
                    f"Bundle: `{result.bundle_id}`"
                )
            else:
                logger.error(f"❌ Trade execution failed: {result.error}")
                logger.info(f"   Execution time: {result.execution_time_ms:.0f}ms")
            
        except Exception as e:
            logger.error(f"❌ Trade execution exception: {e}")
            import traceback
            logger.debug(traceback.format_exc())
    
    async def _send_progress_update(self):
        """Send progress update via Telegram"""
        try:
            current_balance = await self._get_wallet_balance()
            progress_pct = ((current_balance - self.start_balance) / 
                           (self.target_balance - self.start_balance)) * 100
            
            win_rate = (self.successful_trades / self.trades_executed * 100 
                       if self.trades_executed > 0 else 0)
            
            self.telegram.send_message(
                f"📊 *Progress Update*\n\n"
                f"💰 Balance: {current_balance:.4f} SOL\n"
                f"📈 Progress: {progress_pct:.1f}%\n"
                f"💵 Profit: +{(current_balance - self.start_balance):.4f} SOL\n"
                f"✅ Win Rate: {win_rate:.1f}% ({self.successful_trades}/{self.trades_executed})\n"
                f"⏱️ Runtime: {self._get_runtime()}"
            )
        except Exception as e:
            logger.error(f"Error sending progress update: {e}")
    
    async def _send_final_report(self):
        """Send final performance report"""
        try:
            current_balance = await self._get_wallet_balance()
            total_profit = current_balance - self.start_balance
            roi_pct = (total_profit / self.start_balance) * 100
            win_rate = (self.successful_trades / self.trades_executed * 100 
                       if self.trades_executed > 0 else 0)
            
            self.telegram.send_message(
                f"📊 *Final Report*\n\n"
                f"💰 Final Balance: {current_balance:.4f} SOL\n"
                f"📈 Total Profit: {total_profit:+.4f} SOL ({roi_pct:+.1f}%)\n"
                f"✅ Successful Trades: {self.successful_trades}/{self.trades_executed}\n"
                f"🎯 Win Rate: {win_rate:.1f}%\n"
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
    bot = AggressiveCrossDEXBot()
    await bot.run()

if __name__ == "__main__":
    asyncio.run(main())
