import asyncio
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime, timedelta
import time

from api_client import BlockchainAPIClient

logger = logging.getLogger("liquidity_flow")

@dataclass
class FlowSnapshot:
    """Snapshot of liquidity at a point in time"""
    timestamp: float
    total_liquidity: Decimal
    base_amount: Decimal
    quote_amount: Decimal
    inflow_rate: Decimal  # SOL per minute

@dataclass
class FlowAnalysis:
    """Analysis of liquidity flow"""
    current_inflow_rate: Decimal  # Current rate (SOL/min)
    avg_inflow_5min: Decimal
    avg_inflow_15min: Decimal
    is_reversing: bool
    reversal_strength: float  # 0-1, higher = stronger reversal
    recommendation: str  # 'hold', 'prepare_to_sell', 'sell_now'
    reason: str

class LiquidityFlowAnalyzer:
    """
    Monitors SOL inflow to pools and detects when flow begins to reverse
    Triggers sell signals to exit before dumps
    """
    
    def __init__(self, config, api_client: BlockchainAPIClient):
        self.config = config
        self.api_client = api_client
        
        # Track flow history for each pool
        self.flow_history: Dict[str, List[FlowSnapshot]] = {}
        
        # Configuration for HIGH-FREQUENCY meme coin sniping
        self.snapshot_interval = 2  # Take snapshot every 2 seconds
        self.history_window = 60  # Keep only 1 minute of history (fast moving)
        self.reversal_threshold = -0.3  # 30% drop = reversal (more sensitive)
        self.peak_detection_window = 10  # Last 10 seconds for peak detection
        
    async def take_snapshot(self, pool_id: str) -> Optional[FlowSnapshot]:
        """Take a snapshot of current pool liquidity"""
        try:
            pool = await self.api_client.get_raydium_pool(pool_id)
            if not pool:
                return None
            
            # Calculate inflow rate if we have previous snapshot
            inflow_rate = Decimal('0')
            if pool_id in self.flow_history and self.flow_history[pool_id]:
                last_snapshot = self.flow_history[pool_id][-1]
                time_diff = time.time() - last_snapshot.timestamp
                
                if time_diff > 0:
                    current_liquidity = Decimal(pool.quote_amount)
                    liquidity_change = current_liquidity - last_snapshot.total_liquidity
                    inflow_rate = (liquidity_change / Decimal(str(time_diff))) * 60  # Per minute
            
            snapshot = FlowSnapshot(
                timestamp=time.time(),
                total_liquidity=Decimal(pool.quote_amount),
                base_amount=Decimal(pool.base_amount),
                quote_amount=Decimal(pool.quote_amount),
                inflow_rate=inflow_rate
            )
            
            # Add to history
            if pool_id not in self.flow_history:
                self.flow_history[pool_id] = []
            
            self.flow_history[pool_id].append(snapshot)
            
            # Clean old snapshots
            cutoff_time = time.time() - self.history_window
            self.flow_history[pool_id] = [
                s for s in self.flow_history[pool_id]
                if s.timestamp > cutoff_time
            ]
            
            return snapshot
            
        except Exception as e:
            logger.error(f"Error taking snapshot for pool {pool_id}: {e}")
            return None
    
    def analyze_flow(self, pool_id: str) -> Optional[FlowAnalysis]:
        """Analyze liquidity flow and detect reversals in REAL-TIME"""
        try:
            if pool_id not in self.flow_history or len(self.flow_history[pool_id]) < 5:
                return None
            
            history = self.flow_history[pool_id]
            current_time = time.time()
            
            # Get recent snapshots (FAST windows for meme coins)
            recent_10sec = [s for s in history if current_time - s.timestamp <= 10]
            recent_30sec = [s for s in history if current_time - s.timestamp <= 30]
            recent_60sec = [s for s in history if current_time - s.timestamp <= 60]
            
            if not recent_10sec or not recent_30sec:
                return None
            
            # Calculate average inflow rates (per SECOND now, not minute)
            current_inflow = history[-1].inflow_rate
            
            avg_10sec = sum(s.inflow_rate for s in recent_10sec) / len(recent_10sec)
            avg_30sec = sum(s.inflow_rate for s in recent_30sec) / len(recent_30sec)
            avg_60sec = sum(s.inflow_rate for s in recent_60sec) / len(recent_60sec) if recent_60sec else avg_30sec
            
            # DETECT PARABOLA PEAK (critical for meme coins)
            is_reversing = False
            reversal_strength = 0.0
            recommendation = 'hold'
            reason = "Accumulation phase"
            
            # Check if we're at or past peak
            peak_snapshots = recent_10sec[-5:] if len(recent_10sec) >= 5 else recent_10sec
            if len(peak_snapshots) >= 3:
                # Check for deceleration (first derivative declining)
                inflow_rates = [float(s.inflow_rate) for s in peak_snapshots]
                
                # Calculate rate of change (acceleration)
                if len(inflow_rates) >= 3:
                    recent_acceleration = inflow_rates[-1] - inflow_rates[-2]
                    prev_acceleration = inflow_rates[-2] - inflow_rates[-3]
                    
                    # Peak detected: acceleration is slowing or reversing
                    if recent_acceleration < prev_acceleration and recent_acceleration < 0:
                        is_reversing = True
                        reversal_strength = 0.9
                        recommendation = 'sell_now'
                        reason = f"PEAK DETECTED: Inflow decelerating ({recent_acceleration:.1f} SOL/s)"
            
            # Fast reversal patterns for meme coins
            if avg_30sec > 0:  # Was accumulating
                # Calculate % change from 30sec average
                flow_change_pct = float((current_inflow - avg_30sec) / avg_30sec)
                
                if flow_change_pct < self.reversal_threshold:
                    is_reversing = True
                    reversal_strength = min(1.0, abs(flow_change_pct))
                    
                    if current_inflow < 0:
                        recommendation = 'sell_now'
                        reason = f"Inflow REVERSED: Now -{float(abs(current_inflow)):.1f} SOL/min"
                    elif flow_change_pct < -0.5:
                        recommendation = 'sell_now'
                        reason = f"Rapid slowdown: {flow_change_pct*100:.0f}% drop in 30sec"
                    else:
                        recommendation = 'prepare_to_sell'
                        reason = f"Momentum fading: {flow_change_pct*100:.0f}% decline"
            
            # Check for massive dump (>10 SOL/s outflow)
            if current_inflow < -600:  # -600 SOL/min = -10 SOL/sec
                is_reversing = True
                reversal_strength = 1.0
                recommendation = 'sell_now'
                reason = f"DUMP DETECTED: {float(current_inflow):.0f} SOL/min outflow"
            
            # Check last 3 snapshots (6 seconds) for trend
            if len(history) >= 3:
                last_3_rates = [s.inflow_rate for s in history[-3:]]
                if all(rate < last_3_rates[i-1] for i, rate in enumerate(last_3_rates[1:], 1)):
                    # Declining for 3 consecutive periods
                    is_reversing = True
                    reversal_strength = max(reversal_strength, 0.8)
                    if recommendation != 'sell_now':
                        recommendation = 'sell_now'
                        reason = "Consistent decline detected (6sec)"
            
            # BONUS: Detect if liquidity peaked and is now stable (top of parabola)
            if len(recent_30sec) >= 10:
                max_liquidity = max(s.total_liquidity for s in recent_30sec)
                current_liquidity = history[-1].total_liquidity
                
                # If current liquidity is >98% of recent max, we might be at peak
                if current_liquidity >= max_liquidity * Decimal('0.98'):
                    # Check if inflow is slowing
                    if float(current_inflow) < float(avg_10sec) * 0.7:
                        is_reversing = True
                        reversal_strength = max(reversal_strength, 0.85)
                        recommendation = 'sell_now'
                        reason = "At peak liquidity with slowing inflow - EXIT NOW"
            
            analysis = FlowAnalysis(
                current_inflow_rate=current_inflow,
                avg_inflow_5min=avg_10sec,  # Now 10sec avg
                avg_inflow_15min=avg_30sec,  # Now 30sec avg
                is_reversing=is_reversing,
                reversal_strength=reversal_strength,
                recommendation=recommendation,
                reason=reason
            )
            
            if is_reversing:
                logger.warning(f"Flow reversal detected for pool {pool_id}: {reason}")
            
            return analysis
            
        except Exception as e:
            logger.error(f"Error analyzing flow for pool {pool_id}: {e}")
            return None
    
    async def monitor_position(self, pool_id: str, check_interval: int = 2) -> FlowAnalysis:
        """
        Continuously monitor a position and return when action is needed
        """
        try:
            logger.info(f"Starting flow monitoring for pool {pool_id}")
            
            while True:
                # Take snapshot
                snapshot = await self.take_snapshot(pool_id)
                
                if snapshot:
                    # Analyze flow
                    analysis = self.analyze_flow(pool_id)
                    
                    if analysis:
                        logger.info(
                            f"Pool {pool_id}: "
                            f"Inflow: {float(analysis.current_inflow_rate):.1f} SOL/min, "
                            f"10s avg: {float(analysis.avg_inflow_5min):.1f}, "
                            f"30s avg: {float(analysis.avg_inflow_15min):.1f}"
                        )
                        
                        # Return immediately if action needed
                        if analysis.recommendation in ['sell_now', 'prepare_to_sell']:
                            logger.critical(
                                f"🚨 FLOW ALERT for {pool_id}: "
                                f"{analysis.recommendation.upper()} - {analysis.reason}"
                            )
                            return analysis
                
                # Wait before next check
                await asyncio.sleep(check_interval)
                
        except Exception as e:
            logger.error(f"Error monitoring position: {e}")
            return None
    
    def get_flow_summary(self, pool_id: str) -> Optional[Dict]:
        """Get a summary of flow statistics"""
        try:
            if pool_id not in self.flow_history or not self.flow_history[pool_id]:
                return None
            
            history = self.flow_history[pool_id]
            current = history[-1]
            
            # Calculate statistics
            total_change = current.total_liquidity - history[0].total_liquidity
            time_span = current.timestamp - history[0].timestamp
            avg_rate = (total_change / Decimal(str(time_span))) * 60 if time_span > 0 else Decimal('0')
            
            positive_flows = sum(1 for s in history if s.inflow_rate > 0)
            negative_flows = sum(1 for s in history if s.inflow_rate < 0)
            
            return {
                'pool_id': pool_id,
                'current_liquidity': float(current.total_liquidity),
                'liquidity_change': float(total_change),
                'avg_flow_rate': float(avg_rate),
                'positive_periods': positive_flows,
                'negative_periods': negative_flows,
                'snapshots_count': len(history),
                'monitoring_duration_min': time_span / 60
            }
            
        except Exception as e:
            logger.error(f"Error getting flow summary: {e}")
            return None
