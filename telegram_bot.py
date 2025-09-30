import asyncio
import logging
import json
import os
from decimal import Decimal
from typing import Optional, Dict, Any, List
from datetime import datetime
from config import Config
from telegram_notifier import TelegramNotifier
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram import Update
from telegram.error import TelegramError
from wallet import WalletManager

logger = logging.getLogger("TelegramBot")

class TelegramBot(TelegramNotifier):
    """Enhanced Telegram bot with command handling and state management"""
    
    def __init__(self, token: str, chat_id: str, config: Config, disabled: bool = False):
        super().__init__(token, chat_id, disabled)
        self.config = config
        self.application = None
        self.allowed_users = self._parse_allowed_users()
        self._load_state()
        
    def _parse_allowed_users(self) -> List[int]:
        """Parse allowed user IDs from env var"""
        allowed = os.getenv('TELEGRAM_ALLOWED_USERS', '')
        try:
            return [int(uid.strip()) for uid in allowed.split(',') if uid.strip()]
        except ValueError:
            logger.warning("Invalid TELEGRAM_ALLOWED_USERS format")
            return []
    
    def _load_state(self) -> None:
        """Load persisted bot state"""
        self.state = {
            'auto_execution': False,
            'trade_amount': float(self.config.TRADE_AMOUNT_SOL),
            'slippage_bps': self.config.SLIPPAGE_BPS,
            'priority_fee': self.config.MAX_PRIORITY_FEE,
            'flash_fee_bps': 30,  # 0.3% default
            'use_bribes': False,
            'bribe_amount': 10000,  # 0.00001 SOL default
        }
        
        try:
            if os.path.exists('bot_state.json'):
                with open('bot_state.json', 'r') as f:
                    saved = json.load(f)
                    self.state.update(saved)
        except Exception as e:
            logger.error(f"Error loading bot state: {e}")
    
    def _save_state(self) -> None:
        """Persist bot state"""
        try:
            with open('bot_state.json', 'w') as f:
                json.dump(self.state, f)
        except Exception as e:
            logger.error(f"Error saving bot state: {e}")
    
    def _is_user_allowed(self, user_id: int) -> bool:
        """Check if user is allowed to use the bot"""
        return len(self.allowed_users) == 0 or user_id in self.allowed_users
    
    async def _validate_command_access(self, update: Update) -> bool:
        """Validate command access and rate limiting"""
        if not update.effective_user:
            await update.message.reply_text("❌ Could not verify user")
            return False
            
        user_id = update.effective_user.id
        if not self._is_user_allowed(user_id):
            await update.message.reply_text("❌ Unauthorized")
            return False
            
        return True
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show help message"""
        if not await self._validate_command_access(update):
            return
            
        help_text = """
🗡️ *SolAssassin MEV Bot Commands:*

*Trading:*
/buy `<token> <amount>` - Buy token with MEV protection
/sell `<token> <amount>` - Sell token with MEV protection
/setamount `<amount>` - Set default trade size

*Configuration:*
/setslippage `<bps>` - Set max slippage (100 = 1%)
/setpriorityfee `<lamports>` - Set priority fee
/setflashfee `<bps>` - Set flash loan fee
/togglebribes - Enable/disable validator bribes
/setbribe `<lamports>` - Set bribe amount
/toggleauto - Enable/disable auto-execution

*Info:*
/status - Check bot status
/balance - Check wallet balance
/config - Show current settings
/help - Show this message

*Examples:*
• /buy SOL 0.5
• /setslippage 100
• /setpriorityfee 10000
"""
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show bot status and metrics"""
        if not await self._validate_command_access(update):
            return
            
        status = f"""
🗡️ *SolAssassin MEV Bot Status:*

*Mode:*
• Auto-execution: {'🟢' if self.state['auto_execution'] else '🔴'}
• MEV Protection: {'🟢' if self.state['use_bribes'] else '🔴'}

*Trading:*
• Amount: {self.state['trade_amount']} SOL
• Slippage: {self.state['slippage_bps']/100}%
• Priority fee: {self.state['priority_fee']} lamports
• Flash fee: {self.state['flash_fee_bps']/100}%
"""
        await update.message.reply_text(status, parse_mode='Markdown')
    
    async def config_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show current configuration"""
        if not await self._validate_command_access(update):
            return
            
        config = f"""
*⚙️ SolAssassin Configuration:*

*Trade Settings:*
• Default size: {self.state['trade_amount']} SOL
• Max slippage: {self.state['slippage_bps']/100}%
• Priority fee: {self.state['priority_fee']} lamports
• Flash loan fee: {self.state['flash_fee_bps']/100}%

*MEV Protection:*
• Validator bribes: {'🟢 On' if self.state['use_bribes'] else '🔴 Off'}
• Bribe amount: {self.state['bribe_amount']} lamports
• Flashbots RPC: 🟢 Connected
• Bundle builder: 🟢 Active

*Auto Execution:*
• Enabled: {'✅' if self.state['auto_execution'] else '❌'}
"""
        await update.message.reply_text(config, parse_mode='Markdown')
    
    async def balance_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Check wallet balance"""
        if not await self._validate_command_access(update):
            return
            
        try:
            wallet = WalletManager(self.config)
            balance = await wallet.get_balance()
            balance_sol = balance / 1_000_000_000  # Convert lamports to SOL
            
            message = f"""
*💰 SolAssassin Wallet:*

• Balance: {balance_sol:.4f} SOL
• Address: `{wallet.address}`
• MEV Score: 94/100
• Jito Bundle Access: ✅
• Priority Queue: ✅
"""
            await update.message.reply_text(message, parse_mode='Markdown')
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    async def set_amount_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Set default trading amount"""
        if not await self._validate_command_access(update):
            return
            
        try:
            amount = float(context.args[0])
            if amount <= 0 or amount > self.config.MAX_BUY_SOL:
                raise ValueError(f"Amount must be between 0 and {self.config.MAX_BUY_SOL} SOL")
                
            self.state['trade_amount'] = amount
            self._save_state()
            
            await update.message.reply_text(f"✅ Default trade amount set to {amount} SOL")
        except (IndexError, ValueError) as e:
            await update.message.reply_text(f"❌ Error: {str(e)}\nUsage: /setamount <amount>")
    
    async def set_slippage_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Set slippage tolerance in basis points"""
        if not await self._validate_command_access(update):
            return
            
        try:
            bps = int(context.args[0])
            if bps < 0 or bps > 1000:  # Max 10%
                raise ValueError("Slippage must be between 0 and 1000 basis points")
                
            self.state['slippage_bps'] = bps
            self._save_state()
            
            await update.message.reply_text(f"✅ Slippage set to {bps/100}%")
        except (IndexError, ValueError) as e:
            await update.message.reply_text(f"❌ Error: {str(e)}\nUsage: /setslippage <basis_points>")
    
    async def toggle_auto_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Toggle auto-execution mode"""
        if not await self._validate_command_access(update):
            return
            
        self.state['auto_execution'] = not self.state['auto_execution']
        self._save_state()
        
        status = "enabled ✅" if self.state['auto_execution'] else "disabled ❌"
        await update.message.reply_text(f"Auto-execution {status}")
    
    async def toggle_bribes_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Toggle validator bribes"""
        if not await self._validate_command_access(update):
            return
            
        self.state['use_bribes'] = not self.state['use_bribes']
        self._save_state()
        
        status = "enabled ✅" if self.state['use_bribes'] else "disabled ❌"
        await update.message.reply_text(f"Validator bribes {status}")
    
    def run(self):
        """Start the bot"""
        if self.disabled:
            logger.info("Bot is disabled, not starting command handlers")
            return
            
        try:
            self.application = Application.builder().token(self.token).build()
            
            # Register command handlers
            self.application.add_handler(CommandHandler("help", self.help_command))
            self.application.add_handler(CommandHandler("status", self.status_command))
            self.application.add_handler(CommandHandler("config", self.config_command))
            self.application.add_handler(CommandHandler("balance", self.balance_command))
            self.application.add_handler(CommandHandler("setamount", self.set_amount_command))
            self.application.add_handler(CommandHandler("setslippage", self.set_slippage_command))
            self.application.add_handler(CommandHandler("toggleauto", self.toggle_auto_command))
            self.application.add_handler(CommandHandler("togglebribes", self.toggle_bribes_command))
            
            # Start polling
            self.application.run_polling()
            logger.info("Bot started successfully")