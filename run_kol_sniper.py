#!/usr/bin/env python3
"""
KOL Sniper Bot Runner
Entry point for production KOL sniping strategy
"""

import asyncio
import logging
import sys
import time
from typing import List

from config import Config
from kol_sniper import KOLSniperBot
from trending_fetcher import fetch_trending_solana
from email_notifier import EmailNotifier

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/kol_sniper.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("KOLSniperRunner")


async def get_trending_tokens() -> List[str]:
    """
    Get list of trending tokens using DexScreener API
    Filters for:
    - High liquidity ($50k+)
    - Recent launches (< 3 hours)
    - High 1h volume ($20k+)
    """
    logger.info("🔍 Fetching trending tokens from DexScreener...")
    
    tokens = await fetch_trending_solana(
        limit=10,
        min_liquidity_usd=50000,
        max_pair_age_minutes=180,  # 3 hours
        min_volume_h1_usd=20000
    )
    
    if not tokens:
        logger.warning("⚠️  No trending tokens found, using fallback list")
        # Fallback to test tokens if nothing trending
        return [
            "So11111111111111111111111111111111111111112",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        ]
    
    logger.info(f"✅ Found {len(tokens)} trending tokens")
    return tokens


async def main():
    """Main entry point with hourly email updates"""
    logger.info("=" * 60)
    logger.info("🎯 KOL SNIPER BOT - AUTO DISCOVERY MODE")
    logger.info("=" * 60)
    logger.info("Strategy: Smart Money + Momentum + FOMO Detection")
    logger.info("=" * 60)
    
    try:
        # Load configuration
        config = Config()
        
        # Validate wallet
        import os
        if not os.getenv('SOLANA_PRIVATE_KEY'):
            logger.error("❌ No SOLANA_PRIVATE_KEY found in .env")
            sys.exit(1)
        
        # Initialize email notifier
        email_notifier = EmailNotifier()
        
        # Create bot
        bot = KOLSniperBot(config)
        
        start_time = time.time()
        last_hourly_update = time.time()
        
        logger.info("🚀 Starting continuous auto-discovery mode...")
        
        # Continuous loop with hourly token refresh
        while True:
            try:
                # Get fresh trending tokens
                token_addresses = await get_trending_tokens()
                
                if not token_addresses:
                    logger.warning("⚠️  No tokens found, waiting 10 minutes...")
                    await asyncio.sleep(600)
                    continue
                
                logger.info(f"📋 Monitoring {len(token_addresses)} tokens for 1 hour")
                
                # Run bot on these tokens for 1 hour
                await bot.run(token_addresses)
                
                # Send hourly email update
                runtime_hours = (time.time() - start_time) / 3600
                whale_summary = bot.smart_money_detector.get_whale_summary()
                
                await email_notifier.send_hourly_kol_update(
                    tokens_monitored=len(token_addresses),
                    scans_completed=0,  # Can add scan counter
                    trades_executed=bot.trades_executed,
                    successful_trades=bot.successful_trades,
                    total_pnl_sol=bot.total_pnl,
                    whales_found=whale_summary['total_whales'],
                    runtime_hours=runtime_hours
                )
                
                logger.info("✅ Session complete, refreshing tokens...")
                
            except Exception as e:
                logger.error(f"❌ Error in main loop: {e}")
                import traceback
                logger.error(traceback.format_exc())
                await asyncio.sleep(300)  # Wait 5 min before retry
        
    except KeyboardInterrupt:
        logger.info("⏹️  Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
