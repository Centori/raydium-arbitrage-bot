import asyncio
import logging
import signal
from typing import Optional

from config import Config
from api_client import BlockchainAPIClient
from wallet import WalletManager
from backrun_strategy import BackrunStrategy, create_backrun_strategy

# Configure logging
logger = logging.getLogger("backrun_integration")

class BackrunIntegration:
    """Integration class to connect backrun strategy with the main arbitrage bot"""
    
    def __init__(self, config: Config, api_client: BlockchainAPIClient, wallet_manager: WalletManager):
        """Initialize the backrun integration"""
        self.config = config
        self.api_client = api_client
        self.wallet_manager = wallet_manager
        self.backrun_strategy: Optional[BackrunStrategy] = None
        self.running = False
        
        # Load configuration
        self.enable_backrun = self.config.BACKRUN_STRATEGY.get("ENABLE_BACKRUN_STRATEGY", False)
        self.yellowstone_url = self.config.YELLOWSTONE.get("YELLOWSTONE_URL", "")
        self.yellowstone_token = self.config.YELLOWSTONE.get("YELLOWSTONE_XTOKEN", "")
        
    async def start(self):
        """Start the backrun strategy"""
        if not self.enable_backrun:
            logger.info("Backrun strategy is disabled in configuration")
            return
            
        if not self.yellowstone_url or not self.yellowstone_token:
            logger.error("Yellowstone URL or token not configured. Cannot start backrun strategy.")
            return
            
        try:
            logger.info("Initializing backrun strategy...")
            self.backrun_strategy = create_backrun_strategy(self.config, self.api_client, self.wallet_manager)
            
            # Start monitoring for backrun opportunities
            self.running = True
            asyncio.create_task(self._run_backrun_strategy())
            
            logger.info("Backrun strategy started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start backrun strategy: {str(e)}")
            self.running = False
    
    async def _run_backrun_strategy(self):
        """Run the backrun strategy"""
        if not self.backrun_strategy:
            return
            
        try:
            await self.backrun_strategy.start_monitoring(
                self.yellowstone_url, 
                self.yellowstone_token
            )
        except Exception as e:
            logger.error(f"Error in backrun strategy: {str(e)}")
            self.running = False
    
    async def stop(self):
        """Stop the backrun strategy"""
        if self.backrun_strategy and self.running:
            logger.info("Stopping backrun strategy...")
            self.backrun_strategy.stop_monitoring()
            self.running = False
            logger.info("Backrun strategy stopped")

# Main function for testing the backrun strategy standalone
async def main():
    """Main function for testing the backrun integration standalone"""
    from config import load_config
    
    # Load configuration
    config = load_config()
    
    # Create API client 
    api_client = BlockchainAPIClient(config)
    
    # Create wallet manager
    wallet_manager = WalletManager(config)
    await wallet_manager.initialize()
    
    # Create backrun integration
    integration = BackrunIntegration(config, api_client, wallet_manager)
    
    # Setup signal handlers
    def signal_handler():
        asyncio.create_task(integration.stop())
    
    for sig in [signal.SIGINT, signal.SIGTERM]:
        asyncio.get_event_loop().add_signal_handler(sig, signal_handler)
    
    # Start backrun integration
    await integration.start()
    
    # Keep running until stopped
    while integration.running:
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())