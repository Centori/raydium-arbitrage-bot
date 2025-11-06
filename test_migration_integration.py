#!/usr/bin/env python3
import asyncio
import logging
from decimal import Decimal
from datetime import datetime, timedelta
import pytest
from solders.pubkey import Pubkey

from config import Config
from api_client import BlockchainAPIClient
from venue_tracker import VenueTracker
from solana_elite_tracker import SolanaEliteTracker
from pool_analyzer import PoolAnalyzer
from migration_executor import MigrationExecutor, MigrationResult
from migration_sniper import MigrationContract

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("migration_test")

class TestMigrationIntegration:
    """Integration tests for migration execution with monitoring components"""

    async def build_setup(self):
        """Setup test environment (usable by pytest and standalone)"""
        config = Config()
        api_client = BlockchainAPIClient(config)
        venue_tracker = VenueTracker(config)
        elite_tracker = SolanaEliteTracker(config)
        pool_analyzer = PoolAnalyzer(config, api_client)
        executor = MigrationExecutor(config, pool_analyzer, api_client)
        return {
            'config': config,
            'api_client': api_client,
            'venue_tracker': venue_tracker,
            'elite_tracker': elite_tracker,
            'pool_analyzer': pool_analyzer,
            'executor': executor
        }

    @pytest.mark.asyncio
    async def test_migration_analysis_flow(self):
        setup = await self.build_setup()
        try:
            # Sample pool addresses
            v3_pool = "V3PoolAddress111111111111111111111111111111"
            v4_pool = "V4PoolAddress222222222222222222222222222222"

            # 1. Analyze migration opportunity
            opportunity = await setup['venue_tracker'].analyze_migration_opportunity(
                v3_pool,
                v4_pool
            )
            assert opportunity is not None, "Failed to analyze migration opportunity"
            logger.info(f"Migration opportunity analysis: {opportunity}")

            # 2. Check elite trader activity
            elite_traders = await setup['elite_tracker'].track_migration_trades(
                v3_pool,
                v4_pool
            )
            assert len(elite_traders) > 0, "No elite traders found"
            logger.info(f"Found {len(elite_traders)} elite traders")

            # 3. Create test migration contract
            migration_contract = MigrationContract(
                address="11111111111111111111111111111111",
                source_pool=v3_pool,
                target_pool=v4_pool,
                migration_deadline=int((datetime.now() + timedelta(days=7)).timestamp()),
                rewards_multiplier=1.0,
                is_active=True
            )

            # 4. Calculate migration parameters
            amount = Decimal("1.0")  # 1 SOL for testing
            slippage = Decimal("0.01")  # 1%

            # Adjust amount based on venue tracker recommendation
            if opportunity['recommended_split_size'] < amount:
                amount = opportunity['recommended_split_size']
                logger.info(f"Adjusted amount to recommended size: {amount}")

            # 5. Execute migration if risk is acceptable
            if opportunity['migration_risk_score'] < 50:  # Risk threshold
                result = await setup['executor'].execute_migration(
                    migration_contract,
                    amount,
                    slippage
                )

                assert isinstance(result, MigrationResult), "Invalid result type"
                logger.info(f"Migration execution result: {result}")

                if result.success:
                    logger.info(
                        f"Migration successful!\n"
                        f"Amount in: {result.amount_in}\n"
                        f"Amount out: {result.amount_out}\n"
                        f"Effective price: {result.effective_price}\n"
                        f"Fees paid: {result.fees_paid}"
                    )
                else:
                    logger.warning(f"Migration failed: {result.error_message}")
            else:
                logger.warning(
                    f"Migration skipped - risk too high "
                    f"(score: {opportunity['migration_risk_score']})"
                )

        except Exception as e:
            logger.error(f"Migration integration test failed: {e}")
            raise

async def main():
    """Run the integration test standalone"""
    test = TestMigrationIntegration()
    await test.test_migration_analysis_flow()

if __name__ == '__main__':
    asyncio.run(main())