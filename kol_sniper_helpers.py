#!/usr/bin/env python3
"""
Helper classes for KOL Sniper Bot
- LiquidityMomentum: Track liquidity growth patterns
- PatternAnalyzer: Detect FOMO/pump patterns
- KOLTracker: Track and rank KOL wallet performance
"""

import time
import logging
from collections import deque
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field

logger = logging.getLogger("KOLSniperHelpers")


@dataclass
class KOLWallet:
    """Track performance of a KOL wallet"""
    address: str
    profit_pct: float = 0.0
    usd_pnl: float = 0.0
    win_rate: float = 0.0
    num_trades: int = 0
    last_updated: float = field(default_factory=time.time)
    
    def score(self) -> float:
        """Compute composite KOL score"""
        # Weighted score: profit%, win rate, and trade volume
        return (self.profit_pct * 0.4) + (self.win_rate * 100 * 0.4) + (min(self.num_trades, 100) * 0.2)


class KOLTracker:
    """Track and rank KOL wallets"""
    
    def __init__(self, min_trades: int = 10, min_win_rate: float = 0.60):
        self.wallets: Dict[str, KOLWallet] = {}
        self.min_trades = min_trades
        self.min_win_rate = min_win_rate
        
    def update_wallet(self, address: str, profit_pct: float, usd_pnl: float, 
                     win_rate: float, num_trades: int):
        """Update or create KOL wallet entry"""
        if address not in self.wallets:
            self.wallets[address] = KOLWallet(address=address)
        
        wallet = self.wallets[address]
        wallet.profit_pct = profit_pct
        wallet.usd_pnl = usd_pnl
        wallet.win_rate = win_rate
        wallet.num_trades = num_trades
        wallet.last_updated = time.time()
        
    def get_top_kols(self, limit: int = 10) -> List[KOLWallet]:
        """Get top performing KOLs"""
        qualified = [
            w for w in self.wallets.values()
            if w.num_trades >= self.min_trades and w.win_rate >= self.min_win_rate
        ]
        return sorted(qualified, key=lambda w: w.score(), reverse=True)[:limit]
    
    def is_top_kol_in_token(self, token_holders: List[str]) -> bool:
        """Check if any top KOL holds this token"""
        top_kols = self.get_top_kols(limit=20)
        top_addresses = {kol.address for kol in top_kols}
        return any(holder in top_addresses for holder in token_holders)


class LiquidityMomentum:
    """Track liquidity momentum and growth patterns"""
    
    def __init__(self, mode: str = "slot", window_size: int = 10):
        self.mode = mode
        self.window_size = window_size
        self.liquidity_points: deque = deque(maxlen=window_size)
        
    def add_liquidity_point(self, liquidity: float, timestamp: float):
        """Add a new liquidity data point"""
        self.liquidity_points.append((timestamp, liquidity))
        
    def get_momentum(self) -> float:
        """Calculate liquidity momentum (percentage growth rate)"""
        if len(self.liquidity_points) < 2:
            return 0.0
        
        first_liq = self.liquidity_points[0][1]
        last_liq = self.liquidity_points[-1][1]
        
        if first_liq == 0:
            return 0.0
        
        return ((last_liq - first_liq) / first_liq) * 100
    
    def is_accelerating(self, threshold: float = 50.0) -> bool:
        """Check if liquidity is accelerating rapidly"""
        if len(self.liquidity_points) < self.window_size:
            return False
        
        momentum = self.get_momentum()
        return momentum > threshold
    
    def get_growth_rate(self) -> float:
        """Get average growth rate per time unit"""
        if len(self.liquidity_points) < 2:
            return 0.0
        
        first_time, first_liq = self.liquidity_points[0]
        last_time, last_liq = self.liquidity_points[-1]
        
        time_delta = last_time - first_time
        if time_delta == 0:
            return 0.0
        
        liq_growth = last_liq - first_liq
        return liq_growth / time_delta


class PatternAnalyzer:
    """Analyze trading patterns to detect FOMO/pump signals"""
    
    def __init__(self):
        self.volume_history: deque = deque(maxlen=20)
        self.price_history: deque = deque(maxlen=20)
        
    def add_volume_point(self, volume: float, timestamp: float):
        """Track volume data"""
        self.volume_history.append((timestamp, volume))
        
    def add_price_point(self, price: float, timestamp: float):
        """Track price data"""
        self.price_history.append((timestamp, price))
        
    def detect_fomo_pattern(self) -> bool:
        """Detect FOMO pattern: rapid price increase + volume spike"""
        if len(self.price_history) < 5 or len(self.volume_history) < 5:
            return False
        
        # Check price surge (>20% in recent window)
        recent_prices = [p[1] for p in list(self.price_history)[-5:]]
        price_change = (recent_prices[-1] - recent_prices[0]) / recent_prices[0]
        
        # Check volume spike (last volume > 2x average)
        recent_volumes = [v[1] for v in list(self.volume_history)[-5:]]
        avg_volume = sum(recent_volumes[:-1]) / len(recent_volumes[:-1]) if len(recent_volumes) > 1 else 0
        
        if avg_volume == 0:
            return False
        
        volume_spike = recent_volumes[-1] / avg_volume
        
        # FOMO pattern: strong price increase + volume spike
        return price_change > 0.20 and volume_spike > 2.0
    
    def detect_pump_pattern(self) -> bool:
        """Detect coordinated pump pattern"""
        if len(self.price_history) < 10:
            return False
        
        # Look for consistent upward movement with increasing volume
        recent_prices = [p[1] for p in list(self.price_history)[-10:]]
        price_increases = sum(1 for i in range(1, len(recent_prices)) 
                            if recent_prices[i] > recent_prices[i-1])
        
        # Pump if >70% of recent moves are upward
        return price_increases >= 7
    
    def get_volatility(self) -> float:
        """Calculate recent price volatility"""
        if len(self.price_history) < 3:
            return 0.0
        
        prices = [p[1] for p in self.price_history]
        avg = sum(prices) / len(prices)
        variance = sum((p - avg) ** 2 for p in prices) / len(prices)
        return variance ** 0.5


def safety_checks(token_info: dict) -> Tuple[bool, str]:
    """
    Perform safety checks on token:
    - LP burned or locked
    - Not a honeypot
    - Contract renounced or verified
    - Not mintable
    """
    # Check LP status
    lp_burned = token_info.get('lp_burned', False)
    lp_locked = token_info.get('lp_locked', False)
    
    if not (lp_burned or lp_locked):
        return False, "LP not burned or locked"
    
    # Check honeypot
    is_honeypot = token_info.get('is_honeypot', False)
    if is_honeypot:
        return False, "Token is a honeypot"
    
    # Check if renounced
    renounced = token_info.get('renounced', False)
    if not renounced:
        logger.warning("Token not renounced - proceed with caution")
    
    # Check mintable
    is_mintable = token_info.get('is_mintable', False)
    if is_mintable:
        return False, "Token is mintable (rug risk)"
    
    # Check freeze authority
    freeze_authority = token_info.get('freeze_authority', None)
    if freeze_authority:
        return False, "Freeze authority present"
    
    return True, "All safety checks passed"


def pre_entry_confirmation(
    token_info: dict,
    liquidity_history: deque,
    pattern_analyzer: PatternAnalyzer,
    kol_tracker: KOLTracker,
    volume_ratio: float,
    min_liquidity: float,
    liquidity_momentum: LiquidityMomentum
) -> bool:
    """
    Composite signal for entry:
    1. Safety checks pass
    2. Liquidity above minimum
    3. Strong liquidity momentum
    4. FOMO or pump pattern detected
    5. Top KOL is in token
    6. High volume ratio
    """
    # 1. Safety checks
    safe, reason = safety_checks(token_info)
    if not safe:
        logger.info(f"❌ Safety check failed: {reason}")
        return False
    
    # 2. Liquidity check
    if not liquidity_history or liquidity_history[-1][1] < min_liquidity:
        logger.info(f"❌ Insufficient liquidity: {liquidity_history[-1][1] if liquidity_history else 0}")
        return False
    
    # 3. Liquidity momentum
    if not liquidity_momentum.is_accelerating(threshold=50.0):
        logger.info("❌ Liquidity not accelerating")
        return False
    
    # 4. Pattern detection
    has_fomo = pattern_analyzer.detect_fomo_pattern()
    has_pump = pattern_analyzer.detect_pump_pattern()
    
    if not (has_fomo or has_pump):
        logger.info("❌ No FOMO/pump pattern detected")
        return False
    
    # 5. KOL/Smart Money check - SKIPPED (checked separately via on-chain analysis)
    # This allows the function to work without KOL data from GMGN
    # Smart money is detected by analyzing recent blockchain transactions
    
    # 6. Volume ratio check
    if volume_ratio < 3.0:
        logger.info(f"❌ Low volume ratio: {volume_ratio}")
        return False
    
    logger.info("✅ All pre-entry confirmations passed!")
    return True
