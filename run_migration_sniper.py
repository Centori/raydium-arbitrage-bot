#!/usr/bin/env python3
import asyncio
import logging
import sys
from datetime import datetime
from decimal import Decimal
from typing import Optional

from config import Config
from api_client import BlockchainAPIClient, PoolData
from raydium_pools import RaydiumPoolFetcher
from pool_analyzer import PoolAnalyzer
from risk_analyzer import RiskAnalyzer
from migration_sniper import MigrationSniper, MigrationContract
from migration_executor import MigrationExecutor
from migration_contract_monitor import MigrationContractMonitor, MigrationStats

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger()

# Add colorized output
class ColorFormatter(logging.Formatter):
    COLORS = {
        'WARNING': '\033[33m',  # Yellow
        'INFO': '\033[37m',     # White
        'DEBUG': '\033[34m',    # Blue
        'CRITICAL': '\033[35m', # Magenta
        'ERROR': '\033[31m',    # Red
        'OPPORTUNITY': '\033[32m'  # Green
    }
    RESET = '\033[0m'
    
    def format(self, record):
        if not hasattr(record, 'opportunity'):
            color = self.COLORS.get(record.levelname, self.RESET)
        else:
            color = self.COLORS['OPPORTUNITY']
        
        record.msg = f'{color}{record.msg}{self.RESET}'
        return super().format(record)

for handler in logger.handlers:
    handler.setFormatter(ColorFormatter(
        '%(asctime)s | %(levelname)s | %(message)s',
        '%Y-%m-%d %H:%M:%S'
    ))

def format_migration_opportunity(opportunity, stats=None):
    """Format migration opportunity details for display"""
    lines = [
        "=" * 100,
        f"🔄 MIGRATION OPPORTUNITY DETECTED",
        f"V3 Pool: {opportunity.old_pool_id}",
        f"V4 Pool: {opportunity.new_pool_id}",
        f"Tokens: {opportunity.token_a} ⟷ {opportunity.token_b}",
        "-" * 50,
        f"Expected Profit: {opportunity.expected_profit_pct:.2f}%",
        f"Trade Size Range: ${float(opportunity.min_trade_size):.2f} - ${float(opportunity.max_trade_size):.2f}",
        f"Risk Score: {opportunity.risk_score:.2f}",
        "-" * 50,
        "Price Impact Analysis:",
        f"  Base Impact: {opportunity.price_impact.base_impact*100:.2f}%",
        f"  Quote Impact: {opportunity.price_impact.quote_impact*100:.2f}%",
        f"  Combined Impact: {opportunity.price_impact.combined_impact*100:.2f}%",
        f"  Slippage Estimate: {opportunity.price_impact.slippage_estimate*100:.2f}%",
        f"  Confidence Score: {opportunity.price_impact.confidence_score:.2f}"
    ]
    
    if opportunity.migration_contract:
        contract = opportunity.migration_contract
        lines.extend([
            "-" * 50,
            "Migration Contract Details:",
            f"  Contract: {contract.address}",
            f"  Deadline: {datetime.fromtimestamp(contract.migration_deadline)}",
            f"  Rewards Multiplier: {contract.rewards_multiplier}x",
            f"  Status: {'🟢 Active' if contract.is_active else '🔴 Inactive'}"
        ])
        
        if stats:
            lines.extend([
                "-" * 50,
                "Migration Statistics:",
                f"  Total Migrations: {stats.total_migrations}",
                f"  Total Volume: ${float(stats.total_volume):.2f}",
                f"  Unique Users: {stats.unique_users}",
                f"  Avg Slippage: {float(stats.avg_slippage)*100:.2f}%",
                f"  Success Rate: {stats.success_rate*100:.1f}%",
                f"  Avg Gas Cost: {float(stats.avg_gas_cost):.4f} SOL"
            ])
    
    lines.append("=" * 100)
    return "\n".join(lines)

async def main():
    try:
        # Initialize components
        config = Config()
        api_client = BlockchainAPIClient(config)
        pool_fetcher = RaydiumPoolFetcher(config)
        risk_analyzer = RiskAnalyzer(config)
        pool_analyzer = PoolAnalyzer(config, risk_analyzer)
        
        # Initialize migration monitoring system
        contract_monitor = MigrationContractMonitor(api_client)
        migration_executor = MigrationExecutor(config, pool_analyzer, api_client)
        
        # Initialize migration sniper
        sniper = MigrationSniper(config, pool_fetcher, pool_analyzer, executor=migration_executor)
        
        logger.info("Starting migration opportunity monitoring...")
        
        # Start monitoring tasks
        monitor_task = asyncio.create_task(contract_monitor.start_monitoring())
        sniper_task = asyncio.create_task(sniper.start_monitoring())
        
        try:
            while True:
                # Keep tasks alive; opportunities will be logged by the sniper when detected
                logger.debug("Monitoring for migration opportunities...")
                await asyncio.sleep(5)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            monitor_task.cancel()
            sniper_task.cancel()
            
    except Exception as e:
        logger.error(f"Error in main loop: {e}")
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)