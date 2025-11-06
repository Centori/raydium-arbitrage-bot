"""
Solana Perpetuals Trading Strategy with Advanced ML
====================================================
Combines:
- Markov Chains for Support/Resistance detection
- Q-Learning with VaR-constrained rewards
- LSTM for temporal pattern recognition
- Kelly Criterion for dynamic leverage
- Order book microstructure analysis
- Jito bundle execution for MEV protection

Author: Quantitative Trading System
"""

import asyncio
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import deque
import json
import logging
from enum import Enum

# Deep learning
try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    logging.warning("PyTorch not available. Install with: pip install torch")

# Solana imports
try:
    from solana.rpc.async_api import AsyncClient
    from solana.rpc.commitment import Confirmed
    from solders.pubkey import Pubkey
    from solders.keypair import Keypair
    SOLANA_AVAILABLE = True
except ImportError:
    SOLANA_AVAILABLE = False
    logging.warning("Solana libraries not available. Install with: pip install solana solders")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("PerpsStrategy")


# ============================================================================
# ENUMS AND DATA CLASSES
# ============================================================================

class MarketRegime(Enum):
    """Market regime states"""
    UPTREND = "uptrend"
    DOWNTREND = "downtrend"
    RANGING = "ranging"


class VolatilityRegime(Enum):
    """Volatility states"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class LiquidityRegime(Enum):
    """Liquidity states"""
    THIN = "thin"
    NORMAL = "normal"
    THICK = "thick"


class OrderFlow(Enum):
    """Order flow direction"""
    BUYER_PRESSURE = "buyer_pressure"
    NEUTRAL = "neutral"
    SELLER_PRESSURE = "seller_pressure"


class Action(Enum):
    """Trading actions"""
    LONG_ENTRY = 0
    SHORT_ENTRY = 1
    INCREASE_LONG = 2
    INCREASE_SHORT = 3
    REDUCE_LONG = 4
    REDUCE_SHORT = 5
    CLOSE_ALL = 6
    HOLD = 7


@dataclass
class OrderBookSnapshot:
    """Level 2 order book snapshot"""
    timestamp: float
    bids: List[Tuple[float, float]]  # [(price, size), ...]
    asks: List[Tuple[float, float]]
    mid_price: float
    spread: float
    
    def __post_init__(self):
        if not self.mid_price and self.bids and self.asks:
            self.mid_price = (self.bids[0][0] + self.asks[0][0]) / 2
        if not self.spread and self.bids and self.asks:
            self.spread = self.asks[0][0] - self.bids[0][0]


@dataclass
class Trade:
    """Individual trade execution"""
    timestamp: float
    price: float
    size: float
    is_buyer: bool  # True if buyer initiated (aggressive buy)


@dataclass
class MarketState:
    """Complete market state for ML models"""
    price_regime: MarketRegime
    volatility: VolatilityRegime
    liquidity: LiquidityRegime
    order_flow: OrderFlow
    
    def to_id(self) -> int:
        """Convert to discrete state ID (0-80)"""
        regimes = [MarketRegime, VolatilityRegime, LiquidityRegime, OrderFlow]
        multipliers = [27, 9, 3, 1]  # 3*3*3*3 = 81 states
        
        state_id = 0
        for regime_type, multiplier in zip(regimes, multipliers):
            enum_value = getattr(self, regime_type.__name__.lower().replace('regime', '').replace('_', ''))
            if hasattr(enum_value, 'name'):
                state_id += list(regime_type).index(enum_value) * multiplier
            else:
                state_id += list(regime_type).index(enum_value) * multiplier
        
        return state_id
    
    @classmethod
    def from_id(cls, state_id: int) -> 'MarketState':
        """Reconstruct state from ID"""
        regimes = [MarketRegime, VolatilityRegime, LiquidityRegime, OrderFlow]
        multipliers = [27, 9, 3, 1]
        
        indices = []
        remaining = state_id
        for mult in multipliers:
            indices.append(remaining // mult)
            remaining %= mult
        
        return cls(
            price_regime=list(MarketRegime)[indices[0]],
            volatility=list(VolatilityRegime)[indices[1]],
            liquidity=list(LiquidityRegime)[indices[2]],
            order_flow=list(OrderFlow)[indices[3]]
        )


@dataclass
class Position:
    """Current trading position"""
    size: float = 0.0  # Positive = long, negative = short
    entry_price: float = 0.0
    leverage: float = 1.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    margin_used: float = 0.0
    
    def update_unrealized_pnl(self, current_price: float):
        """Update unrealized P&L"""
        if self.size != 0:
            self.unrealized_pnl = self.size * (current_price - self.entry_price)


@dataclass
class RiskMetrics:
    """Real-time risk metrics"""
    var_99_1day: float = 0.0
    cvar: float = 0.0
    current_drawdown: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0


# ============================================================================
# ORDER BOOK MICROSTRUCTURE FEATURES
# ============================================================================

class MicrostructureAnalyzer:
    """Compute order book microstructure features"""
    
    @staticmethod
    def compute_ofi(ob: OrderBookSnapshot, levels: int = 5) -> float:
        """Order Flow Imbalance"""
        bid_vol = sum(size for _, size in ob.bids[:levels])
        ask_vol = sum(size for _, size in ob.asks[:levels])
        
        if bid_vol + ask_vol == 0:
            return 0.0
        
        return (bid_vol - ask_vol) / (bid_vol + ask_vol)
    
    @staticmethod
    def compute_microprice(ob: OrderBookSnapshot) -> float:
        """Volume-weighted microprice"""
        if not ob.bids or not ob.asks:
            return ob.mid_price
        
        bid_price, bid_vol = ob.bids[0]
        ask_price, ask_vol = ob.asks[0]
        
        if bid_vol + ask_vol == 0:
            return ob.mid_price
        
        return (bid_price * ask_vol + ask_price * bid_vol) / (bid_vol + ask_vol)
    
    @staticmethod
    def compute_book_pressure(ob: OrderBookSnapshot, levels: int = 10) -> float:
        """Cumulative volume difference"""
        bid_vol = sum(size for _, size in ob.bids[:levels])
        ask_vol = sum(size for _, size in ob.asks[:levels])
        
        return bid_vol - ask_vol
    
    @staticmethod
    def compute_kyle_lambda(trades: List[Trade], window: timedelta) -> float:
        """Kyle's lambda (price impact per unit volume)"""
        if len(trades) < 2:
            return 0.0
        
        current_time = trades[-1].timestamp
        recent_trades = [t for t in trades if current_time - t.timestamp <= window.total_seconds()]
        
        if len(recent_trades) < 2:
            return 0.0
        
        # Signed volume (positive for buys, negative for sells)
        signed_volumes = [t.size if t.is_buyer else -t.size for t in recent_trades]
        price_changes = [recent_trades[i].price - recent_trades[i-1].price 
                        for i in range(1, len(recent_trades))]
        
        if not signed_volumes[:-1] or not price_changes:
            return 0.0
        
        # Simple regression: price_change = lambda * signed_volume
        volumes_array = np.array(signed_volumes[:-1])
        prices_array = np.array(price_changes)
        
        if np.sum(volumes_array ** 2) == 0:
            return 0.0
        
        lambda_estimate = np.sum(volumes_array * prices_array) / np.sum(volumes_array ** 2)
        return lambda_estimate
    
    @staticmethod
    def compute_all_features(ob: OrderBookSnapshot, trades: List[Trade]) -> Dict[str, float]:
        """Compute all microstructure features"""
        return {
            'ofi_5': MicrostructureAnalyzer.compute_ofi(ob, 5),
            'ofi_10': MicrostructureAnalyzer.compute_ofi(ob, 10),
            'ofi_20': MicrostructureAnalyzer.compute_ofi(ob, 20),
            'microprice': MicrostructureAnalyzer.compute_microprice(ob),
            'mid_price': ob.mid_price,
            'spread': ob.spread,
            'relative_spread': ob.spread / ob.mid_price if ob.mid_price > 0 else 0,
            'book_pressure_5': MicrostructureAnalyzer.compute_book_pressure(ob, 5),
            'book_pressure_10': MicrostructureAnalyzer.compute_book_pressure(ob, 10),
            'kyle_lambda': MicrostructureAnalyzer.compute_kyle_lambda(trades, timedelta(seconds=60))
        }


# ============================================================================
# MARKOV CHAIN FOR SUPPORT/RESISTANCE
# ============================================================================

class MarkovChain:
    """Markov Chain for regime detection and S/R levels"""
    
    def __init__(self, num_states: int = 81, window_size: int = 10000):
        self.num_states = num_states
        self.window_size = window_size
        self.transition_matrix = np.zeros((num_states, num_states))
        self.state_counts = np.zeros(num_states)
        self.state_history = deque(maxlen=window_size)
        
    def update(self, prev_state: int, curr_state: int):
        """Update transition matrix with new observation"""
        self.transition_matrix[prev_state, curr_state] += 1
        self.state_counts[curr_state] += 1
        self.state_history.append(curr_state)
    
    def get_transition_probabilities(self) -> np.ndarray:
        """Get normalized transition probability matrix"""
        # Avoid division by zero
        row_sums = self.transition_matrix.sum(axis=1, keepdims=True)
        row_sums[row_sums == 0] = 1
        return self.transition_matrix / row_sums
    
    def get_stationary_distribution(self) -> np.ndarray:
        """Compute stationary distribution (long-run probabilities)"""
        trans_prob = self.get_transition_probabilities()
        
        # Find eigenvector for eigenvalue 1
        eigenvalues, eigenvectors = np.linalg.eig(trans_prob.T)
        
        # Find index of eigenvalue closest to 1
        idx = np.argmin(np.abs(eigenvalues - 1.0))
        stationary = np.real(eigenvectors[:, idx])
        
        # Normalize
        stationary = stationary / np.sum(stationary)
        return stationary
    
    def identify_persistent_states(self, threshold: float = 0.7) -> List[int]:
        """Identify states with high self-transition probability (S/R levels)"""
        trans_prob = self.get_transition_probabilities()
        diagonal = np.diag(trans_prob)
        
        persistent_states = np.where(diagonal > threshold)[0]
        return persistent_states.tolist()
    
    def get_state_entropy(self, state: int) -> float:
        """Compute entropy of transitions from a state"""
        trans_prob = self.get_transition_probabilities()
        probs = trans_prob[state]
        
        # Filter out zero probabilities
        probs = probs[probs > 0]
        
        if len(probs) == 0:
            return 0.0
        
        return -np.sum(probs * np.log2(probs))


# ============================================================================
# LSTM NETWORK
# ============================================================================

if TORCH_AVAILABLE:
    class LSTMPredictor(nn.Module):
        """LSTM for temporal pattern recognition and Q-value refinement"""
        
        def __init__(self, input_size: int = 45, hidden_size_1: int = 128, 
                     hidden_size_2: int = 64, output_size: int = 9):
            super(LSTMPredictor, self).__init__()
            
            self.lstm1 = nn.LSTM(input_size, hidden_size_1, batch_first=True)
            self.dropout1 = nn.Dropout(0.3)
            
            self.lstm2 = nn.LSTM(hidden_size_1, hidden_size_2, batch_first=True)
            self.dropout2 = nn.Dropout(0.2)
            
            self.fc1 = nn.Linear(hidden_size_2, 32)
            self.bn1 = nn.BatchNorm1d(32)
            self.relu = nn.ReLU()
            
            # Two heads: Q-values and confidence
            self.q_head = nn.Linear(32, 8)  # 8 actions
            self.confidence_head = nn.Linear(32, 1)  # Confidence score
            
        def forward(self, x, hidden=None):
            """Forward pass
            
            Args:
                x: Input tensor of shape (batch, seq_len, features)
                hidden: Optional hidden state tuple
                
            Returns:
                q_values: Refined Q-values for each action
                confidence: Confidence score (0-1)
            """
            # LSTM layers
            out1, hidden1 = self.lstm1(x, hidden[0] if hidden else None)
            out1 = self.dropout1(out1)
            
            out2, hidden2 = self.lstm2(out1, hidden[1] if hidden else None)
            out2 = self.dropout2(out2)
            
            # Take last time step
            out = out2[:, -1, :]
            
            # Fully connected layers
            out = self.fc1(out)
            out = self.bn1(out)
            out = self.relu(out)
            
            # Output heads
            q_values = self.q_head(out)
            confidence = torch.sigmoid(self.confidence_head(out))
            
            return q_values, confidence, (hidden1, hidden2)


# ============================================================================
# Q-LEARNING AGENT
# ============================================================================

class QLearningAgent:
    """Q-Learning agent with VaR-constrained rewards"""
    
    def __init__(self, num_states: int = 81, num_actions: int = 8,
                 learning_rate: float = 0.001, discount_factor: float = 0.95,
                 epsilon: float = 0.3, epsilon_decay: float = 0.9995,
                 epsilon_min: float = 0.05):
        
        self.num_states = num_states
        self.num_actions = num_actions
        self.lr = learning_rate
        self.gamma = discount_factor
        self.epsilon = epsilon
        self.epsilon_decay = epsilon_decay
        self.epsilon_min = epsilon_min
        
        # Q-table
        self.q_table = np.zeros((num_states, num_actions))
        
        # Experience replay buffer
        self.replay_buffer = deque(maxlen=1_000_000)
        
    def select_action(self, state: int, explore: bool = True) -> int:
        """Epsilon-greedy action selection"""
        if explore and np.random.random() < self.epsilon:
            return np.random.randint(0, self.num_actions)
        else:
            return np.argmax(self.q_table[state])
    
    def update(self, state: int, action: int, reward: float, 
               next_state: int, done: bool):
        """Q-learning update"""
        # TD target
        if done:
            target = reward
        else:
            target = reward + self.gamma * np.max(self.q_table[next_state])
        
        # TD error
        td_error = target - self.q_table[state, action]
        
        # Update Q-value
        self.q_table[state, action] += self.lr * td_error
        
        # Store in replay buffer
        self.replay_buffer.append((state, action, reward, next_state, done, td_error))
        
        # Decay epsilon
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)
        
        return td_error
    
    def batch_update(self, batch_size: int = 256):
        """Update from experience replay"""
        if len(self.replay_buffer) < batch_size:
            return
        
        # Sample batch (prioritized by TD error)
        indices = self._prioritized_sample(batch_size)
        batch = [self.replay_buffer[i] for i in indices]
        
        for state, action, reward, next_state, done, _ in batch:
            if done:
                target = reward
            else:
                target = reward + self.gamma * np.max(self.q_table[next_state])
            
            td_error = target - self.q_table[state, action]
            self.q_table[state, action] += self.lr * td_error
    
    def _prioritized_sample(self, batch_size: int) -> List[int]:
        """Sample experiences prioritized by absolute TD error"""
        if not self.replay_buffer:
            return []
        
        # Extract TD errors
        td_errors = np.array([abs(exp[5]) for exp in self.replay_buffer])
        
        # Add small constant to avoid zero probabilities
        priorities = td_errors + 1e-5
        probabilities = priorities / np.sum(priorities)
        
        # Sample indices
        indices = np.random.choice(len(self.replay_buffer), size=batch_size, 
                                  p=probabilities, replace=False)
        
        return indices.tolist()


# ============================================================================
# VAR CALCULATOR
# ============================================================================

class VaRCalculator:
    """Value at Risk calculation with multiple methods"""
    
    def __init__(self, confidence_level: float = 0.99, horizon_days: int = 1):
        self.confidence = confidence_level
        self.horizon = horizon_days
        self.returns_history = deque(maxlen=10000)
    
    def update(self, return_value: float):
        """Add new return to history"""
        self.returns_history.append(return_value)
    
    def historical_var(self) -> float:
        """Historical VaR"""
        if len(self.returns_history) < 30:
            return 0.0
        
        returns = np.array(self.returns_history)
        percentile = (1 - self.confidence) * 100
        return np.percentile(returns, percentile)
    
    def parametric_var(self) -> float:
        """Parametric VaR (assumes normal distribution)"""
        if len(self.returns_history) < 30:
            return 0.0
        
        returns = np.array(self.returns_history)
        mean = np.mean(returns)
        std = np.std(returns)
        
        # Z-score for 99% confidence
        z_score = 2.33
        
        return mean - z_score * std * np.sqrt(self.horizon)
    
    def cvar(self) -> float:
        """Conditional VaR (Expected Shortfall)"""
        var = self.historical_var()
        
        if var == 0.0:
            return 0.0
        
        returns = np.array(self.returns_history)
        tail_returns = returns[returns < var]
        
        if len(tail_returns) == 0:
            return var
        
        return np.mean(tail_returns)
    
    def monte_carlo_var(self, simulations: int = 10000) -> float:
        """Monte Carlo VaR"""
        if len(self.returns_history) < 30:
            return 0.0
        
        returns = np.array(self.returns_history)
        mean = np.mean(returns)
        std = np.std(returns)
        
        # Simulate returns
        simulated_returns = np.random.normal(mean, std, simulations)
        
        percentile = (1 - self.confidence) * 100
        return np.percentile(simulated_returns, percentile)


# ============================================================================
# KELLY CRITERION
# ============================================================================

class KellyCalculator:
    """Kelly Criterion for optimal position sizing"""
    
    @staticmethod
    def fractional_kelly(win_prob: float, avg_win: float, avg_loss: float,
                        confidence: float = 1.0, fraction: float = 0.25) -> float:
        """
        Calculate fractional Kelly position size
        
        Args:
            win_prob: Probability of winning trade (0-1)
            avg_win: Average win amount
            avg_loss: Average loss amount (positive)
            confidence: Confidence score from LSTM (0-1)
            fraction: Kelly fraction (0.25 = quarter Kelly)
            
        Returns:
            Optimal fraction of capital to risk
        """
        if avg_loss == 0:
            return 0.0
        
        b = avg_win / avg_loss  # Win/loss ratio
        p = win_prob
        q = 1 - p
        
        # Classic Kelly
        kelly = (p * b - q) / b
        
        # Apply confidence and fraction
        kelly_adjusted = kelly * confidence / fraction
        
        # Clamp to reasonable bounds
        return np.clip(kelly_adjusted, 0.0, 1.0)
    
    @staticmethod
    def var_adjusted_kelly(kelly_fraction: float, current_var: float,
                          max_loss_tolerance: float, account_value: float) -> float:
        """
        Adjust Kelly fraction based on VaR constraints
        
        Args:
            kelly_fraction: Base Kelly fraction
            current_var: Current VaR estimate
            max_loss_tolerance: Maximum acceptable loss (e.g., 0.02 for 2%)
            account_value: Total account value
            
        Returns:
            VaR-adjusted position size
        """
        if current_var == 0:
            return kelly_fraction
        
        # Maximum position based on VaR
        max_position_from_var = (max_loss_tolerance * account_value) / abs(current_var)
        
        # Take minimum of Kelly and VaR constraint
        return min(kelly_fraction, max_position_from_var / account_value)


# ============================================================================
# MAIN TRADING STRATEGY
# ============================================================================

class PerpetualTradingStrategy:
    """Main trading strategy combining all components"""
    
    def __init__(self, 
                 rpc_url: str = "https://api.mainnet-beta.solana.com",
                 initial_capital: float = 10000.0,
                 max_leverage: float = 5.0,
                 var_threshold: float = 0.02):
        
        self.rpc_url = rpc_url
        self.initial_capital = initial_capital
        self.account_value = initial_capital
        self.max_leverage = max_leverage
        self.var_threshold = var_threshold
        
        # Components
        self.markov = MarkovChain(num_states=81)
        self.q_agent = QLearningAgent()
        self.var_calc = VaRCalculator(confidence_level=0.99)
        
        if TORCH_AVAILABLE:
            self.lstm = LSTMPredictor()
            self.lstm_optimizer = optim.Adam(self.lstm.parameters(), lr=0.0001)
        else:
            self.lstm = None
        
        # State
        self.position = Position()
        self.current_state = MarketState(
            price_regime=MarketRegime.RANGING,
            volatility=VolatilityRegime.MEDIUM,
            liquidity=LiquidityRegime.NORMAL,
            order_flow=OrderFlow.NEUTRAL
        )
        
        # Data buffers
        self.orderbook_buffer = deque(maxlen=1000)
        self.trade_buffer = deque(maxlen=10000)
        self.feature_buffer = deque(maxlen=100)
        
        # Performance tracking
        self.trade_history = []
        self.returns_history = []
        
        logger.info(f"Strategy initialized with capital: ${initial_capital:.2f}")
    
    async def process_orderbook_snapshot(self, snapshot: OrderBookSnapshot):
        """Process new order book snapshot"""
        self.orderbook_buffer.append(snapshot)
        
        # Compute microstructure features
        features = MicrostructureAnalyzer.compute_all_features(
            snapshot, list(self.trade_buffer)
        )
        
        self.feature_buffer.append(features)
        
        # Update market state
        self._update_market_state(snapshot, features)
        
        # Update Markov chain
        if len(self.orderbook_buffer) >= 2:
            prev_state_id = self.current_state.to_id()
            self.markov.update(prev_state_id, self.current_state.to_id())
    
    async def process_trade(self, trade: Trade):
        """Process new trade"""
        self.trade_buffer.append(trade)
    
    def _update_market_state(self, snapshot: OrderBookSnapshot, features: Dict[str, float]):
        """Update current market regime"""
        # Price regime (simple trend detection)
        if len(self.orderbook_buffer) >= 20:
            prices = [ob.mid_price for ob in list(self.orderbook_buffer)[-20:]]
            price_change = (prices[-1] - prices[0]) / prices[0]
            
            if price_change > 0.001:  # 0.1% threshold
                price_regime = MarketRegime.UPTREND
            elif price_change < -0.001:
                price_regime = MarketRegime.DOWNTREND
            else:
                price_regime = MarketRegime.RANGING
        else:
            price_regime = MarketRegime.RANGING
        
        # Volatility regime
        if len(self.orderbook_buffer) >= 60:
            prices = [ob.mid_price for ob in list(self.orderbook_buffer)[-60:]]
            returns = np.diff(prices) / prices[:-1]
            volatility = np.std(returns)
            
            if volatility < 0.0005:
                vol_regime = VolatilityRegime.LOW
            elif volatility < 0.002:
                vol_regime = VolatilityRegime.MEDIUM
            else:
                vol_regime = VolatilityRegime.HIGH
        else:
            vol_regime = VolatilityRegime.MEDIUM
        
        # Liquidity regime
        total_liquidity = sum(size for _, size in snapshot.bids[:10]) + \
                         sum(size for _, size in snapshot.asks[:10])
        
        if total_liquidity < 1000:
            liq_regime = LiquidityRegime.THIN
        elif total_liquidity < 10000:
            liq_regime = LiquidityRegime.NORMAL
        else:
            liq_regime = LiquidityRegime.THICK
        
        # Order flow regime
        ofi = features.get('ofi_5', 0)
        if ofi > 0.3:
            flow_regime = OrderFlow.BUYER_PRESSURE
        elif ofi < -0.3:
            flow_regime = OrderFlow.SELLER_PRESSURE
        else:
            flow_regime = OrderFlow.NEUTRAL
        
        self.current_state = MarketState(
            price_regime=price_regime,
            volatility=vol_regime,
            liquidity=liq_regime,
            order_flow=flow_regime
        )
    
    def calculate_reward(self, action: Action, prev_position: Position,
                        current_price: float) -> float:
        """Calculate VaR-constrained reward"""
        # PnL components
        pnl_realized = self.position.realized_pnl - prev_position.realized_pnl
        pnl_unrealized = self.position.unrealized_pnl
        
        # Calculate components
        α1 = 1.0   # Realized PnL weight
        α2 = 0.5   # Unrealized PnL weight
        α3 = 0.1   # Position size penalty
        α4 = 1.0   # Transaction cost weight
        α5 = 10.0  # Liquidation penalty
        α6 = 0.5   # Sharpe component
        α7 = 5.0   # VaR penalty weight
        
        # Transaction costs (estimated)
        transaction_cost = 0.0005 * abs(self.position.size - prev_position.size) * current_price
        
        # Liquidation penalty (check margin ratio)
        margin_ratio = self.position.margin_used / self.account_value if self.account_value > 0 else 0
        liquidation_penalty = -100 if margin_ratio > 0.9 else 0
        
        # Volatility penalty
        volatility = self.var_calc.parametric_var()
        position_penalty = -abs(self.position.size) * abs(volatility)
        
        # Sharpe component (incremental)
        sharpe_component = 0.0
        if len(self.returns_history) > 30:
            returns = np.array(self.returns_history[-30:])
            if np.std(returns) > 0:
                sharpe_component = np.mean(returns) / np.std(returns)
        
        # VaR penalty
        current_var = self.var_calc.historical_var()
        var_penalty = 0.0
        if current_var < self.var_threshold:
            var_penalty = -max(0, (current_var - self.var_threshold) / self.var_threshold) * 10
        
        # Total reward
        reward = (
            α1 * pnl_realized +
            α2 * pnl_unrealized +
            α3 * position_penalty +
            α4 * (-transaction_cost) +
            α5 * liquidation_penalty +
            α6 * sharpe_component +
            α7 * var_penalty
        )
        
        return reward
    
    async def make_trading_decision(self) -> Tuple[Action, float]:
        """
        Make trading decision using full strategy pipeline
        
        Returns:
            (action, position_size)
        """
        if not self.orderbook_buffer or not self.feature_buffer:
            return Action.HOLD, 0.0
        
        # Get current state
        state_id = self.current_state.to_id()
        
        # Q-Learning action selection
        action_id = self.q_agent.select_action(state_id)
        action = Action(action_id)
        
        # LSTM refinement (if available)
        confidence = 0.5  # Default confidence
        win_probability = 0.5  # Default
        
        if TORCH_AVAILABLE and self.lstm and len(self.feature_buffer) >= 10:
            # Prepare LSTM input
            feature_sequence = list(self.feature_buffer)[-10:]
            feature_array = np.array([[f['ofi_5'], f['ofi_10'], f['microprice'], 
                                      f['mid_price'], f['spread']] 
                                     for f in feature_sequence])
            
            # Normalize
            feature_array = (feature_array - feature_array.mean(axis=0)) / (feature_array.std(axis=0) + 1e-8)
            
            # Convert to tensor
            x = torch.FloatTensor(feature_array).unsqueeze(0)
            
            # Forward pass
            with torch.no_grad():
                q_values, conf, _ = self.lstm(x)
                confidence = conf.item()
                
                # Win probability (softmax over positive Q-values)
                positive_q = torch.relu(q_values[0])
                if positive_q.sum() > 0:
                    win_probability = (positive_q[action_id] / positive_q.sum()).item()
        
        # Calculate position size using Kelly Criterion
        kelly_fraction = KellyCalculator.fractional_kelly(
            win_prob=win_probability,
            avg_win=0.01,  # Placeholder - should track from history
            avg_loss=0.005,
            confidence=confidence,
            fraction=0.25
        )
        
        # VaR adjustment
        current_var = self.var_calc.historical_var()
        var_adjusted_size = KellyCalculator.var_adjusted_kelly(
            kelly_fraction=kelly_fraction,
            current_var=current_var,
            max_loss_tolerance=self.var_threshold,
            account_value=self.account_value
        )
        
        # Apply leverage constraint
        max_size = self.account_value * self.max_leverage
        position_size = min(var_adjusted_size * self.account_value, max_size)
        
        # Adjust based on volatility regime
        if self.current_state.volatility == VolatilityRegime.HIGH:
            position_size *= 0.5
        
        # Adjust based on liquidity regime
        if self.current_state.liquidity == LiquidityRegime.THIN:
            position_size *= 0.3
        
        logger.info(f"Decision: {action.name}, Size: ${position_size:.2f}, "
                   f"Confidence: {confidence:.2f}, Kelly: {kelly_fraction:.2f}")
        
        return action, position_size
    
    async def execute_action(self, action: Action, size: float, 
                           current_price: float) -> bool:
        """
        Execute trading action
        
        Note: This is a placeholder. In production, integrate with:
        - Drift Protocol SDK
        - Jito bundles for MEV protection
        - Proper order submission and confirmation
        """
        logger.info(f"Executing {action.name} with size ${size:.2f} at ${current_price:.2f}")
        
        # Update position (simplified)
        prev_position = Position(
            size=self.position.size,
            entry_price=self.position.entry_price,
            leverage=self.position.leverage,
            realized_pnl=self.position.realized_pnl
        )
        
        if action == Action.LONG_ENTRY:
            self.position.size = size / current_price
            self.position.entry_price = current_price
            self.position.leverage = min(size / self.account_value, self.max_leverage)
            
        elif action == Action.SHORT_ENTRY:
            self.position.size = -(size / current_price)
            self.position.entry_price = current_price
            self.position.leverage = min(size / self.account_value, self.max_leverage)
            
        elif action == Action.CLOSE_ALL:
            pnl = self.position.size * (current_price - self.position.entry_price)
            self.position.realized_pnl += pnl
            self.account_value += pnl
            self.position.size = 0
            self.position.leverage = 1.0
        
        # Update unrealized PnL
        self.position.update_unrealized_pnl(current_price)
        
        # Calculate reward
        reward = self.calculate_reward(action, prev_position, current_price)
        
        # Update Q-agent
        next_state_id = self.current_state.to_id()
        prev_state_id = next_state_id  # Simplified
        self.q_agent.update(prev_state_id, action.value, reward, next_state_id, False)
        
        # Update VaR
        if prev_position.size != 0:
            return_value = (current_price - prev_position.entry_price) / prev_position.entry_price
            self.var_calc.update(return_value)
            self.returns_history.append(return_value)
        
        return True
    
    def get_support_resistance_levels(self) -> List[Tuple[int, float]]:
        """Get support/resistance levels from Markov chain"""
        persistent_states = self.markov.identify_persistent_states(threshold=0.7)
        
        # Map states back to price regimes
        levels = []
        for state_id in persistent_states:
            market_state = MarketState.from_id(state_id)
            entropy = self.markov.get_state_entropy(state_id)
            levels.append((state_id, entropy))
        
        return levels
    
    def get_risk_metrics(self) -> RiskMetrics:
        """Get current risk metrics"""
        return RiskMetrics(
            var_99_1day=self.var_calc.historical_var(),
            cvar=self.var_calc.cvar(),
            current_drawdown=min(0, self.account_value - self.initial_capital) / self.initial_capital,
            max_drawdown=0.0,  # TODO: Track properly
            sharpe_ratio=0.0,  # TODO: Calculate
            sortino_ratio=0.0  # TODO: Calculate
        )
    
    async def training_loop(self, duration_seconds: int = 3600):
        """
        Main training loop for testnet
        
        Args:
            duration_seconds: How long to run (default 1 hour)
        """
        logger.info(f"Starting training loop for {duration_seconds}s")
        
        start_time = datetime.now()
        step = 0
        
        while (datetime.now() - start_time).total_seconds() < duration_seconds:
            # Simulate orderbook snapshot (in production, fetch from real feed)
            # This is just a placeholder
            snapshot = self._generate_mock_snapshot()
            await self.process_orderbook_snapshot(snapshot)
            
            # Make decision every 5 seconds
            if step % 50 == 0:
                action, size = await self.make_trading_decision()
                
                if action != Action.HOLD:
                    current_price = snapshot.mid_price
                    await self.execute_action(action, size, current_price)
            
            # Batch Q-learning update
            if step % 500 == 0:
                self.q_agent.batch_update(batch_size=256)
            
            # Log metrics
            if step % 1000 == 0:
                metrics = self.get_risk_metrics()
                logger.info(f"Step {step}: Account ${self.account_value:.2f}, "
                           f"VaR: {metrics.var_99_1day:.4f}, Position: {self.position.size:.4f}")
            
            step += 1
            await asyncio.sleep(0.1)
        
        logger.info(f"Training complete. Final account value: ${self.account_value:.2f}")
    
    def _generate_mock_snapshot(self) -> OrderBookSnapshot:
        """Generate mock order book for testing"""
        mid_price = 100 + np.random.randn() * 0.1
        
        bids = [(mid_price - i * 0.01, 100 + np.random.randn() * 20) 
                for i in range(1, 21)]
        asks = [(mid_price + i * 0.01, 100 + np.random.randn() * 20) 
                for i in range(1, 21)]
        
        return OrderBookSnapshot(
            timestamp=datetime.now().timestamp(),
            bids=bids,
            asks=asks,
            mid_price=mid_price,
            spread=asks[0][0] - bids[0][0]
        )


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

async def main():
    """Main entry point for testing"""
    logger.info("Initializing Perpetual Trading Strategy...")
    
    # Initialize strategy
    strategy = PerpetualTradingStrategy(
        rpc_url="https://api.mainnet-beta.solana.com",
        initial_capital=10000.0,
        max_leverage=5.0,
        var_threshold=0.02
    )
    
    # Run training loop
    await strategy.training_loop(duration_seconds=300)  # 5 minutes for testing
    
    # Print final metrics
    metrics = strategy.get_risk_metrics()
    print("\n=== Final Metrics ===")
    print(f"Account Value: ${strategy.account_value:.2f}")
    print(f"Total Return: {(strategy.account_value / strategy.initial_capital - 1) * 100:.2f}%")
    print(f"VaR (99%): {metrics.var_99_1day:.4f}")
    print(f"CVaR: {metrics.cvar:.4f}")
    print(f"Max Drawdown: {metrics.max_drawdown:.2%}")
    
    # Print support/resistance levels
    sr_levels = strategy.get_support_resistance_levels()
    print(f"\n=== Support/Resistance Levels ===")
    for state_id, entropy in sr_levels[:5]:
        state = MarketState.from_id(state_id)
        print(f"State {state_id}: {state.price_regime.value}, Entropy: {entropy:.3f}")


if __name__ == "__main__":
    asyncio.run(main())
