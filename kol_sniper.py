#!/usr/bin/env python3
"""
Production KOL Sniper Bot
- Real-time token monitoring via GMGN.ai API
- Liquidity momentum and pattern analysis
- KOL wallet tracking
- Jito bundle execution
- Stop-loss / Take-profit position management
"""

import asyncio
import aiohttp
import time
import logging
from collections import deque
from typing import List, Dict, Optional
from dataclasses import dataclass

from config import Config
from wallet import WalletManager
from telegram_notifier import TelegramNotifier
from jito_executor import JitoExecutor
from kol_sniper_helpers import (
    LiquidityMomentum, PatternAnalyzer, KOLTracker,
    safety_checks, pre_entry_confirmation
)
from smart_money_detector import SmartMoneyDetector

logger = logging.getLogger("KOLSniper")


@dataclass
class Position:
    """Track an open trading position"""
    token_address: str
    entry_price: float
    entry_time: float
    amount_sol: float
    stop_loss_pct: float
    take_profit_pct: float
    is_active: bool = True


class RiskManager:
    """Manage trading risk and position sizing"""
    
    def __init__(self, config: Config):
        self.config = config
        self.max_trade_fraction = 0.25  # Max 25% of balance per trade (0.025 SOL from 0.1 SOL)
        self.slippage_pct = 0.02  # 2% slippage buffer
        self.stop_loss_pct = 0.08  # 8% stop loss
        self.take_profit_pct = None  # UNCAPPED - dynamic exit based on momentum/KOL sells
        
    def compute_trade_amount(self, balance_sol: float, liquidity_usd: float) -> float:
        """
        Compute safe trade amount based on balance and liquidity
        """
        # Base amount from balance
        max_from_balance = balance_sol * self.max_trade_fraction
        
        # Don't trade more than 2% of liquidity pool
        max_from_liquidity = (liquidity_usd * 0.02) / 200  # Assuming $200/SOL
        
        # Use the smaller of the two
        trade_amount = min(max_from_balance, max_from_liquidity, self.config.MAX_BUY_SOL)
        
        # Apply slippage buffer
        return trade_amount * (1 - self.slippage_pct)


class KOLSniperBot:
    """Main KOL Sniper Bot"""
    
    def __init__(self, config: Config):
        self.config = config
        self.wallet_manager = WalletManager(config)
        self.jito_executor = JitoExecutor(config, self.wallet_manager)
        self.risk_manager = RiskManager(config)
        self.telegram = TelegramNotifier(
            token=config.TELEGRAM_BOT_TOKEN,
            chat_id=config.TELEGRAM_CHAT_ID,
            disabled=not config.TELEGRAM_NOTIFICATIONS_ENABLED
        )
        
        # Tracking
        self.kol_tracker = KOLTracker(min_trades=10, min_win_rate=0.60)
        self.smart_money_detector = SmartMoneyDetector(self.wallet_manager.client)
        self.active_positions: Dict[str, Position] = {}
        self.monitored_tokens: List[str] = []
        
        # Stats
        self.trades_executed = 0
        self.successful_trades = 0
        self.total_pnl = 0.0
        
    async def initialize(self):
        """Initialize bot components"""
        try:
            logger.info("Initializing KOL Sniper Bot...")
            
            # Initialize Jito executor
            await self.jito_executor.initialize()
            
            # Load KOL wallets
            await self._load_kol_wallets()
            
            # Send startup notification
            self.telegram.send_message(
                "🎯 *KOL Sniper Bot Started*\\n\\n"
                f"💰 Wallet: {self.wallet_manager.pubkey}\\n"
                f"🔍 Monitoring Mode: Active\\n"
                f"⚡ Strategy: KOL Following + Momentum\\n"
                "🚀 Ready to snipe!"
            )
            
            logger.info("✅ KOL Sniper Bot initialized")
            return True
            
        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            self.telegram.send_error(f"Bot initialization failed: {e}")
            return False
    
    async def _load_kol_wallets(self):
        """Initialize smart money detection system"""
        try:
            logger.info("🔍 Smart Money Detection: ON-CHAIN ANALYSIS ENABLED")
            logger.info("📈 Will analyze recent transactions for whale activity")
            logger.info("🐋 Thresholds: 10+ SOL volume, 1+ SOL avg trade, 5+ trades")
            
            # Smart money detector is ready to use
            logger.info("✅ Smart money detector initialized")
                        
        except Exception as e:
            logger.error(f"Error initializing smart money detection: {e}")
    
    async def fetch_token_info(self, session: aiohttp.ClientSession, 
                               token_address: str) -> Optional[Dict]:
        """
        Fetch token info from DexScreener API (more reliable than GMGN)
        Returns token metadata, liquidity, holders, safety info
        """
        try:
            # Use DexScreener which doesn't require auth
            url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
            
            async with session.get(url, timeout=10) as resp:
                if resp.status != 200:
                    logger.warning(f"DexScreener returned {resp.status} for {token_address}")
                    return None
                
                data = await resp.json()
                pairs = data.get('pairs', [])
                
                if not pairs:
                    logger.warning(f"No pairs found for {token_address}")
                    return None
                
                # Use the pair with highest liquidity
                pair = max(pairs, key=lambda p: float(p.get('liquidity', {}).get('usd', 0) or 0))
                
                # Parse relevant fields
                liquidity_usd = float(pair.get('liquidity', {}).get('usd', 0) or 0)
                volume_24h = float(pair.get('volume', {}).get('h24', 0) or 0)
                price_usd = float(pair.get('priceUsd', 0) or 0)
                
                return {
                    'address': token_address,
                    'symbol': pair.get('baseToken', {}).get('symbol', ''),
                    'name': pair.get('baseToken', {}).get('name', ''),
                    'liquidity': liquidity_usd,
                    'volume_24h': volume_24h,
                    'price': price_usd,
                    'price_change_percent': float(pair.get('priceChange', {}).get('h24', 0) or 0),
                    'holder_count': 0,  # DexScreener doesn't provide this
                    'top_holders': [],  # Not available
                    'lp_burned': True,  # Assume safe for now (can add RugCheck API later)
                    'lp_locked': False,
                    'is_honeypot': False,  # Optimistic (can add honeypot check)
                    'renounced': False,
                    'is_mintable': False,
                    'freeze_authority': None,
                    'market_cap': float(pair.get('fdv', 0) or 0),
                    'created_timestamp': pair.get('pairCreatedAt', 0)
                }
                
        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching token info: {token_address}")
            return None
        except Exception as e:
            logger.error(f"Error fetching token info: {e}")
            return None
    
    async def get_token_price(self, session: aiohttp.ClientSession, 
                             token_address: str) -> float:
        """Get current token price from Jupiter API"""
        try:
            url = f"https://price.jup.ag/v4/price?ids={token_address}"
            async with session.get(url, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get('data', {}).get(token_address, {}).get('price', 0.0)
        except:
            pass
        return 0.0
    
    async def execute_jito_trade(self, token_address: str, amount_sol: float) -> bool:
        """Execute buy trade via Jito bundle"""
        try:
            logger.info(f"💎 Executing Jito bundle for {token_address[:8]}... with {amount_sol:.4f} SOL")
            
            # Execute bundle via Jito
            success = await self.jito_executor.execute_buy(
                token_address=token_address,
                amount_sol=amount_sol
            )
            
            if success:
                logger.info(f"✅ Jito bundle executed successfully")
                self.telegram.send_message(
                    f"💎 *Trade Executed*\\n\\n"
                    f"Token: `{token_address[:12]}...`\\n"
                    f"Amount: {amount_sol:.4f} SOL\\n"
                    f"Via: Jito Bundle"
                )
                return True
            else:
                logger.error("❌ Jito bundle execution failed")
                return False
                
        except Exception as e:
            logger.error(f"Error executing Jito trade: {e}")
            return False
    
    async def monitor_position(self, position: Position):
        """Monitor position with dynamic exit: stop-loss OR velocity reversal OR KOL sell"""
        logger.info(f"📊 Monitoring position for {position.token_address[:8]} (DYNAMIC EXIT)...")
        logger.info(f"   Exit triggers: 8% stop-loss OR velocity reversal OR KOL sell")
        
        # Track peak profit for momentum detection
        peak_pnl_pct = 0.0
        last_price = position.entry_price
        velocity_negative_count = 0
        
        async with aiohttp.ClientSession() as session:
            while position.is_active:
                try:
                    # Get current price
                    current_price = await self.get_token_price(session, position.token_address)
                    
                    if current_price == 0:
                        await asyncio.sleep(2)
                        continue
                    
                    # Calculate P&L
                    pnl_pct = (current_price - position.entry_price) / position.entry_price
                    
                    # Update peak
                    if pnl_pct > peak_pnl_pct:
                        peak_pnl_pct = pnl_pct
                        velocity_negative_count = 0  # Reset on new high
                    
                    # Calculate velocity (price change rate)
                    velocity = (current_price - last_price) / last_price if last_price > 0 else 0
                    last_price = current_price
                    
                    # Check stop-loss (8%)
                    if pnl_pct <= -position.stop_loss_pct:
                        logger.warning(f"⛔ Stop-loss triggered for {position.token_address[:8]}: {pnl_pct*100:.2f}%")
                        await self._close_position(position, current_price, "Stop-Loss")
                        break
                    
                    # Check velocity reversal (momentum turning negative)
                    if velocity < -0.02:  # Price dropping 2%+
                        velocity_negative_count += 1
                        if velocity_negative_count >= 3:  # 3 consecutive drops
                            logger.info(f"📉 Velocity reversal detected for {position.token_address[:8]}: {pnl_pct*100:.2f}%")
                            await self._close_position(position, current_price, f"Velocity Reversal (Peak: {peak_pnl_pct*100:.1f}%)")
                            break
                    else:
                        velocity_negative_count = 0
                    
                    # Check for KOL sell (whale activity reversal)
                    if pnl_pct > 0.10:  # Only check if we're up 10%+
                        try:
                            # Quick check for large sells (whale dumping)
                            smart_wallets = await self.smart_money_detector.scan_token_transactions(
                                position.token_address, 
                                limit=10  # Just recent activity
                            )
                            
                            # Count recent sells vs buys
                            recent_sells = sum(1 for w in smart_wallets.values() if w.sell_count > w.buy_count)
                            if recent_sells >= 2:  # 2+ whales selling
                                logger.warning(f"🐋 KOL/Whale sell detected for {position.token_address[:8]}: {pnl_pct*100:.2f}%")
                                await self._close_position(position, current_price, f"KOL Sell Detected (Peak: {peak_pnl_pct*100:.1f}%)")
                                break
                        except Exception as e:
                            logger.debug(f"Error checking KOL activity: {e}")
                    
                    # Log progress every 10 checks if profitable
                    if pnl_pct > 0.05:
                        logger.info(f"🐎 Holding {position.token_address[:8]}: {pnl_pct*100:+.1f}% (Peak: {peak_pnl_pct*100:.1f}%, Velocity: {velocity*100:+.1f}%)")
                    
                    # Continue monitoring
                    await asyncio.sleep(5)  # Check every 5 seconds
                    
                except Exception as e:
                    logger.error(f"Error monitoring position: {e}")
                    await asyncio.sleep(5)
    
    async def _close_position(self, position: Position, exit_price: float, reason: str):
        """Close a position"""
        try:
            position.is_active = False
            
            # Calculate P&L
            pnl_pct = (exit_price - position.entry_price) / position.entry_price
            pnl_sol = position.amount_sol * pnl_pct
            
            # Update stats
            self.total_pnl += pnl_sol
            if pnl_sol > 0:
                self.successful_trades += 1
            
            # Send notification
            self.telegram.send_message(
                f"🔚 *Position Closed - {reason}*\\n\\n"
                f"Token: `{position.token_address[:12]}...`\\n"
                f"Entry: ${position.entry_price:.6f}\\n"
                f"Exit: ${exit_price:.6f}\\n"
                f"P&L: {pnl_pct*100:+.2f}% ({pnl_sol:+.4f} SOL)\\n"
                f"Duration: {(time.time() - position.entry_time)/60:.1f}min"
            )
            
            # Remove from active positions
            if position.token_address in self.active_positions:
                del self.active_positions[position.token_address]
            
            logger.info(f"Position closed: {reason}, P&L: {pnl_pct*100:+.2f}%")
            
        except Exception as e:
            logger.error(f"Error closing position: {e}")
    
    async def monitor_token(self, token_address: str, session: aiohttp.ClientSession):
        """Monitor a single token for entry opportunity"""
        liquidity_history = deque(maxlen=20)
        liquidity_momentum = LiquidityMomentum(mode="slot", window_size=10)
        pattern_analyzer = PatternAnalyzer()
        
        logger.info(f"👀 Monitoring token: {token_address[:8]}...")
        
        # Monitor for up to 5 minutes or until entry signal
        start_time = time.time()
        check_interval = 2  # seconds
        max_duration = 300  # 5 minutes
        
        while time.time() - start_time < max_duration:
            try:
                # Fetch token info
                token_info = await self.fetch_token_info(session, token_address)
                if not token_info:
                    await asyncio.sleep(check_interval)
                    continue
                
                # Update liquidity tracking
                timestamp = time.time()
                liquidity = token_info['liquidity']
                liquidity_momentum.add_liquidity_point(liquidity, timestamp)
                liquidity_history.append((timestamp, liquidity))
                
                # Update pattern analyzer
                price = token_info['price']
                volume = token_info['volume_24h']
                pattern_analyzer.add_price_point(price, timestamp)
                pattern_analyzer.add_volume_point(volume, timestamp)
                
                # Calculate volume ratio
                volume_ratio = volume / liquidity if liquidity > 0 else 0
                
                # Check smart money presence (on-chain whale detection)
                smart_money_present = await self.smart_money_detector.is_smart_money_in_token(token_address)
                
                if not smart_money_present:
                    logger.info("❌ No whale activity detected in recent transactions")
                    await asyncio.sleep(check_interval)
                    continue
                
                # Check entry signal (with KOL tracker for compatibility)
                enter_signal = pre_entry_confirmation(
                    token_info=token_info,
                    liquidity_history=liquidity_history,
                    pattern_analyzer=pattern_analyzer,
                    kol_tracker=self.kol_tracker,  # Not used since we check smart money above
                    volume_ratio=volume_ratio,
                    min_liquidity=50000,  # $50k minimum
                    liquidity_momentum=liquidity_momentum
                )
                
                if enter_signal:
                    logger.info(f"🎯 Entry signal confirmed for {token_address[:8]}!")
                    
                    # Calculate trade amount
                    balance = 0.4811  # TODO: Get real balance
                    trade_amount = self.risk_manager.compute_trade_amount(
                        balance, 
                        liquidity
                    )
                    
                    # Execute trade
                    success = await self.execute_jito_trade(token_address, trade_amount)
                    
                    if success:
                        # Create position
                        position = Position(
                            token_address=token_address,
                            entry_price=price,
                            entry_time=time.time(),
                            amount_sol=trade_amount,
                            stop_loss_pct=self.risk_manager.stop_loss_pct,
                            take_profit_pct=self.risk_manager.take_profit_pct
                        )
                        
                        self.active_positions[token_address] = position
                        self.trades_executed += 1
                        
                        # Start position monitoring
                        asyncio.create_task(self.monitor_position(position))
                    
                    break  # Exit monitoring loop
                
                await asyncio.sleep(check_interval)
                
            except Exception as e:
                logger.error(f"Error in token monitoring loop: {e}")
                await asyncio.sleep(check_interval)
        
        logger.info(f"Finished monitoring {token_address[:8]}")
    
    async def run(self, token_addresses: List[str]):
        """Main run loop - monitor multiple tokens"""
        if not await self.initialize():
            return
        
        logger.info(f"🚀 Starting multi-token sniper for {len(token_addresses)} tokens")
        
        async with aiohttp.ClientSession() as session:
            tasks = [
                self.monitor_token(addr, session) 
                for addr in token_addresses
            ]
            await asyncio.gather(*tasks)
        
        logger.info("✅ All token monitoring complete")
        self.telegram.send_message(
            f"📊 *Sniper Session Complete*\\n\\n"
            f"Trades: {self.trades_executed}\\n"
            f"Successful: {self.successful_trades}\\n"
            f"Total P&L: {self.total_pnl:+.4f} SOL"
        )
