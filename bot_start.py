#!/usr/bin/env python3
import asyncio
import logging
import sys
from datetime import datetime
from decimal import Decimal
from config import Config
from telegram_bot import TelegramBot
from wallet import WalletManager

# Configure logging with timestamp and level
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger()

# Initialize components
try:
    config = Config()
    wallet = WalletManager(config)
except Exception as e:
    logger.error(f"Failed to initialize: {e}")
    sys.exit(1)

# Create and start Telegram bot
bot = TelegramBot(
    token=config.TELEGRAM_BOT_TOKEN,
    chat_id=config.TELEGRAM_CHAT_ID,
    config=config
)

def main():
    """Entry point for the bot"""
    try:
        # Log startup
        logger.info("Starting SolAssassin_bot...")
        
        # Check wallet
        balance = asyncio.run(wallet.get_balance())
        balance_sol = balance / 1_000_000_000
        logger.info(f"Wallet loaded: {wallet.address}")
        logger.info(f"Balance: {balance_sol:.4f} SOL")
        
        # Start bot with command handling
        if bot.disabled:
            logger.warning("Bot is disabled - check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
            sys.exit(1)
        
        logger.info("Bot initialized - starting command handlers")
        bot.run()
        
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()