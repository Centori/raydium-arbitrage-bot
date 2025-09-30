#!/usr/bin/env python3
import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal
import os

from config import Config
from migration_sniper import MigrationSniper
from raydium_pools import RaydiumPoolFetcher
from pool_analyzer import PoolAnalyzer
from risk_analyzer import RiskAnalyzer
from email_notifier import EmailNotifier
from wallet import WalletManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger()

class StrategyRunner:
    def __init__(self):
        self.config = Config()
        self.notifier = EmailNotifier()
        self.wallet = WalletManager(self.config)
        
        # Split allocation (0.3 SOL each)
        self.config.TRADE_AMOUNT_SOL = float(os.getenv('TRADE_AMOUNT_SOL', '0.3'))
        self.config.DEX_ALLOC = float(os.getenv('DEX_ALLOC', '0.3'))
        
        # Strategy stats
        self.stats = {
            'migration': {'profit': 0.0, 'trades': 0, 'success_rate': 0.0},
            'dex_arb': {'profit': 0.0, 'trades': 0, 'success_rate': 0.0}
        }
        self.last_summary = datetime.now()
        
    async def send_daily_summary(self):
        total_profit = sum(s['profit'] for s in self.stats.values())
        total_trades = sum(s['trades'] for s in self.stats.values())
        await self.notifier.send_daily_summary(self.stats, total_profit, total_trades)
        self.last_summary = datetime.now()
        
    async def run_migration_strategy(self):
        """Run the V3->V4 migration strategy"""
        try:
            # Initialize components
            pool_fetcher = RaydiumPoolFetcher(self.config)
            risk_analyzer = RiskAnalyzer(self.config)
            pool_analyzer = PoolAnalyzer(self.config, risk_analyzer)
            
            # Initialize sniper
            sniper = MigrationSniper(self.config, pool_fetcher, pool_analyzer)
            
            logger.info("Starting migration strategy monitoring...")
            while True:
                try:
                    # Check for opportunities
                    opportunities = await sniper.start_monitoring()
                    
                    # Process profitable opportunities
                    for opp in opportunities:
                        if opp.is_profitable and opp.estimated_profit > 0.001:  # Min 0.001 SOL profit
                            result = await sniper.execute_migration(opp)
                            if result and result.success:
                                self.stats['migration']['profit'] += float(result.amount_out)
                                self.stats['migration']['trades'] += 1
                                # Send notification
                                await self.notifier.send_trade_notification(
                                    "Migration",
                                    float(result.amount_out),
                                    result.tx_signature
                                )
                    
                    # Check if daily summary needed
                    if datetime.now() - self.last_summary > timedelta(days=1):
                        await self.send_daily_summary()
                        
                    await asyncio.sleep(1)  # Rate limit
                    
                except Exception as e:
                    logger.error(f"Error in migration monitoring: {e}")
                    await asyncio.sleep(5)  # Backoff on error
                    
        except Exception as e:
            logger.error(f"Fatal error in migration strategy: {e}")
    
    async def run_dex_arbitrage(self):
        """Run the DEX arbitrage strategy"""
        # This would import and run your existing DEX arbitrage code
        # For now, we'll just log that it would run
        logger.info("DEX arbitrage strategy would run here")
        while True:
            await asyncio.sleep(60)
    
    async def run_all_strategies(self):
        """Run all strategies concurrently"""
        try:
            # Verify wallet balance
            balance = await self.wallet.get_balance()
            balance_sol = balance / 1_000_000_000  # Convert lamports to SOL
            
            if balance_sol < 0.6:
                logger.error(f"Insufficient balance: {balance_sol} SOL (need 0.6 SOL)")
                return
                
            logger.info(f"Starting with balance: {balance_sol} SOL")
            logger.info(f"Allocating {self.config.TRADE_AMOUNT_SOL} SOL to migration strategy")
            logger.info(f"Allocating {self.config.DEX_ALLOC} SOL to DEX arbitrage")
            
            # Run strategies
            migration = asyncio.create_task(self.run_migration_strategy())
            dex_arb = asyncio.create_task(self.run_dex_arbitrage())
            
            # Wait for both to complete (they shouldn't unless there's an error)
            await asyncio.gather(migration, dex_arb)
            
        except Exception as e:
            logger.error(f"Fatal error running strategies: {e}")
            raise

async def main():
    runner = StrategyRunner()
    await runner.run_all_strategies()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise