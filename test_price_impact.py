import asyncio
import logging
from config import Config
from jito_executor import JitoExecutor
from wallet import WalletManager

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ArbitrageOpportunity:
    """Mock arbitrage opportunity for testing"""
    def __init__(self):
        self.expected_profit = 0.05  # 0.05 SOL
        self.sol_price = 150.0  # $150 per SOL
        self.estimated_price_impact = 0.0065  # 0.65% - above the 0.52% threshold
        self.amount = 100.0
        self.type = "triangle"
        self.tokens = ["SOL", "USDC", "RAY"]
        self.pools = ["SOL/USDC", "USDC/RAY", "RAY/SOL"]

async def test_price_impact_limiting():
    """Test the price impact limiting feature"""
    config = Config()
    wallet_manager = WalletManager(config)
    
    # Initialize the executor
    jito_executor = JitoExecutor(wallet_manager, config)
    await jito_executor.initialize()
    
    # Create a mock opportunity with high price impact
    opportunity = ArbitrageOpportunity()
    original_amount = opportunity.amount
    original_impact = opportunity.estimated_price_impact
    
    logger.info(f"Original opportunity: Amount={original_amount}, Price Impact={original_impact*100:.2f}%, Expected Profit=${opportunity.expected_profit*opportunity.sol_price:.2f}")
    
    # This call should adjust the trade size based on price impact
    # Note: this will fail at the transaction building stage without a real opportunity
    # but we're just testing the price impact adjustment logic
    try:
        result = await jito_executor.submit_arbitrage_opportunity(opportunity)
        
        # We expect this to fail at some point, but we should see the price impact adjustment in logs
        logger.info(f"After adjustment: Amount={opportunity.amount}, Price Impact={opportunity.estimated_price_impact*100:.2f}%, Expected Profit=${opportunity.expected_profit*opportunity.sol_price:.2f}")
        
        # Verify the adjustment was made correctly
        adjustment_ratio = jito_executor.max_price_impact / original_impact
        expected_new_amount = original_amount * adjustment_ratio
        
        logger.info(f"Expected adjusted amount: {expected_new_amount:.2f}")
        logger.info(f"Actual adjusted amount: {opportunity.amount:.2f}")
        
    except Exception as e:
        # We expect this to fail in a real scenario since we're using mock data
        logger.info(f"Expected exception after adjustment: {e}")
    
    # Print the adjusted opportunity details
    logger.info(f"Price impact adjusted from {original_impact*100:.2f}% to {opportunity.estimated_price_impact*100:.2f}%")
    logger.info(f"Amount adjusted from {original_amount:.2f} to {opportunity.amount:.2f}")
    
    # Check if the adjustment was done correctly
    assert abs(opportunity.estimated_price_impact - jito_executor.max_price_impact) < 0.0001, "Price impact was not adjusted to the max threshold"
    assert opportunity.amount < original_amount, "Amount was not reduced"

if __name__ == "__main__":
    asyncio.run(test_price_impact_limiting())