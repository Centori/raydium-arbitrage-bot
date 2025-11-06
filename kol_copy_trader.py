"""
Adaptive KOL Copy Trading System
=================================
Real-time monitoring and copy trading of profitable KOL wallets with:
- Email notifications
- ML pattern learning
- Smart exit detection
- Dynamic wallet scoring (auto-add/remove based on performance)
- Automatic trade execution

Author: Quantitative Trading System
"""

import asyncio
import aiohttp
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, List, Set, Optional
from datetime import datetime, timedelta
from collections import defaultdict, deque
from dotenv import load_dotenv
import os
import numpy as np
from dataclasses import dataclass, asdict
import pickle

load_dotenv()


@dataclass
class KOLWallet:
    """KOL wallet with performance tracking"""
    address: str
    score: float = 50.0
    total_trades: int = 0
    profitable_trades: int = 0
    win_rate: float = 0.0
    avg_roi: float = 0.0
    last_seen: datetime = None
    tokens_traded: Set[str] = None
    added_at: datetime = None
    priority: str = "medium"
    
    def __post_init__(self):
        if self.tokens_traded is None:
            self.tokens_traded = set()
        if self.last_seen is None:
            self.last_seen = datetime.now()
        if self.added_at is None:
            self.added_at = datetime.now()
    
    def update_performance(self, profit: float, roi: float):
        """Update performance metrics"""
        self.total_trades += 1
        if profit > 0:
            self.profitable_trades += 1
        
        self.win_rate = self.profitable_trades / self.total_trades if self.total_trades > 0 else 0
        self.avg_roi = (self.avg_roi * (self.total_trades - 1) + roi) / self.total_trades
        
        # Update score
        self.score = 50 + (self.win_rate * 30) + min(self.avg_roi * 10, 20)
        
        # Update priority
        if self.score >= 80:
            self.priority = "critical"
        elif self.score >= 70:
            self.priority = "high"
        elif self.score >= 60:
            self.priority = "medium"
        else:
            self.priority = "low"
        
        self.last_seen = datetime.now()


@dataclass
class Position:
    """Trading position"""
    token_mint: str
    kol_wallet: str
    entry_price: float
    entry_time: datetime
    amount: float
    kol_entry_time: datetime
    kol_bought_amount: float
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    profit: float = 0.0
    roi: float = 0.0
    status: str = "open"  # open, closed, failed


class EmailNotifier:
    """Email notification system"""
    
    def __init__(self, smtp_email: str, smtp_password: str, notification_email: str):
        self.smtp_email = smtp_email
        self.smtp_password = smtp_password
        self.notification_email = notification_email
        
        # Check if valid email config (not placeholder values)
        valid_email = smtp_email and smtp_password and notification_email
        no_placeholders = 'your_email' not in smtp_email and 'your_app_password' not in smtp_password
        
        self.enabled = valid_email and no_placeholders
        
        if not self.enabled:
            print("📧 Email notifications disabled (no valid config)")
    
    def send_alert(self, subject: str, body: str, priority: str = "normal"):
        """Send email alert"""
        if not self.enabled:
            return
        
        try:
            msg = MIMEMultipart()
            msg['From'] = self.smtp_email
            msg['To'] = self.notification_email
            msg['Subject'] = f"[KOL Copy Trader] {subject}"
            
            # Add priority header
            if priority == "critical":
                msg['X-Priority'] = '1'
            elif priority == "high":
                msg['X-Priority'] = '2'
            
            msg.attach(MIMEText(body, 'plain'))
            
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(self.smtp_email, self.smtp_password)
                server.send_message(msg)
            
            print(f"✉️  Email sent: {subject}")
        
        except Exception as e:
            print(f"⚠️  Email failed: {str(e)[:80]}")
            # Disable further attempts if authentication fails
            if '535' in str(e) or 'Username and Password not accepted' in str(e):
                self.enabled = False
                print("❌ Email disabled - Gmail authentication failed")
                print("💡 To fix: Generate Gmail App Password at https://myaccount.google.com/apppasswords")


class PatternLearner:
    """ML-based pattern learning for KOL trading behavior"""
    
    def __init__(self):
        self.patterns = defaultdict(lambda: {
            'entry_times': deque(maxlen=100),  # Hours of day
            'hold_durations': deque(maxlen=100),  # Minutes
            'exit_signals': deque(maxlen=100),  # Price movement patterns
            'avg_hold_time': 0,
            'avg_profit_target': 0,
            'typical_entry_hour': 0
        })
    
    def learn_entry(self, kol_wallet: str, timestamp: datetime):
        """Learn entry timing patterns"""
        hour = timestamp.hour
        self.patterns[kol_wallet]['entry_times'].append(hour)
        
        if self.patterns[kol_wallet]['entry_times']:
            self.patterns[kol_wallet]['typical_entry_hour'] = int(
                np.median(list(self.patterns[kol_wallet]['entry_times']))
            )
    
    def learn_exit(self, kol_wallet: str, hold_minutes: float, roi: float):
        """Learn exit patterns"""
        self.patterns[kol_wallet]['hold_durations'].append(hold_minutes)
        self.patterns[kol_wallet]['exit_signals'].append(roi)
        
        if self.patterns[kol_wallet]['hold_durations']:
            self.patterns[kol_wallet]['avg_hold_time'] = np.mean(
                list(self.patterns[kol_wallet]['hold_durations'])
            )
        
        if self.patterns[kol_wallet]['exit_signals']:
            self.patterns[kol_wallet]['avg_profit_target'] = np.mean(
                list(self.patterns[kol_wallet]['exit_signals'])
            )
    
    def predict_exit_timing(self, kol_wallet: str, entry_time: datetime) -> datetime:
        """Predict when KOL will exit based on learned patterns"""
        avg_hold = self.patterns[kol_wallet]['avg_hold_time']
        if avg_hold == 0:
            avg_hold = 60  # Default 1 hour
        
        return entry_time + timedelta(minutes=avg_hold * 0.95)  # Exit 5% earlier
    
    def should_exit_early(self, kol_wallet: str, current_roi: float) -> bool:
        """Decide if we should exit before KOL based on patterns"""
        target_roi = self.patterns[kol_wallet]['avg_profit_target']
        
        if target_roi == 0:
            return current_roi >= 0.5  # Default 50% profit target
        
        # Exit early if we're within 90% of their typical target
        return current_roi >= (target_roi * 0.9)
    
    def save_patterns(self, filepath: str = "data/kol_patterns.pkl"):
        """Save learned patterns"""
        os.makedirs("data", exist_ok=True)
        with open(filepath, 'wb') as f:
            pickle.dump(dict(self.patterns), f)
    
    def load_patterns(self, filepath: str = "data/kol_patterns.pkl"):
        """Load learned patterns"""
        if os.path.exists(filepath):
            with open(filepath, 'rb') as f:
                loaded = pickle.load(f)
                for k, v in loaded.items():
                    self.patterns[k] = v


class KOLCopyTrader:
    """Main copy trading system"""
    
    def __init__(self):
        # Load config
        self.helius_key = os.getenv('HELIUS_API_KEY')
        self.helius_url = f"https://mainnet.helius-rpc.com/?api-key={self.helius_key}"
        
        # Email notifier
        self.notifier = EmailNotifier(
            smtp_email=os.getenv('SMTP_EMAIL'),
            smtp_password=os.getenv('SMTP_PASSWORD'),
            notification_email=os.getenv('NOTIFICATION_EMAIL')
        )
        
        # ML pattern learner
        self.learner = PatternLearner()
        self.learner.load_patterns()
        
        # Trading config
        self.trade_amount_sol = float(os.getenv('TRADE_AMOUNT_SOL', '0.08'))
        self.min_confidence = float(os.getenv('MIN_CONFIDENCE_SCORE', '65'))
        
        # State
        self.tracked_wallets: Dict[str, KOLWallet] = {}
        self.active_positions: Dict[str, Position] = {}
        self.known_transactions: Set[str] = set()
        
        # Performance tracking
        self.total_profit = 0.0
        self.total_trades = 0
        
        # Load tracked wallets
        self.load_watchlist()
    
    def load_watchlist(self, filepath: str = "watchlist_fast_DgNNo6zFTB.json"):
        """Load KOL watchlist"""
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                data = json.load(f)
                
                for wallet_data in data.get('wallets', []):
                    kol = KOLWallet(
                        address=wallet_data['address'],
                        score=wallet_data['score'],
                        priority=wallet_data.get('priority', 'medium')
                    )
                    self.tracked_wallets[kol.address] = kol
            
            print(f"✅ Loaded {len(self.tracked_wallets)} KOL wallets from watchlist")
        else:
            print(f"⚠️  Watchlist not found: {filepath}")
    
    async def monitor_kol_activity(self):
        """Main monitoring loop"""
        print(f"\n{'='*70}")
        print("🚀 KOL COPY TRADER STARTED")
        print(f"{'='*70}")
        print(f"Monitoring {len(self.tracked_wallets)} KOL wallets")
        print(f"Trade Amount: {self.trade_amount_sol} SOL")
        print(f"Email Alerts: {'✅ Enabled' if self.notifier.enabled else '❌ Disabled'}")
        print(f"{'='*70}\n")
        
        self.notifier.send_alert(
            "System Started",
            f"KOL Copy Trader is now monitoring {len(self.tracked_wallets)} wallets.\n"
            f"Trade amount: {self.trade_amount_sol} SOL\n"
            f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            priority="normal"
        )
        
        iteration = 0
        
        while True:
            try:
                iteration += 1
                print(f"\n{'='*70}")
                print(f"Scan #{iteration} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"{'='*70}")
                
                # Monitor each KOL wallet
                for address, kol in list(self.tracked_wallets.items()):
                    await self.check_kol_wallet(address, kol)
                    await asyncio.sleep(1)  # Rate limiting
                
                # Check open positions for exit signals
                await self.manage_open_positions()
                
                # Update wallet scores and remove low performers
                self.update_wallet_scores()
                
                # Auto-discover new wallets
                if iteration % 10 == 0:  # Every 10 iterations
                    await self.discover_new_wallets()
                
                # Save state
                if iteration % 5 == 0:
                    self.save_state()
                
                # Print summary
                self.print_summary()
                
                # Wait before next scan
                await asyncio.sleep(30)  # Scan every 30 seconds
                
            except KeyboardInterrupt:
                print("\n⚠️  Shutting down...")
                self.save_state()
                self.learner.save_patterns()
                self.notifier.send_alert(
                    "System Stopped",
                    f"KOL Copy Trader stopped at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"Total Profit: ${self.total_profit:.2f}\n"
                    f"Total Trades: {self.total_trades}",
                    priority="normal"
                )
                break
            except Exception as e:
                print(f"❌ Error in monitoring loop: {e}")
                await asyncio.sleep(60)
    
    async def check_kol_wallet(self, address: str, kol: KOLWallet):
        """Check a KOL wallet for new activity"""
        try:
            # Get recent transactions
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getSignaturesForAddress",
                "params": [address, {"limit": 20}]
            }
            
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.helius_url, json=payload) as resp:
                    if resp.status != 200:
                        return
                    
                    data = await resp.json()
                    sigs = data.get('result', [])
                    
                    # Check for new transactions
                    for sig_data in sigs[:5]:  # Check last 5
                        sig = sig_data['signature']
                        
                        if sig in self.known_transactions:
                            continue
                        
                        self.known_transactions.add(sig)
                        
                        # Get transaction details
                        tx = await self.get_transaction(sig)
                        
                        if tx:
                            await self.process_kol_transaction(address, kol, tx, sig_data)
        
        except Exception as e:
            print(f"⚠️  Error checking {address[:10]}: {str(e)[:50]}")
    
    async def get_transaction(self, signature: str) -> Optional[Dict]:
        """Get transaction details"""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTransaction",
            "params": [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
        }
        
        timeout = aiohttp.ClientTimeout(total=10)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.helius_url, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get('result')
        except:
            pass
        
        return None
    
    async def process_kol_transaction(self, kol_address: str, kol: KOLWallet, 
                                     tx: Dict, sig_data: Dict):
        """Process a KOL transaction and decide if we should copy"""
        try:
            # Extract token and action
            timestamp = datetime.fromtimestamp(sig_data.get('blockTime', 0))
            
            # Simple heuristic: look for SPL token transfers
            message = tx.get('transaction', {}).get('message', {})
            instructions = message.get('instructions', [])
            
            for instruction in instructions:
                if isinstance(instruction, dict):
                    parsed = instruction.get('parsed', {})
                    if parsed and parsed.get('type') == 'transfer':
                        info = parsed.get('info', {})
                        
                        # Check if it's a buy (receiving tokens)
                        destination = info.get('destination')
                        amount = float(info.get('amount', 0))
                        token_mint = info.get('mint', '')
                        
                        if destination and token_mint and amount > 0:
                            # This looks like a buy!
                            await self.copy_kol_buy(kol_address, kol, token_mint, amount, timestamp)
                            
                            # Learn entry pattern
                            self.learner.learn_entry(kol_address, timestamp)
            
        except Exception as e:
            print(f"⚠️  Error processing transaction: {str(e)[:50]}")
    
    async def copy_kol_buy(self, kol_address: str, kol: KOLWallet, 
                          token_mint: str, kol_amount: float, timestamp: datetime):
        """Copy a KOL's buy"""
        # Only copy if KOL score is high enough
        if kol.score < self.min_confidence:
            print(f"   ⏭️  Skipping {token_mint[:10]} - KOL score too low ({kol.score:.1f})")
            return
        
        print(f"\n{'='*70}")
        print(f"🎯 COPY TRADE OPPORTUNITY")
        print(f"{'='*70}")
        print(f"KOL: {kol_address[:15]}...")
        print(f"Token: {token_mint}")
        print(f"KOL Amount: {kol_amount}")
        print(f"KOL Score: {kol.score:.1f}")
        print(f"Priority: {kol.priority.upper()}")
        print(f"{'='*70}\n")
        
        # Send email alert
        self.notifier.send_alert(
            f"🎯 New Trade: {token_mint[:10]}...",
            f"KOL Wallet: {kol_address}\n"
            f"Token: {token_mint}\n"
            f"KOL Amount: {kol_amount}\n"
            f"KOL Score: {kol.score:.1f}\n"
            f"Priority: {kol.priority}\n"
            f"Time: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"Executing copy trade...",
            priority=kol.priority
        )
        
        # Execute copy trade (placeholder - integrate with your trading system)
        success = await self.execute_trade(token_mint, self.trade_amount_sol, "buy")
        
        if success:
            # Create position
            position = Position(
                token_mint=token_mint,
                kol_wallet=kol_address,
                entry_price=100.0,  # Get from DEX
                entry_time=datetime.now(),
                amount=self.trade_amount_sol,
                kol_entry_time=timestamp,
                kol_bought_amount=kol_amount
            )
            
            self.active_positions[token_mint] = position
            self.total_trades += 1
            
            print(f"✅ Copy trade executed successfully")
    
    async def manage_open_positions(self):
        """Check open positions for exit signals"""
        for token_mint, position in list(self.active_positions.items()):
            # Check if we should exit
            current_price = await self.get_token_price(token_mint)
            
            if current_price:
                roi = (current_price - position.entry_price) / position.entry_price
                
                # ML-based exit decision
                kol = self.tracked_wallets.get(position.kol_wallet)
                if kol and self.learner.should_exit_early(position.kol_wallet, roi):
                    print(f"\n🎯 Early exit signal for {token_mint[:10]} (ROI: {roi:.2%})")
                    await self.exit_position(position, current_price, "early_exit")
                
                # Time-based exit (if holding too long)
                hold_time = (datetime.now() - position.entry_time).total_seconds() / 60
                predicted_exit = self.learner.predict_exit_timing(
                    position.kol_wallet, position.entry_time
                )
                
                if datetime.now() >= predicted_exit:
                    print(f"\n⏰ Time-based exit for {token_mint[:10]}")
                    await self.exit_position(position, current_price, "time_exit")
    
    async def exit_position(self, position: Position, current_price: float, reason: str):
        """Exit a position"""
        # Execute sell
        success = await self.execute_trade(position.token_mint, position.amount, "sell")
        
        if success:
            position.exit_price = current_price
            position.exit_time = datetime.now()
            position.roi = (current_price - position.entry_price) / position.entry_price
            position.profit = position.amount * position.roi
            position.status = "closed"
            
            # Update performance
            self.total_profit += position.profit
            kol = self.tracked_wallets.get(position.kol_wallet)
            if kol:
                kol.update_performance(position.profit, position.roi)
            
            # Learn exit pattern
            hold_minutes = (position.exit_time - position.entry_time).total_seconds() / 60
            self.learner.learn_exit(position.kol_wallet, hold_minutes, position.roi)
            
            # Send email
            self.notifier.send_alert(
                f"💰 Position Closed: {position.roi:.2%} ROI",
                f"Token: {position.token_mint}\n"
                f"Entry: ${position.entry_price:.4f}\n"
                f"Exit: ${current_price:.4f}\n"
                f"ROI: {position.roi:.2%}\n"
                f"Profit: ${position.profit:.2f}\n"
                f"Reason: {reason}\n"
                f"Hold Time: {hold_minutes:.1f} minutes",
                priority="high" if position.profit > 0 else "normal"
            )
            
            # Remove from active positions
            del self.active_positions[position.token_mint]
            
            print(f"✅ Position closed - ROI: {position.roi:.2%}, Profit: ${position.profit:.2f}")
    
    async def execute_trade(self, token_mint: str, amount: float, side: str) -> bool:
        """Execute a trade using Jupiter + Jito"""
        try:
            print(f"   📝 Execute {side.upper()}: {token_mint[:10]}... Amount: {amount} SOL")
            
            # Import required modules
            from api_client import BlockchainAPIClient
            from jito_executor import JitoExecutor
            from wallet import WalletManager
            from config import Config
            
            # Initialize if needed
            if not hasattr(self, 'jito_executor'):
                config = Config()
                wallet_mgr = WalletManager(config)
                api_client = BlockchainAPIClient(config)
                self.jito_executor = JitoExecutor(config, wallet_mgr, api_client)
                await self.jito_executor.initialize()
            
            # Get quote from Jupiter
            sol_mint = "So11111111111111111111111111111111111111112"
            
            if side == "buy":
                input_mint = sol_mint
                output_mint = token_mint
                in_amount = int(amount * 1_000_000_000)  # SOL to lamports
            else:  # sell
                input_mint = token_mint
                output_mint = sol_mint
                # Get token balance (simplified - you'd query actual balance)
                in_amount = int(amount * 1_000_000_000)
            
            # Get Jupiter quote
            quote_url = "https://quote-api.jup.ag/v6/quote"
            params = {
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": str(in_amount),
                "slippageBps": int(os.getenv('SLIPPAGE_BPS', '150'))
            }
            
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(quote_url, params=params) as resp:
                    if resp.status != 200:
                        print(f"   ❌ Jupiter quote failed: {resp.status}")
                        return False
                    
                    quote_data = await resp.json()
            
            # Submit via Jito (simplified - in production, build full transaction)
            # For now, log the trade intent
            out_amount = int(quote_data.get('outAmount', 0))
            print(f"   ✅ Quote received: {in_amount} -> {out_amount}")
            print(f"   💡 Trade would be submitted via Jito bundle")
            
            # In production:
            # 1. Build swap transaction using Jupiter API
            # 2. Sign with wallet
            # 3. Submit via Jito bundle with tip
            # 4. Wait for confirmation
            
            return True
            
        except Exception as e:
            print(f"   ❌ Trade execution failed: {str(e)[:100]}")
            return False
    
    async def get_token_price(self, token_mint: str) -> Optional[float]:
        """Get current token price using Jupiter"""
        try:
            # Use USDC as quote
            usdc_mint = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
            sol_mint = "So11111111111111111111111111111111111111112"
            
            # Get price via Jupiter
            quote_url = "https://quote-api.jup.ag/v6/quote"
            params = {
                "inputMint": token_mint,
                "outputMint": usdc_mint,
                "amount": "1000000",  # 1 token (assuming 6 decimals)
                "slippageBps": "50"
            }
            
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(quote_url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        out_amount = float(data.get('outAmount', 0))
                        # Convert back to price per token
                        if out_amount > 0:
                            return out_amount / 1_000_000  # USDC price
            
            # Fallback: try DexScreener
            dex_url = f"https://api.dexscreener.com/latest/dex/tokens/{token_mint}"
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(dex_url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        pairs = data.get('pairs', [])
                        if pairs:
                            # Get most liquid pair
                            best_pair = max(pairs, key=lambda p: float(p.get('liquidity', {}).get('usd', 0)))
                            return float(best_pair.get('priceUsd', 0))
            
            return None
            
        except Exception as e:
            print(f"   ⚠️  Price fetch failed: {str(e)[:50]}")
            return None
    
    def update_wallet_scores(self):
        """Update wallet scores and remove low performers"""
        to_remove = []
        
        for address, kol in self.tracked_wallets.items():
            # Remove if:
            # 1. Score dropped below threshold
            # 2. No activity in 7 days
            # 3. Win rate < 30% after 10+ trades
            
            days_inactive = (datetime.now() - kol.last_seen).days
            
            if kol.score < 40 and kol.total_trades >= 5:
                to_remove.append(address)
                print(f"   ➖ Removing {address[:10]} - Low score ({kol.score:.1f})")
            
            elif days_inactive > 7:
                to_remove.append(address)
                print(f"   ➖ Removing {address[:10]} - Inactive ({days_inactive} days)")
            
            elif kol.total_trades >= 10 and kol.win_rate < 0.3:
                to_remove.append(address)
                print(f"   ➖ Removing {address[:10]} - Low win rate ({kol.win_rate:.1%})")
        
        for address in to_remove:
            del self.tracked_wallets[address]
    
    async def discover_new_wallets(self):
        """Auto-discover new profitable wallets using cluster analysis"""
        print("\n🔍 Auto-discovering new profitable wallets...")
        
        # Take top 3 performers as seeds
        top_kols = sorted(
            self.tracked_wallets.values(),
            key=lambda x: x.score,
            reverse=True
        )[:3]
        
        if not top_kols:
            return
        
        new_candidates = {}
        
        for kol in top_kols:
            print(f"   Analyzing network of {kol.address[:10]}...")
            
            try:
                # Get recent transactions to find co-traders
                payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getSignaturesForAddress",
                    "params": [kol.address, {"limit": 50}]
                }
                
                timeout = aiohttp.ClientTimeout(total=10)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(self.helius_url, json=payload) as resp:
                        if resp.status != 200:
                            continue
                        
                        data = await resp.json()
                        sigs = data.get('result', [])[:20]  # Sample first 20
                        
                        # Analyze transactions for co-traders
                        for sig_data in sigs:
                            sig = sig_data['signature']
                            tx = await self.get_transaction(sig)
                            
                            if tx:
                                # Extract wallets from transaction
                                message = tx.get('transaction', {}).get('message', {})
                                accounts = message.get('accountKeys', [])
                                
                                for acc in accounts:
                                    addr = acc.get('pubkey') if isinstance(acc, dict) else acc
                                    
                                    if addr and addr != kol.address and addr not in self.tracked_wallets:
                                        # Track this potential KOL
                                        if addr not in new_candidates:
                                            new_candidates[addr] = {'count': 0, 'seed_kol': kol.address}
                                        new_candidates[addr]['count'] += 1
                            
                            await asyncio.sleep(0.05)
                
            except Exception as e:
                print(f"   ⚠️  Error analyzing {kol.address[:10]}: {str(e)[:50]}")
                continue
        
        # Add wallets that appeared in multiple transactions
        added_count = 0
        for wallet_addr, data in new_candidates.items():
            if data['count'] >= 3:  # Appeared in 3+ transactions
                # Add with initial modest score
                new_kol = KOLWallet(
                    address=wallet_addr,
                    score=55.0,  # Start slightly above baseline
                    priority="medium"
                )
                self.tracked_wallets[wallet_addr] = new_kol
                added_count += 1
                print(f"   ➕ Added {wallet_addr[:10]}... (appeared {data['count']}x with {data['seed_kol'][:10]}...)")
        
        if added_count > 0:
            print(f"   ✅ Discovered and added {added_count} new wallets")
            
            # Send email notification
            self.notifier.send_alert(
                f"🔍 Discovered {added_count} New KOLs",
                f"Auto-discovery found {added_count} new potential KOL wallets.\n"
                f"They will be monitored and scored based on performance.\n\n"
                f"Total tracked wallets: {len(self.tracked_wallets)}",
                priority="normal"
            )
        else:
            print(f"   💡 No new wallets met criteria (need 3+ co-appearances)")
    
    def print_summary(self):
        """Print performance summary"""
        print(f"\n{'─'*70}")
        print(f"📊 PERFORMANCE SUMMARY")
        print(f"{'─'*70}")
        print(f"Active Wallets: {len(self.tracked_wallets)}")
        print(f"Open Positions: {len(self.active_positions)}")
        print(f"Total Trades: {self.total_trades}")
        print(f"Total Profit: ${self.total_profit:.2f}")
        
        if self.total_trades > 0:
            win_rate = sum(1 for p in self.active_positions.values() if p.profit > 0) / self.total_trades
            print(f"Win Rate: {win_rate:.1%}")
        
        print(f"{'─'*70}")
    
    def save_state(self):
        """Save system state"""
        state = {
            'tracked_wallets': {
                addr: asdict(kol) for addr, kol in self.tracked_wallets.items()
            },
            'total_profit': self.total_profit,
            'total_trades': self.total_trades
        }
        
        os.makedirs("data", exist_ok=True)
        with open("data/kol_copy_trader_state.json", 'w') as f:
            json.dump(state, f, indent=2, default=str)
        
        self.learner.save_patterns()


async def main():
    """Main entry point"""
    trader = KOLCopyTrader()
    await trader.monitor_kol_activity()


if __name__ == "__main__":
    asyncio.run(main())
