import asyncio
import logging
import json
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from datetime import datetime, timedelta
import aiohttp
from decimal import Decimal

from config import Config
from api_client import BlockchainAPIClient

logger = logging.getLogger("kol_tracker")

@dataclass
class TradePerformance:
    wallet_address: str
    profitable_trades: int
    total_trades: int
    total_profit_usd: Decimal
    avg_trade_size_usd: Decimal
    last_trade_timestamp: int

@dataclass
class KOLTrade:
    wallet_address: str
    token_address: str
    token_symbol: str
    amount: Decimal
    price_usd: Decimal
    timestamp: int
    transaction_id: str
    is_buy: bool
    source: str  # 'jupiter', 'raydium', etc.

@dataclass
class KOLAlert:
    kol_name: str
    trade: KOLTrade
    confidence_score: float  # 0-1 based on trade size, wallet history, etc.
    correlation_score: float  # 0-1 based on correlation with other KOLs

class KOLTracker:
    """Tracks KOL trading activity across multiple sources"""
    
    # Well-known KOL wallets
    KOL_WALLETS = {
        "SOL_Mate": "7eDiHXpGzwHJsN9EhwqXu6jxSEkM4Sw1c6oWi4rZXvEQ",
        "DeGod": "9CipFGrq3n8qh2GcqRA6hdxhFezQXg6c5sLnKxfhJXry",
        # Add more KOL wallets here
    }
    
    def __init__(self, config: Config, api_client: BlockchainAPIClient):
        self.config = config
        self.api_client = api_client
        self.recent_trades: Dict[str, List[KOLTrade]] = {}
        self.tracked_tokens: Set[str] = set()
        self.alert_threshold_usd = 1000  # Minimum USD value for trade alerts
        self.min_correlation_score = 0.7
        
        # Wallet discovery settings
        self.min_profitable_trades = 8  # Minimum number of profitable trades out of 10
        self.min_avg_profit = 100  # Minimum average profit in USD
        self.discovery_window = 7 * 24 * 3600  # 7 days in seconds
        
        # Track wallet performance
        self.wallet_performance: Dict[str, TradePerformance] = {}
        
        # Dynamic KOL list
        self.discovered_kols: Set[str] = set()
        
        # Initialize Helius API client if key is available
        self.helius_api_key = getattr(config, "HELIUS_API_KEY", None)
        if self.helius_api_key:
            self.helius_api = f"https://api.helius.xyz/v0/addresses/?api-key={self.helius_api_key}"
        
        # Load historical KOL data
        self._load_historical_data()
    
    def _load_historical_data(self):
        """Load historical KOL trading data"""
        try:
            with open('data/kol_history.json', 'r') as f:
                data = json.load(f)
                self.recent_trades = {
                    wallet: [
                        KOLTrade(**trade_data)
                        for trade_data in trades
                    ]
                    for wallet, trades in data.items()
                }
        except FileNotFoundError:
            logger.info("No historical KOL data found")
        except Exception as e:
            logger.error(f"Error loading KOL history: {e}")
    
    def _save_historical_data(self):
        """Save KOL trading history and discovered KOLs"""
        try:
            with open('data/kol_history.json', 'w') as f:
                data = {
                    wallet: [
                        {
                            'wallet_address': t.wallet_address,
                            'token_address': t.token_address,
                            'token_symbol': t.token_symbol,
                            'amount': str(t.amount),
                            'price_usd': str(t.price_usd),
                            'timestamp': t.timestamp,
                            'transaction_id': t.transaction_id,
                            'is_buy': t.is_buy,
                            'source': t.source
                        }
                        for t in trades
                    ]
                    for wallet, trades in self.recent_trades.items()
                }
                
                # Add discovered KOLs and their performance
                data['discovered_kols'] = list(self.discovered_kols)
                data['wallet_performance'] = {
                    wallet: {
                        'profitable_trades': perf.profitable_trades,
                        'total_trades': perf.total_trades,
                        'total_profit_usd': str(perf.total_profit_usd),
                        'avg_trade_size_usd': str(perf.avg_trade_size_usd),
                        'last_trade_timestamp': perf.last_trade_timestamp
                    }
                    for wallet, perf in self.wallet_performance.items()
                }
                
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving KOL history: {e}")
    
    async def start_monitoring(self):
        """Start monitoring KOL wallets"""
        logger.info("Starting KOL tracker...")
        
        while True:
            try:
                await self._monitor_jupiter_swaps()
                await self._monitor_helius_transactions()
                await self._analyze_trading_patterns()
                
                # Save updated data
                self._save_historical_data()
                
                # Sleep to avoid rate limits
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"Error in KOL monitoring: {e}")
                await asyncio.sleep(5)
    
    async def _monitor_jupiter_swaps(self):
        """Monitor Jupiter API for KOL trades"""
        try:
            jupiter_url = "https://stats.jup.ag/api/trades"
            async with aiohttp.ClientSession() as session:
                async with session.get(jupiter_url) as response:
                    if response.status == 200:
                        trades = await response.json()
                        
                        for trade in trades:
                            wallet = trade.get('wallet')
                            if wallet in self.KOL_WALLETS.values():
                                kol_trade = KOLTrade(
                                    wallet_address=wallet,
                                    token_address=trade.get('outputMint'),
                                    token_symbol=trade.get('outputSymbol', 'UNKNOWN'),
                                    amount=Decimal(str(trade.get('outputAmount', 0))),
                                    price_usd=Decimal(str(trade.get('priceUsd', 0))),
                                    timestamp=int(trade.get('timestamp', 0)),
                                    transaction_id=trade.get('signature'),
                                    is_buy=True,
                                    source='jupiter'
                                )
                                
                                self._process_trade(kol_trade)
                    
        except Exception as e:
            logger.error(f"Error monitoring Jupiter swaps: {e}")
    
    async def _monitor_helius_transactions(self):
        """Monitor transactions using Helius API"""
        if not self.helius_api_key:
            return
            
        try:
            addresses = list(self.KOL_WALLETS.values())
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.helius_api,
                    json={
                        "addresses": addresses,
                        "query": {
                            "types": ["TOKEN_TRANSFER"]
                        }
                    }
                ) as response:
                    if response.status == 200:
                        transactions = await response.json()
                        for tx in transactions:
                            # Process Helius transaction data
                            await self._process_helius_transaction(tx)
                            
        except Exception as e:
            logger.error(f"Error monitoring Helius transactions: {e}")
    
    async def _process_helius_transaction(self, tx: dict):
        """Process a transaction from Helius API"""
        try:
            # Extract token transfer details
            token_transfers = tx.get('tokenTransfers', [])
            for transfer in token_transfers:
                kol_trade = KOLTrade(
                    wallet_address=tx.get('source'),
                    token_address=transfer.get('mint'),
                    token_symbol=transfer.get('tokenSymbol', 'UNKNOWN'),
                    amount=Decimal(str(transfer.get('amount', 0))),
                    price_usd=Decimal('0'),  # Need to fetch price
                    timestamp=tx.get('timestamp', 0),
                    transaction_id=tx.get('signature'),
                    is_buy=transfer.get('source') != tx.get('source'),
                    source='helius'
                )
                
                # Fetch token price if needed
                if kol_trade.price_usd == 0:
                    price = await self._fetch_token_price(kol_trade.token_address)
                    kol_trade.price_usd = price
                
                self._process_trade(kol_trade)
                
        except Exception as e:
            logger.error(f"Error processing Helius transaction: {e}")
    
    async def _fetch_token_price(self, token_address: str) -> Decimal:
        """Fetch token price from Birdeye API"""
        try:
            url = f"https://public-api.birdeye.so/public/price?address={token_address}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        return Decimal(str(data.get('value', 0)))
            return Decimal('0')
        except Exception as e:
            logger.error(f"Error fetching token price: {e}")
            return Decimal('0')
    
    def _process_trade(self, trade: KOLTrade):
        """Process and store a KOL trade"""
        wallet = trade.wallet_address
        if wallet not in self.recent_trades:
            self.recent_trades[wallet] = []
            
        # Add to recent trades
        self.recent_trades[wallet].append(trade)
        
        # Maintain last 24 hours of trades
        cutoff = int(datetime.now().timestamp()) - 86400
        self.recent_trades[wallet] = [
            t for t in self.recent_trades[wallet]
            if t.timestamp > cutoff
        ]
        
        # Track token
        self.tracked_tokens.add(trade.token_address)
        
        # Generate alert if significant
        if trade.price_usd * trade.amount >= self.alert_threshold_usd:
            alert = self._generate_alert(trade)
            if alert and alert.confidence_score >= 0.7:
                logger.info(f"KOL Alert: {alert.kol_name} {trade.token_symbol} "
                          f"{'bought' if trade.is_buy else 'sold'} "
                          f"${float(trade.price_usd * trade.amount):,.2f}")
    
    def _generate_alert(self, trade: KOLTrade) -> Optional[KOLAlert]:
        """Generate alert for significant KOL trade"""
        try:
            # Find KOL name
            kol_name = next(
                (name for name, addr in self.KOL_WALLETS.items()
                 if addr == trade.wallet_address),
                "Unknown KOL"
            )
            
            # Calculate confidence score
            trade_value = trade.price_usd * trade.amount
            size_score = min(trade_value / 10000, 1)  # Scale based on trade size
            
            # Check wallet history
            wallet_history = self.recent_trades.get(trade.wallet_address, [])
            history_score = len(wallet_history) / 100  # Scale based on activity
            
            # Calculate correlation with other KOLs
            correlation = self._calculate_kol_correlation(trade)
            
            confidence_score = (size_score + history_score) / 2
            
            return KOLAlert(
                kol_name=kol_name,
                trade=trade,
                confidence_score=confidence_score,
                correlation_score=correlation
            )
            
        except Exception as e:
            logger.error(f"Error generating alert: {e}")
            return None
    
    def _calculate_kol_correlation(self, trade: KOLTrade) -> float:
        """Calculate correlation of trade with other KOLs"""
        try:
            # Look for similar trades in last hour
            cutoff = trade.timestamp - 3600
            similar_trades = 0
            total_kols = len(self.KOL_WALLETS)
            
            for wallet, trades in self.recent_trades.items():
                if wallet != trade.wallet_address:
                    # Check if KOL made similar trade
                    for t in trades:
                        if (t.timestamp > cutoff and
                            t.token_address == trade.token_address and
                            t.is_buy == trade.is_buy):
                            similar_trades += 1
                            break
            
            return similar_trades / total_kols
            
        except Exception as e:
            logger.error(f"Error calculating correlation: {e}")
            return 0.0
    
    async def _analyze_trading_patterns(self):
        """Analyze KOL trading patterns and discover new KOLs"""
        try:
            # Update wallet performance and discover new KOLs
            await self._update_wallet_performance()
            await self._discover_new_kols()
            
            # Original token analysis
            for token in self.tracked_tokens:
                kol_interest = 0
                total_volume = Decimal('0')
                
                # Calculate KOL interest in token
                for wallet, trades in self.recent_trades.items():
                    token_trades = [
                        t for t in trades
                        if t.token_address == token
                    ]
                    
                    if token_trades:
                        kol_interest += 1
                        total_volume += sum(
                            t.amount * t.price_usd
                            for t in token_trades
                        )
                
                # Log significant patterns
                if kol_interest >= 2 and total_volume >= 10000:
                    logger.info(
                        f"Token {token} has interest from {kol_interest} KOLs "
                        f"with ${float(total_volume):,.2f} volume"
                    )
                    
        except Exception as e:
            logger.error(f"Error analyzing trading patterns: {e}")
    
    def get_token_kol_sentiment(self, token_address: str) -> float:
        """Get KOL sentiment score for a token"""
        try:
            positive_signals = 0
            total_signals = 0
            
            for wallet, trades in self.recent_trades.items():
                token_trades = [
                    t for t in trades
                    if t.token_address == token_address
                ]
                
                if token_trades:
                    # Calculate net buying/selling
                    net_amount = sum(
                        t.amount if t.is_buy else -t.amount
                        for t in token_trades
                    )
                    
                    if net_amount > 0:
                        positive_signals += 1
                    total_signals += 1
            
            return positive_signals / total_signals if total_signals > 0 else 0.5
            
        except Exception as e:
            logger.error(f"Error calculating token sentiment: {e}")
            return 0.5
            
    async def _update_wallet_performance(self):
        """Update performance metrics for all tracked wallets"""
        try:
            current_time = int(datetime.now().timestamp())
            discovery_cutoff = current_time - self.discovery_window
            
            # Get all unique wallets from recent trades
            all_wallets = set()
            for trades in self.recent_trades.values():
                for trade in trades:
                    all_wallets.add(trade.wallet_address)
            
            # Update performance for each wallet
            for wallet in all_wallets:
                trades = []
                for wallet_trades in self.recent_trades.values():
                    trades.extend([t for t in wallet_trades 
                                 if t.wallet_address == wallet and 
                                 t.timestamp > discovery_cutoff])
                
                if not trades:
                    continue
                
                # Calculate performance metrics
                profitable_trades = sum(1 for t in trades[-10:] 
                                      if t.price_usd * t.amount > 0)  # Simplified profit check
                total_profit = sum(t.price_usd * t.amount for t in trades)
                avg_trade_size = sum(t.price_usd * t.amount for t in trades) / len(trades)
                
                self.wallet_performance[wallet] = TradePerformance(
                    wallet_address=wallet,
                    profitable_trades=profitable_trades,
                    total_trades=len(trades[-10:]),  # Look at last 10 trades
                    total_profit_usd=Decimal(str(total_profit)),
                    avg_trade_size_usd=Decimal(str(avg_trade_size)),
                    last_trade_timestamp=max(t.timestamp for t in trades)
                )
                
        except Exception as e:
            logger.error(f"Error updating wallet performance: {e}")
    
    async def _discover_new_kols(self):
        """Discover new KOLs based on trading performance"""
        try:
            current_time = int(datetime.now().timestamp())
            
            for wallet, perf in self.wallet_performance.items():
                # Skip if already a known KOL
                if wallet in self.KOL_WALLETS.values() or wallet in self.discovered_kols:
                    continue
                
                # Check if wallet meets KOL criteria
                if (perf.profitable_trades >= self.min_profitable_trades and
                    perf.total_profit_usd > self.min_avg_profit * perf.total_trades and
                    perf.avg_trade_size_usd > self.alert_threshold_usd):
                    
                    logger.info(f"Discovered new KOL: {wallet} with "
                              f"{perf.profitable_trades}/{perf.total_trades} profitable trades ")
                    self.discovered_kols.add(wallet)
                    
                    # Save updated data
                    self._save_historical_data()
                    
        except Exception as e:
            logger.error(f"Error discovering new KOLs: {e}")
    
    def get_all_kol_wallets(self) -> Set[str]:
        """Get combined set of predefined and discovered KOL wallets"""
        return set(self.KOL_WALLETS.values()) | self.discovered_kols
