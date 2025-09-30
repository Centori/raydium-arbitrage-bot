import pandas as pd
import numpy as np
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import json
import logging
from dataclasses import dataclass
from config import Config
from pool_analyzer import PoolAnalyzer
from risk_analyzer import RiskAnalyzer
from monitor import TradingMonitor, TradeMetrics

@dataclass
class BacktestTrade:
    timestamp: datetime
    pool_id: str
    base_token: str
    quote_token: str
    action: str  # 'buy' or 'sell'
    amount: float
    price: float
    gas_cost: float
    slippage: float
    profit_loss: float

class Backtester:
    def __init__(self, config: Config):
        self.config = config
        self.risk_analyzer = RiskAnalyzer(config)
        self.pool_analyzer = PoolAnalyzer(config, self.risk_analyzer)
        self.monitor = TradingMonitor(config)
        
        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            filename='backtest.log'
        )
        self.logger = logging.getLogger(__name__)
        
        # Trading parameters
        self.initial_capital = 1000  # USD
        self.trade_size = 100        # USD per trade
        self.max_slippage = 0.02     # 2%
        self.min_profit = 0.001      # 0.1%
        
        # Results storage
        self.trades: List[BacktestTrade] = []
        self.portfolio_value: List[float] = [self.initial_capital]
        self.current_capital = self.initial_capital

    def load_historical_data(self, start_date: datetime, end_date: datetime) -> Dict:
        """Load historical pool data for backtesting"""
        try:
            # In production, load real historical data
            # For testing, we'll simulate some data
            data = {}
            current_date = start_date
            
            while current_date <= end_date:
                # Simulate daily pool states
                data[current_date.strftime('%Y-%m-%d')] = self._generate_test_data()
                current_date += timedelta(days=1)
            
            return data
        except Exception as e:
            self.logger.error(f"Error loading historical data: {str(e)}")
            return {}

    def _generate_test_data(self) -> Dict:
        """Generate sample pool data for testing"""
        return {
            'pools': [
                {
                    'id': 'sol_usdc_pool',
                    'base_token': 'SOL',
                    'quote_token': 'USDC',
                    'base_amount': '100000000000',
                    'quote_amount': '2000000000000',
                    'volume_24h': '5000000',
                    'price': '20.5',
                    'price_change_24h': '0.02'
                },
                # Add more test pools
            ]
        }

    def simulate_trade(self, pool_data: Dict, amount_in: float) -> Optional[BacktestTrade]:
        """Simulate a trade with historical data"""
        try:
            # Calculate expected output with simulated slippage
            base_amount = float(pool_data['base_amount'])
            quote_amount = float(pool_data['quote_amount'])
            
            # Simulate slippage based on trade size relative to pool size
            slippage = min(0.05, (amount_in / float(pool_data['volume_24h'])) * 100)
            
            # Calculate output amount using AMM formula with slippage
            price = float(pool_data['price'])
            amount_out = (amount_in / price) * (1 - slippage)
            
            # Simulate gas cost (in USD)
            gas_cost = 0.001  # Simplified fixed gas cost
            
            # Calculate profit/loss
            profit_loss = amount_out * price - amount_in - gas_cost
            
            return BacktestTrade(
                timestamp=datetime.now(),
                pool_id=pool_data['id'],
                base_token=pool_data['base_token'],
                quote_token=pool_data['quote_token'],
                action='buy',
                amount=amount_in,
                price=price,
                gas_cost=gas_cost,
                slippage=slippage,
                profit_loss=profit_loss
            )
        except Exception as e:
            self.logger.error(f"Error simulating trade: {str(e)}")
            return None

    def run_backtest(self, start_date: datetime, end_date: datetime) -> Dict:
        """Run backtest over specified period"""
        try:
            self.logger.info(f"Starting backtest from {start_date} to {end_date}")
            
            # Load historical data
            historical_data = self.load_historical_data(start_date, end_date)
            
            # Run simulation
            for date, daily_data in historical_data.items():
                self.logger.info(f"Processing date: {date}")
                
                # Analyze pools for the day
                for pool_data in daily_data['pools']:
                    # Check if pool meets our criteria
                    if self._should_trade(pool_data):
                        # Simulate trade
                        trade = self.simulate_trade(pool_data, self.trade_size)
                        if trade and trade.profit_loss > 0:
                            self.trades.append(trade)
                            self.current_capital += trade.profit_loss
                            self.portfolio_value.append(self.current_capital)
                            
                            # Log trade metrics
                            self.monitor.monitor_transaction(TradeMetrics(
                                timestamp=trade.timestamp.timestamp(),
                                pool_id=trade.pool_id,
                                base_token=trade.base_token,
                                quote_token=trade.quote_token,
                                amount_in=trade.amount,
                                amount_out=trade.amount * (1 + trade.profit_loss),
                                profit_loss=trade.profit_loss,
                                gas_cost=trade.gas_cost,
                                slippage=trade.slippage,
                                execution_time=0.1  # Simulated execution time
                            ))
            
            return self.get_backtest_results()
            
        except Exception as e:
            self.logger.error(f"Error in backtest: {str(e)}")
            return {}

    def _should_trade(self, pool_data: Dict) -> bool:
        """Determine if we should trade based on pool data"""
        try:
            # Check volume
            if float(pool_data['volume_24h']) < self.config.MIN_POOL_VOLUME:
                return False
            
            # Check price movement
            if abs(float(pool_data['price_change_24h'])) > self.config.MAX_PRICE_IMPACT:
                return False
            
            # More checks can be added here
            
            return True
        except:
            return False

    def get_backtest_results(self) -> Dict:
        """Calculate and return backtest results"""
        if not self.trades:
            return {"error": "No trades executed"}
            
        total_trades = len(self.trades)
        profitable_trades = len([t for t in self.trades if t.profit_loss > 0])
        total_profit = sum(t.profit_loss for t in self.trades)
        total_gas = sum(t.gas_cost for t in self.trades)
        
        # Calculate returns
        returns = np.diff(self.portfolio_value) / self.portfolio_value[:-1]
        sharpe_ratio = np.sqrt(252) * (np.mean(returns) / np.std(returns)) if len(returns) > 1 else 0
        
        return {
            "start_capital": self.initial_capital,
            "end_capital": self.current_capital,
            "total_return": ((self.current_capital - self.initial_capital) / self.initial_capital) * 100,
            "total_trades": total_trades,
            "profitable_trades": profitable_trades,
            "win_rate": (profitable_trades / total_trades * 100) if total_trades > 0 else 0,
            "total_profit": total_profit,
            "total_gas_spent": total_gas,
            "sharpe_ratio": sharpe_ratio,
            "max_drawdown": self._calculate_max_drawdown(),
            "daily_stats": self._calculate_daily_stats()
        }

    def _calculate_max_drawdown(self) -> float:
        """Calculate maximum drawdown from portfolio value history"""
        if len(self.portfolio_value) < 2:
            return 0
        
        portfolio_values = np.array(self.portfolio_value)
        peak = np.maximum.accumulate(portfolio_values)
        drawdown = (peak - portfolio_values) / peak
        return float(np.max(drawdown)) * 100

    def _calculate_daily_stats(self) -> Dict:
        """Calculate daily trading statistics"""
        daily_profits = {}
        
        for trade in self.trades:
            date = trade.timestamp.strftime('%Y-%m-%d')
            if date not in daily_profits:
                daily_profits[date] = 0
            daily_profits[date] += trade.profit_loss
        
        return {
            "best_day": max(daily_profits.values()) if daily_profits else 0,
            "worst_day": min(daily_profits.values()) if daily_profits else 0,
            "avg_daily_profit": sum(daily_profits.values()) / len(daily_profits) if daily_profits else 0
        }