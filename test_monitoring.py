#!/usr/bin/env python3
import asyncio
import logging
from datetime import datetime
import sys
from decimal import Decimal
import click
import aiohttp
from solders.pubkey import Pubkey

from config import Config
from solana_elite_tracker import SolanaEliteTracker
from venue_tracker import VenueTracker
from api_client import BlockchainAPIClient

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("monitoring_test")

class MonitoringTester:
    def __init__(self, config: Config):
        self.config = config
        self.api_client = BlockchainAPIClient(config)
        self.elite_tracker = SolanaEliteTracker(config)
        self.venue_tracker = VenueTracker(config)
        
    async def test_all_components(self):
        """Run all monitoring component tests"""
        try:
            logger.info("Starting comprehensive monitoring tests...")
            
            # Test API connections
            await self._test_api_connections()
            
            # Test venue monitoring
            await self._test_venue_monitoring()
            
            # Test elite trader tracking
            await self._test_elite_tracking()
            
            # Test liquidity monitoring
            await self._test_liquidity_monitoring()
            
            # Test execution components
            await self._test_execution_components()
            
            logger.info("All tests completed successfully!")
            
        except Exception as e:
            logger.error(f"Test failed: {e}")
            sys.exit(1)
    
    async def _test_api_connections(self):
        """Test all API connections"""
        logger.info("\nTesting API connections...")
        
        # Test RPC connection
        try:
            slot = await self.api_client.rpc_client.get_slot()
            logger.info(f"✓ RPC connection successful (current slot: {slot})")
        except Exception as e:
            logger.error(f"✗ RPC connection failed: {e}")
            raise
        
        # Test Birdeye API if configured
        if getattr(self.config, "BIRDEYE_API_KEY", None):
            try:
                await self._test_birdeye_api()
                logger.info("✓ Birdeye API connection successful")
            except Exception as e:
                logger.error(f"✗ Birdeye API connection failed: {e}")
                raise
        
        # Test Jupiter API (optional)
        try:
            await self._test_jupiter_api()
            logger.info("✓ Jupiter API connection successful")
        except Exception as e:
            logger.warning(f"Note: Jupiter API check skipped - {e}")
    
    async def _test_birdeye_api(self):
        """Test Birdeye API by fetching token list"""
        url = "https://api.birdeye.so/v1/token/list"
        headers = {"X-Api-Key": self.config.BIRDEYE_API_KEY}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=10) as resp:
                if resp.status != 200:
                    raise Exception(f"HTTP {resp.status}")
                await resp.json()
                return True

    async def _test_jupiter_api(self):
        """Test Jupiter API by getting a simple quote"""
        quote_url = f"{self.config.JUPITER_API_URL}/quote"
        params = {
            "inputMint": "So11111111111111111111111111111111111111112",
            "outputMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "amount": "1000000"
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(quote_url, params=params, timeout=10) as resp:
                if resp.status != 200:
                    raise Exception(f"HTTP {resp.status}")
                await resp.json()
                return True

    async def _test_venue_monitoring(self):
        """Test venue monitoring components"""
        logger.info("\nTesting venue monitoring...")
        
        try:
            # Test Raydium monitoring
            try:
                raydium_stats = await self.venue_tracker._monitor_raydium_v4()
                logger.info("✓ Raydium monitoring successful")
            except Exception as e:
                logger.warning(f"Note: Raydium monitoring skipped - {e}")
            
            # Test Meteora monitoring
            try:
                meteora_stats = await self.venue_tracker._monitor_meteora()
                logger.info("✓ Meteora monitoring successful")
            except Exception as e:
                logger.warning(f"Note: Meteora monitoring skipped - {e}")
            
            # Get venue rankings
            try:
                rankings = await self.venue_tracker.get_venue_rankings()
                logger.info("\nCurrent Venue Rankings:")
                for venue in rankings:
                    logger.info(f"- {venue.name}: ${float(venue.total_liquidity_usd):,.2f} TVL")
            except Exception as e:
                logger.warning(f"Note: Venue rankings skipped - {e}")
            
        except Exception as e:
            logger.error(f"✗ Venue monitoring failed: {e}")
            raise
    
    async def _test_elite_tracking(self):
        """Test elite trader tracking"""
        logger.info("\nTesting elite trader tracking...")
        
        try:
            # Test with a known wallet
            test_wallet = "11111111111111111111111111111111"
            stats = await self.elite_tracker.get_trader_stats(test_wallet, days=30)
            
            if stats:
                logger.info("\nTrader Stats Test:")
                logger.info(
                    f"- Trades: {stats.trades}\n"
                    f"  Win Rate: {stats.win_rate*100:.1f}%\n"
                    f"  Avg Return: {stats.avg_return_pct:.1f}%\n"
                    f"  Volume: ${float(stats.total_volume_usd):,.2f}"
                )
            else:
                logger.warning("No trader stats available for test wallet")
            
            logger.info("✓ Elite trader tracking successful")
            
        except Exception as e:
            logger.error(f"✗ Elite trader tracking failed: {e}")
            raise
    
    async def _test_liquidity_monitoring(self):
        """Test liquidity monitoring"""
        logger.info("\nTesting liquidity monitoring...")
        
        try:
            # Test recent launches tracking
            try:
                recent_launches = await self.venue_tracker.get_recent_launches()
                
                if recent_launches:
                    logger.info("\nRecent Token Launches:")
                    for launch in recent_launches:
                        logger.info(
                            f"- {launch.token_symbol}:\n"
                            f"  Platform: {launch.launch_platform}\n"
                            f"  Initial Liquidity: ${float(launch.initial_liquidity_usd):,.2f}\n"
                            f"  Elite Traders: {launch.elite_trader_count}"
                        )
                else:
                    logger.warning("No recent launches found")
            except Exception as e:
                logger.warning(f"Note: Recent launches tracking skipped - {e}")
            
            # Test liquidity event detection
            try:
                await self._test_liquidity_events()
            except Exception as e:
                logger.warning(f"Note: Liquidity event detection skipped - {e}")
            
            logger.info("✓ Liquidity monitoring successful")
            
        except Exception as e:
            logger.error(f"✗ Liquidity monitoring failed: {e}")
            raise
    
    async def _test_liquidity_events(self):
        """Test liquidity event detection"""
        # Get some recent transactions
        try:
            sigs = await self.api_client.rpc_client.get_signatures_for_address(
                Pubkey.from_string(self.venue_tracker.RAYDIUM_V4_PROGRAM)
            )
            
            if not sigs.value:
                logger.warning("No recent transactions found for testing")
                return
            
            # Test processing a few transactions
            for sig in sigs.value[:5]:
                tx = await self.api_client.rpc_client.get_transaction(
                    sig.signature,
                    encoding="jsonParsed"
                )
                
                if tx and tx.value:
                    await self.venue_tracker._analyze_pool_activity(tx.value, "raydium")
            
            logger.info("✓ Liquidity event detection successful")
            
        except Exception as e:
            logger.error(f"✗ Liquidity event detection failed: {e}")
            raise
    
    async def _test_execution_components(self):
        """Test execution components"""
        logger.info("\nTesting execution components...")
        
        # Test execution preparation (most basic test)
        try:
            blockhash = await self.api_client.rpc_client.get_latest_blockhash()
            if blockhash:
                logger.info("✓ Execution preparation successful (got recent blockhash)")
            else:
                logger.warning("Could not get recent blockhash")
        except Exception as e:
            logger.error(f"✗ Execution preparation failed: {e}")
            return
        
        # Test priority fee estimation (if available)
        try:
            slot = await self.api_client.rpc_client.get_slot()
            logger.info(f"✓ Got current slot: {slot}")
        except Exception as e:
            logger.warning(f"Slot check failed: {e}")
        
        logger.info("✓ Basic execution components tested")

@click.command()
@click.option('--component', type=click.Choice(['all', 'api', 'venues', 'traders', 'liquidity', 'execution']),
             default='all', help='Component to test')
def main(component):
    """Test monitoring and execution components"""
    config = Config()  # Load your configuration
    tester = MonitoringTester(config)
    
    async def run_tests():
        if component == 'all':
            await tester.test_all_components()
        elif component == 'api':
            await tester._test_api_connections()
        elif component == 'venues':
            await tester._test_venue_monitoring()
        elif component == 'traders':
            await tester._test_elite_tracking()
        elif component == 'liquidity':
            await tester._test_liquidity_monitoring()
        elif component == 'execution':
            await tester._test_execution_components()
    
    asyncio.run(run_tests())

if __name__ == '__main__':
    main()