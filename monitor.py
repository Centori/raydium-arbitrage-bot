from typing import Dict, List, Optional
import time
import json
import asyncio
from datetime import datetime
from dataclasses import dataclass
import logging
from config import Config

@dataclass
class TradeMetrics:
    timestamp: float
    pool_id: str
    base_token: str
    quote_token: str
    amount_in: float
    amount_out: float
    profit_loss: float
    gas_cost: float
    slippage: float
    execution_time: float

class TradingMonitor:
    def __init__(self, config: Config):
        self.config = config
        self.metrics: List[TradeMetrics] = []
        self.alert_thresholds = {
            'max_slippage': 2.0,  # 2% max slippage
            'min_profit': 0.1,    # Minimum profit in USD
            'max_gas': 0.01,      # Maximum gas cost in SOL
            'max_execution_time': 2.0  # Maximum execution time in seconds
        }
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('trading.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    async def monitor_transaction(self, trade_metrics: TradeMetrics) -> bool:
        """Monitor a single transaction and return True if it meets all criteria"""
        alerts = []

        # Check slippage
        if trade_metrics.slippage > self.alert_thresholds['max_slippage']:
            alerts.append(f"High slippage detected: {trade_metrics.slippage}%")

        # Check profit
        if trade_metrics.profit_loss < self.alert_thresholds['min_profit']:
            alerts.append(f"Low profit warning: ${trade_metrics.profit_loss}")

        # Check gas costs
        if trade_metrics.gas_cost > self.alert_thresholds['max_gas']:
            alerts.append(f"High gas cost: {trade_metrics.gas_cost} SOL")

        # Check execution time
        if trade_metrics.execution_time > self.alert_thresholds['max_execution_time']:
            alerts.append(f"Slow execution: {trade_metrics.execution_time}s")

        # Log alerts
        if alerts:
            alert_msg = "\n".join(alerts)
            self.logger.warning(f"Trade alerts for {trade_metrics.pool_id}:\n{alert_msg}")
            return False

        # Log success
        self.logger.info(f"Successful trade in pool {trade_metrics.pool_id}")
        self.metrics.append(trade_metrics)
        return True

    def get_performance_summary(self) -> Dict:
        """Calculate performance metrics over all trades"""
        if not self.metrics:
            return {"message": "No trades recorded yet"}

        total_profit = sum(m.profit_loss for m in self.metrics)
        total_gas = sum(m.gas_cost for m in self.metrics)
        avg_execution_time = sum(m.execution_time for m in self.metrics) / len(self.metrics)
        success_rate = len([m for m in self.metrics if m.profit_loss > 0]) / len(self.metrics) * 100

        return {
            "total_trades": len(self.metrics),
            "total_profit_usd": total_profit,
            "total_gas_cost_sol": total_gas,
            "average_execution_time": avg_execution_time,
            "success_rate": success_rate,
            "profit_per_trade": total_profit / len(self.metrics) if self.metrics else 0
        }

    async def monitor_health(self):
        """Monitor system health in real-time"""
        while True:
            try:
                # Calculate recent performance
                recent_metrics = self.metrics[-100:] if len(self.metrics) > 100 else self.metrics
                if recent_metrics:
                    recent_success_rate = len([m for m in recent_metrics if m.profit_loss > 0]) / len(recent_metrics) * 100
                    avg_recent_profit = sum(m.profit_loss for m in recent_metrics) / len(recent_metrics)
                    
                    # Alert on performance degradation
                    if recent_success_rate < 50:
                        self.logger.warning(f"Low success rate alert: {recent_success_rate}%")
                    if avg_recent_profit < 0:
                        self.logger.warning(f"Negative profit alert: ${avg_recent_profit}")

                # Monitor system resources
                # TODO: Add CPU, memory, and network monitoring

                await asyncio.sleep(60)  # Check every minute
            except Exception as e:
                self.logger.error(f"Error in health monitoring: {str(e)}")
                await asyncio.sleep(5)  # Short delay on error

    def save_metrics(self):
        """Save trading metrics to file"""
        try:
            with open('trading_metrics.json', 'w') as f:
                json.dump([vars(m) for m in self.metrics], f)
        except Exception as e:
            self.logger.error(f"Error saving metrics: {str(e)}")

    def load_metrics(self):
        """Load trading metrics from file"""
        try:
            with open('trading_metrics.json', 'r') as f:
                data = json.load(f)
                self.metrics = [TradeMetrics(**m) for m in data]
        except FileNotFoundError:
            self.logger.info("No previous metrics file found")
        except Exception as e:
            self.logger.error(f"Error loading metrics: {str(e)}")