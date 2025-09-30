import pytest
import asyncio
from config import Config 
from jito_executor import JitoExecutor
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction

async def test_jito_connection():
    """Test connection to TypeScript Jito service"""
    try:
        config = Config()
        jito = JitoExecutor(config)
        
        # Try to initialize
        success = await jito.initialize()
        assert success, "Failed to initialize Jito connection"
        print("Successfully initialized Jito connection")
        
        # Try getting tip accounts
        tip_accounts = jito.api_client.get_jito_tip_accounts()
        assert len(tip_accounts) > 0, "No tip accounts found"
        print(f"Found {len(tip_accounts)} tip accounts")
        
        return True
    except Exception as e:
        print(f"Test failed: {e}")
        return False

async def test_bundle_submission():
    """Test bundle submission through TypeScript service"""
    config = Config()
    jito = JitoExecutor(config)
    
    try:
        # Initialize connection
        success = await jito.initialize()
        if not success:
            print("Failed to initialize Jito connection")
            return False
        
        # Create test transaction (a simple empty one for testing)
        test_tx = VersionedTransaction.default()
        
        # Submit bundle
        bundle_id = await jito.submit_transactions([test_tx])
        assert bundle_id is not None, "Failed to get bundle ID"
        print(f"Successfully submitted bundle. ID: {bundle_id}")
        return True
            
    except Exception as e:
        print(f"Bundle submission test failed: {e}")
        return False
    finally:
        await jito.close()

@pytest.mark.asyncio
async def test_next_block():
    """Test getting next block height"""
    config = Config()
    jito = JitoExecutor(config)
    
    try:
        # Initialize
        success = await jito.initialize()
        assert success, "Failed to initialize Jito connection"
        
        # Get next block
        next_block = jito.api_client.get_next_block()
        assert next_block is not None, "Failed to get next block height"
        print(f"Next block height: {next_block}")
        return True
        
    except Exception as e:
        print(f"Next block test failed: {e}")
        return False
    finally:
        await jito.close()

if __name__ == "__main__":
    print("\nTesting Jito connection...")
    asyncio.run(test_jito_connection())
    
    print("\nTesting bundle submission...")
    asyncio.run(test_bundle_submission())
    
    print("\nTesting next block fetch...")
    asyncio.run(test_next_block())