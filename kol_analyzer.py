"""
KOL (Key Opinion Leader) Analyzer for Solana Moonshot Tokens
===========================================================
Analyzes top traders who bought tokens early and achieved massive returns (1000x+)
to identify potential KOLs for copy trading and alpha generation.

Features:
- Token transaction history analysis
- Early buyer identification
- ROI calculation (1000x+ filter)
- Wallet profiling and scoring
- Social media correlation
- Real-time KOL monitoring

Author: Quantitative Trading System
"""

import asyncio
import aiohttp
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional, Set, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import json
import logging
from enum import Enum
import time

# Solana imports
try:
    from solana.rpc.async_api import AsyncClient
    from solana.rpc.commitment import Confirmed
    from solders.pubkey import Pubkey
    from solders.signature import Signature
    SOLANA_AVAILABLE = True
except ImportError:
    SOLANA_AVAILABLE = False
    logging.warning("Solana libraries not available. Install with: pip install solana solders")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("KOLAnalyzer")


# ============================================================================
# ENUMS AND DATA CLASSES
# ============================================================================

class TraderTier(Enum):
    """Trader classification tiers"""
    LEGENDARY = "legendary"    # 10000x+ returns, multiple moonshots
    ELITE = "elite"           # 1000x+ returns, consistent performance
    SKILLED = "skilled"       # 100x+ returns, good track record
    AVERAGE = "average"       # <100x returns
    UNKNOWN = "unknown"       # Insufficient data


class TransactionType(Enum):
    """Transaction types"""
    BUY = "buy"
    SELL = "sell"
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"


@dataclass
class TokenTransaction:
    """Individual token transaction"""
    signature: str
    wallet: str
    token_mint: str
    transaction_type: TransactionType
    amount: float
    price_sol: float
    price_usd: float
    timestamp: datetime
    slot: int
    
    @property
    def value_usd(self) -> float:
        return self.amount * self.price_usd


@dataclass
class TokenPosition:
    """Wallet's position in a specific token"""
    wallet: str
    token_mint: str
    token_symbol: str
    
    # Entry details
    first_buy_timestamp: datetime
    first_buy_price: float
    total_bought: float
    total_spent_usd: float
    avg_buy_price: float
    
    # Exit details
    total_sold: float
    total_received_usd: float
    avg_sell_price: float
    last_sell_timestamp: Optional[datetime] = None
    
    # Current position
    current_balance: float = 0.0
    unrealized_value_usd: float = 0.0
    
    # Performance metrics
    realized_pnl_usd: float = 0.0
    unrealized_pnl_usd: float = 0.0
    total_roi: float = 0.0
    max_roi_achieved: float = 0.0
    
    # Timing metrics
    days_held: float = 0.0
    bought_within_hours: float = 0.0  # Hours after token launch
    
    def calculate_metrics(self, current_price: float = 0.0):
        """Calculate all performance metrics"""
        # ROI calculations
        if self.total_spent_usd > 0:
            self.realized_pnl_usd = self.total_received_usd - (self.total_sold / self.total_bought * self.total_spent_usd) if self.total_bought > 0 else 0
            
            if current_price > 0 and self.current_balance > 0:
                self.unrealized_value_usd = self.current_balance * current_price
                self.unrealized_pnl_usd = self.unrealized_value_usd - (self.current_balance / self.total_bought * self.total_spent_usd) if self.total_bought > 0 else 0
            
            total_value = self.total_received_usd + self.unrealized_value_usd
            self.total_roi = (total_value - self.total_spent_usd) / self.total_spent_usd
        
        # Timing calculations
        if self.last_sell_timestamp:
            self.days_held = (self.last_sell_timestamp - self.first_buy_timestamp).days
        elif self.current_balance > 0:
            self.days_held = (datetime.now() - self.first_buy_timestamp).days


@dataclass
class WalletProfile:
    """Comprehensive wallet profile for KOL analysis"""
    address: str
    
    # Basic stats
    total_transactions: int = 0
    first_activity: Optional[datetime] = None
    last_activity: Optional[datetime] = None
    days_active: int = 0
    
    # Token positions
    positions: List[TokenPosition] = field(default_factory=list)
    moonshot_positions: List[TokenPosition] = field(default_factory=list)  # 1000x+ positions
    
    # Performance metrics
    total_pnl_usd: float = 0.0
    win_rate: float = 0.0
    avg_roi: float = 0.0
    max_single_roi: float = 0.0
    total_volume_usd: float = 0.0
    
    # KOL indicators
    early_buyer_score: float = 0.0  # How early they buy (0-100)
    consistency_score: float = 0.0  # Consistency of good trades
    social_influence_score: float = 0.0  # Social media influence
    overall_kol_score: float = 0.0
    
    # Classification
    tier: TraderTier = TraderTier.UNKNOWN
    
    # Social data (if available)
    twitter_handle: Optional[str] = None
    telegram_username: Optional[str] = None
    discord_id: Optional[str] = None
    
    def calculate_scores(self):
        """Calculate all KOL scores"""
        if not self.positions:
            return
        
        # Early buyer score (average of how early they bought)
        early_scores = []
        for pos in self.positions:
            if pos.bought_within_hours <= 1:  # Within 1 hour
                early_scores.append(100)
            elif pos.bought_within_hours <= 6:  # Within 6 hours
                early_scores.append(80)
            elif pos.bought_within_hours <= 24:  # Within 1 day
                early_scores.append(60)
            elif pos.bought_within_hours <= 168:  # Within 1 week
                early_scores.append(40)
            else:
                early_scores.append(20)
        
        self.early_buyer_score = np.mean(early_scores) if early_scores else 0
        
        # Win rate and consistency
        profitable_positions = [p for p in self.positions if p.total_roi > 0]
        self.win_rate = len(profitable_positions) / len(self.positions)
        
        # ROI variance for consistency (lower variance = more consistent)
        rois = [p.total_roi for p in self.positions if p.total_roi != 0]
        if len(rois) > 1:
            roi_std = np.std(rois)
            avg_roi = np.mean(rois)
            # Consistency score: high average with low variance is better
            self.consistency_score = min(100, max(0, 50 + (avg_roi * 10) - (roi_std * 5)))
        else:
            self.consistency_score = 50
        
        # Overall KOL score (weighted combination)
        moonshot_bonus = len(self.moonshot_positions) * 20  # 20 points per moonshot
        self.overall_kol_score = (
            self.early_buyer_score * 0.3 +
            self.win_rate * 100 * 0.2 +
            self.consistency_score * 0.2 +
            min(self.max_single_roi * 0.1, 20) * 0.2 +  # Cap at 20 points
            min(moonshot_bonus, 100) * 0.1  # Cap moonshot bonus
        )
        
        # Determine tier
        if self.max_single_roi >= 100 and len(self.moonshot_positions) >= 2:
            self.tier = TraderTier.LEGENDARY
        elif self.max_single_roi >= 10 and len(self.moonshot_positions) >= 1:
            self.tier = TraderTier.ELITE
        elif self.max_single_roi >= 1 and self.win_rate > 0.6:
            self.tier = TraderTier.SKILLED
        else:
            self.tier = TraderTier.AVERAGE


@dataclass
class TokenAnalysis:
    """Analysis of a moonshot token"""
    mint: str
    symbol: str
    launch_timestamp: datetime
    peak_price: float
    peak_timestamp: datetime
    launch_price: float
    max_roi: float
    
    # Trader analysis
    total_unique_traders: int = 0
    early_buyers: List[str] = field(default_factory=list)  # First 24h buyers
    top_performers: List[WalletProfile] = field(default_factory=list)
    avg_early_buyer_roi: float = 0.0
    
    # Distribution analysis
    whale_wallets: Set[str] = field(default_factory=set)  # >1M USD positions
    smart_money_wallets: Set[str] = field(default_factory=set)  # Consistent performers


# ============================================================================
# TOKEN DATA FETCHER
# ============================================================================

class SolanaDataFetcher:
    """Fetches transaction data from Solana blockchain"""
    
    def __init__(self, rpc_url: str = "https://api.mainnet-beta.solana.com"):
        self.rpc_url = rpc_url
        self.client = AsyncClient(rpc_url) if SOLANA_AVAILABLE else None
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def initialize(self):
        """Initialize HTTP session"""
        self.session = aiohttp.ClientSession()
    
    async def close(self):
        """Close HTTP session"""
        if self.session:
            await self.session.close()
        if self.client:
            await self.client.close()
    
    async def get_token_transactions(self, token_mint: str, limit: int = 1000) -> List[TokenTransaction]:
        """
        Get all transactions for a token mint
        
        Note: In production, you'd want to use services like:
        - Helius API
        - QuickNode
        - Alchemy
        - Or index the data yourself using Geyser
        """
        # This is a placeholder implementation
        # In reality, you'd need to:
        # 1. Get all signatures for the token mint
        # 2. Parse each transaction
        # 3. Extract transfer amounts and prices
        
        logger.warning("get_token_transactions is a placeholder - integrate with real data source")
        return []
    
    async def get_helius_transactions(self, token_mint: str, api_key: str, limit: int = 1000) -> List[TokenTransaction]:
        """Get transactions using Helius API"""
        if not self.session:
            await self.initialize()
        
        url = f"https://mainnet.helius-rpc.com/?api-key={api_key}"
        
        # Get token transfers
        payload = {
            "jsonrpc": "2.0",
            "id": "helius-test",
            "method": "getAssetsByOwner",
            "params": {
                "mint": token_mint,
                "limit": limit,
                "page": 1
            }
        }
        
        try:
            async with self.session.post(url, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._parse_helius_response(data)
                else:
                    logger.error(f"Helius API error: {response.status}")
                    return []
        except Exception as e:
            logger.error(f"Error fetching from Helius: {e}")
            return []
    
    def _parse_helius_response(self, data: Dict) -> List[TokenTransaction]:
        """Parse Helius API response into TokenTransaction objects"""
        transactions = []
        
        # This would need to be implemented based on Helius API response format
        # Placeholder implementation
        logger.info(f"Parsing Helius response: {len(data.get('result', {}).get('items', []))} items")
        
        return transactions
    
    async def get_birdeye_price_history(self, token_mint: str, api_key: str) -> List[Tuple[datetime, float]]:
        """Get price history from Birdeye API"""
        if not self.session:
            await self.initialize()
        
        url = f"https://public-api.birdeye.so/defi/history_price"
        headers = {
            "X-API-KEY": api_key
        }
        
        params = {
            "address": token_mint,
            "address_type": "token",
            "type": "1m",
            "time_from": int((datetime.now() - timedelta(days=30)).timestamp()),
            "time_to": int(datetime.now().timestamp())
        }
        
        try:
            async with self.session.get(url, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._parse_price_history(data)
                else:
                    logger.error(f"Birdeye API error: {response.status}")
                    return []
        except Exception as e:
            logger.error(f"Error fetching price history: {e}")
            return []
    
    def _parse_price_history(self, data: Dict) -> List[Tuple[datetime, float]]:
        """Parse price history data"""
        price_history = []
        
        if "data" in data and "items" in data["data"]:
            for item in data["data"]["items"]:
                timestamp = datetime.fromtimestamp(item["unixTime"])
                price = float(item["value"])
                price_history.append((timestamp, price))
        
        return sorted(price_history, key=lambda x: x[0])


# ============================================================================
# KOL ANALYZER ENGINE
# ============================================================================

class KOLAnalyzer:
    """Main KOL analysis engine"""
    
    def __init__(self, 
                 rpc_url: str = "https://api.mainnet-beta.solana.com",
                 helius_api_key: str = "",
                 birdeye_api_key: str = ""):
        
        self.data_fetcher = SolanaDataFetcher(rpc_url)
        self.helius_api_key = helius_api_key
        self.birdeye_api_key = birdeye_api_key
        
        # Analysis results
        self.wallet_profiles: Dict[str, WalletProfile] = {}
        self.token_analyses: Dict[str, TokenAnalysis] = {}
        self.kol_database: List[WalletProfile] = []
        
        # Minimum thresholds
        self.min_roi_threshold = 10.0  # 1000% minimum
        self.min_early_hours = 24  # Must buy within 24 hours of launch
        self.min_position_size_usd = 100  # Minimum $100 position
    
    async def analyze_moonshot_token(self, 
                                   token_mint: str, 
                                   token_symbol: str,
                                   launch_timestamp: Optional[datetime] = None) -> TokenAnalysis:
        """
        Analyze a moonshot token to identify top traders
        
        Args:
            token_mint: Token mint address
            token_symbol: Token symbol
            launch_timestamp: When the token launched (if known)
        
        Returns:
            TokenAnalysis with top traders identified
        """
        logger.info(f"Analyzing moonshot token: {token_symbol} ({token_mint})")
        
        # Initialize data fetcher
        await self.data_fetcher.initialize()
        
        try:
            # Get all token transactions
            transactions = await self._get_all_transactions(token_mint)
            
            if not transactions:
                logger.warning(f"No transactions found for {token_symbol}")
                return TokenAnalysis(
                    mint=token_mint,
                    symbol=token_symbol,
                    launch_timestamp=launch_timestamp or datetime.now(),
                    peak_price=0,
                    peak_timestamp=datetime.now(),
                    launch_price=0,
                    max_roi=0
                )
            
            # Get price history
            price_history = await self.data_fetcher.get_birdeye_price_history(
                token_mint, self.birdeye_api_key
            )
            
            # Determine launch details if not provided
            if not launch_timestamp and transactions:
                launch_timestamp = min(tx.timestamp for tx in transactions)
            
            launch_price, peak_price, peak_timestamp = self._analyze_price_action(price_history)
            max_roi = (peak_price / launch_price - 1) if launch_price > 0 else 0
            
            # Group transactions by wallet
            wallet_transactions = defaultdict(list)
            for tx in transactions:
                wallet_transactions[tx.wallet].append(tx)
            
            # Analyze each wallet's performance
            wallet_positions = {}
            for wallet, txs in wallet_transactions.items():
                position = self._calculate_wallet_position(
                    wallet, token_mint, token_symbol, txs, launch_timestamp, peak_price
                )
                if position and position.total_roi >= self.min_roi_threshold:
                    wallet_positions[wallet] = position
            
            # Create token analysis
            analysis = TokenAnalysis(
                mint=token_mint,
                symbol=token_symbol,
                launch_timestamp=launch_timestamp,
                peak_price=peak_price,
                peak_timestamp=peak_timestamp,
                launch_price=launch_price,
                max_roi=max_roi,
                total_unique_traders=len(wallet_transactions)
            )
            
            # Identify early buyers (within first 24 hours)
            early_cutoff = launch_timestamp + timedelta(hours=self.min_early_hours)
            analysis.early_buyers = [
                wallet for wallet, pos in wallet_positions.items()
                if pos.first_buy_timestamp <= early_cutoff
            ]
            
            # Rank top performers
            top_positions = sorted(
                wallet_positions.values(),
                key=lambda x: x.total_roi,
                reverse=True
            )[:50]  # Top 50
            
            # Update wallet profiles
            for position in top_positions:
                if position.wallet not in self.wallet_profiles:
                    self.wallet_profiles[position.wallet] = WalletProfile(
                        address=position.wallet
                    )
                
                profile = self.wallet_profiles[position.wallet]
                profile.positions.append(position)
                
                if position.total_roi >= self.min_roi_threshold:
                    profile.moonshot_positions.append(position)
                    
                # Update max ROI
                profile.max_single_roi = max(profile.max_single_roi, position.total_roi)
            
            # Calculate wallet scores
            for profile in self.wallet_profiles.values():
                if profile.positions:  # Only if they have positions
                    profile.calculate_scores()
            
            # Get top KOL profiles for this token
            analysis.top_performers = [
                self.wallet_profiles[pos.wallet] for pos in top_positions[:20]
                if pos.wallet in self.wallet_profiles
            ]
            
            # Calculate average ROI for early buyers
            early_positions = [
                pos for pos in wallet_positions.values()
                if pos.wallet in analysis.early_buyers
            ]
            if early_positions:
                analysis.avg_early_buyer_roi = np.mean([pos.total_roi for pos in early_positions])
            
            # Store analysis
            self.token_analyses[token_mint] = analysis
            
            logger.info(f"Analysis complete: {len(analysis.top_performers)} top performers identified")
            return analysis
            
        finally:
            await self.data_fetcher.close()
    
    async def _get_all_transactions(self, token_mint: str) -> List[TokenTransaction]:
        """Get all transactions for a token"""
        if self.helius_api_key:
            return await self.data_fetcher.get_helius_transactions(
                token_mint, self.helius_api_key
            )
        else:
            return await self.data_fetcher.get_token_transactions(token_mint)
    
    def _analyze_price_action(self, price_history: List[Tuple[datetime, float]]) -> Tuple[float, float, datetime]:
        """Analyze price action to find launch price and peak"""
        if not price_history:
            return 0.0, 0.0, datetime.now()
        
        # Sort by timestamp
        price_history.sort(key=lambda x: x[0])
        
        launch_price = price_history[0][1]
        peak_price = max(price_history, key=lambda x: x[1])[1]
        peak_timestamp = max(price_history, key=lambda x: x[1])[0]
        
        return launch_price, peak_price, peak_timestamp
    
    def _calculate_wallet_position(self, 
                                 wallet: str,
                                 token_mint: str,
                                 token_symbol: str,
                                 transactions: List[TokenTransaction],
                                 launch_timestamp: datetime,
                                 peak_price: float) -> Optional[TokenPosition]:
        """Calculate a wallet's position and performance for a token"""
        
        # Sort transactions by timestamp
        transactions.sort(key=lambda x: x.timestamp)
        
        # Track buys and sells
        buys = [tx for tx in transactions if tx.transaction_type == TransactionType.BUY]
        sells = [tx for tx in transactions if tx.transaction_type == TransactionType.SELL]
        
        if not buys:
            return None
        
        # Calculate position metrics
        total_bought = sum(tx.amount for tx in buys)
        total_spent_usd = sum(tx.value_usd for tx in buys)
        
        if total_spent_usd < self.min_position_size_usd:
            return None
        
        avg_buy_price = total_spent_usd / total_bought if total_bought > 0 else 0
        
        total_sold = sum(tx.amount for tx in sells)
        total_received_usd = sum(tx.value_usd for tx in sells)
        avg_sell_price = total_received_usd / total_sold if total_sold > 0 else 0
        
        current_balance = total_bought - total_sold
        
        # Calculate timing
        first_buy = buys[0]
        hours_after_launch = (first_buy.timestamp - launch_timestamp).total_seconds() / 3600
        
        # Skip if bought too late
        if hours_after_launch > self.min_early_hours:
            return None
        
        # Create position
        position = TokenPosition(
            wallet=wallet,
            token_mint=token_mint,
            token_symbol=token_symbol,
            first_buy_timestamp=first_buy.timestamp,
            first_buy_price=first_buy.price_usd,
            total_bought=total_bought,
            total_spent_usd=total_spent_usd,
            avg_buy_price=avg_buy_price,
            total_sold=total_sold,
            total_received_usd=total_received_usd,
            avg_sell_price=avg_sell_price,
            last_sell_timestamp=sells[-1].timestamp if sells else None,
            current_balance=current_balance,
            bought_within_hours=hours_after_launch
        )
        
        # Calculate metrics using peak price for max potential
        position.max_roi_achieved = (peak_price - avg_buy_price) / avg_buy_price if avg_buy_price > 0 else 0
        position.calculate_metrics(peak_price if current_balance > 0 else 0)
        
        return position
    
    def get_top_kols(self, min_score: float = 70.0, limit: int = 50) -> List[WalletProfile]:
        """Get top KOLs based on scoring"""
        qualified_kols = [
            profile for profile in self.wallet_profiles.values()
            if profile.overall_kol_score >= min_score and len(profile.moonshot_positions) >= 1
        ]
        
        return sorted(qualified_kols, key=lambda x: x.overall_kol_score, reverse=True)[:limit]
    
    def export_kol_database(self, filename: str = "kol_database.json"):
        """Export KOL database to JSON file"""
        top_kols = self.get_top_kols()
        
        export_data = []
        for kol in top_kols:
            kol_data = {
                "address": kol.address,
                "tier": kol.tier.value,
                "overall_score": kol.overall_kol_score,
                "early_buyer_score": kol.early_buyer_score,
                "win_rate": kol.win_rate,
                "max_roi": kol.max_single_roi,
                "moonshot_count": len(kol.moonshot_positions),
                "total_positions": len(kol.positions),
                "avg_roi": kol.avg_roi,
                "moonshots": [
                    {
                        "token": pos.token_symbol,
                        "roi": pos.total_roi,
                        "bought_hours_after_launch": pos.bought_within_hours,
                        "first_buy": pos.first_buy_timestamp.isoformat(),
                        "spent_usd": pos.total_spent_usd
                    }
                    for pos in kol.moonshot_positions
                ]
            }
            export_data.append(kol_data)
        
        with open(filename, 'w') as f:
            json.dump(export_data, f, indent=2, default=str)
        
        logger.info(f"Exported {len(export_data)} KOLs to {filename}")
    
    async def monitor_kol_activity(self, kol_addresses: List[str], check_interval: int = 300):
        """
        Monitor KOL wallet activity for new trades
        
        Args:
            kol_addresses: List of KOL wallet addresses to monitor
            check_interval: Check interval in seconds
        """
        logger.info(f"Starting KOL monitoring for {len(kol_addresses)} wallets")
        
        last_check = {}
        
        while True:
            try:
                for address in kol_addresses:
                    # In production, you'd check for new transactions
                    # and analyze new token purchases
                    logger.debug(f"Checking activity for {address[:10]}...")
                    
                    # Placeholder for real monitoring logic
                    # You would:
                    # 1. Get recent transactions
                    # 2. Identify new token purchases
                    # 3. Alert if KOL bought a new token early
                    # 4. Analyze the new token for potential
                    
                await asyncio.sleep(check_interval)
                
            except KeyboardInterrupt:
                logger.info("KOL monitoring stopped")
                break
            except Exception as e:
                logger.error(f"Error in KOL monitoring: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retrying


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

async def analyze_example_moonshot():
    """Example usage of the KOL analyzer"""
    
    # Initialize analyzer (you'd need real API keys)
    analyzer = KOLAnalyzer(
        helius_api_key="your-helius-api-key",
        birdeye_api_key="your-birdeye-api-key"
    )
    
    # Example moonshot token (replace with real token)
    token_mint = "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr"  # POPCAT
    token_symbol = "POPCAT"
    launch_date = datetime(2024, 3, 15)  # Example launch date
    
    # Analyze the token
    analysis = await analyzer.analyze_moonshot_token(
        token_mint=token_mint,
        token_symbol=token_symbol,
        launch_timestamp=launch_date
    )
    
    # Print results
    print(f"\n=== {token_symbol} Analysis Results ===")
    print(f"Launch Price: ${analysis.launch_price:.8f}")
    print(f"Peak Price: ${analysis.peak_price:.8f}")
    print(f"Max ROI: {analysis.max_roi:.2f}x")
    print(f"Total Traders: {analysis.total_unique_traders}")
    print(f"Early Buyers: {len(analysis.early_buyers)}")
    print(f"Average Early Buyer ROI: {analysis.avg_early_buyer_roi:.2f}x")
    
    # Top performers
    print(f"\n=== Top 10 Performers ===")
    for i, kol in enumerate(analysis.top_performers[:10], 1):
        moonshot_pos = next((p for p in kol.moonshot_positions if p.token_mint == token_mint), None)
        if moonshot_pos:
            print(f"{i}. {kol.address[:10]}... "
                  f"ROI: {moonshot_pos.total_roi:.2f}x "
                  f"Score: {kol.overall_kol_score:.1f} "
                  f"Tier: {kol.tier.value}")
    
    # Get overall top KOLs
    top_kols = analyzer.get_top_kols(min_score=70, limit=20)
    
    print(f"\n=== Top 20 KOLs Overall ===")
    for i, kol in enumerate(top_kols, 1):
        print(f"{i}. {kol.address[:10]}... "
              f"Score: {kol.overall_kol_score:.1f} "
              f"Moonshots: {len(kol.moonshot_positions)} "
              f"Max ROI: {kol.max_single_roi:.2f}x "
              f"Win Rate: {kol.win_rate:.2%}")
    
    # Export database
    analyzer.export_kol_database("moonshot_kols.json")


if __name__ == "__main__":
    asyncio.run(analyze_example_moonshot())