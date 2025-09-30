import asyncio
import logging
from config import Config
import os
from dotenv import load_dotenv
from api_client import BlockchainAPIClient
from wallet import WalletManager
from backrun_strategy import BackrunStrategy

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("test_backrun")

async def main():
    try:
        # Load environment variables
        load_dotenv()
        
        # Load configuration
        config = Config()
        
        # Set up API endpoints
        os.environ['API_HOST'] = 'localhost'
        os.environ['API_PORT'] = '3000'
        
        # Initialize API client
        api_client = BlockchainAPIClient(config)
        
        # Initialize wallet manager
        wallet_manager = WalletManager(config)
        
        # Create backrun strategy instance
        strategy = BackrunStrategy(config, api_client, wallet_manager)
        
        # Start monitoring with Yellowstone (Jito's mempool service)
        yellowstone_url = "wss://mainnet.block-engine.jito.wtf/search"
        yellowstone_token = os.getenv('JITO_AUTH_KEYPAIR_BASE64', '')
        
        logger.info("Starting backrun strategy test...")
        await strategy.start_monitoring(yellowstone_url, yellowstone_token)
        
    except KeyboardInterrupt:
        logger.info("Stopping backrun strategy...")
        strategy.stop_monitoring()
    except Exception as e:
        logger.exception("Error in backrun test")

if __name__ == "__main__":
    asyncio.run(main())