from jito_py_rpc import JitoRpcClient
import asyncio
import sys

async def test_jito_connection():
    """Test connection to Jito RPC"""
    try:
        # Initialize Jito client with the endpoint
        endpoint = "https://mainnet.block-engine.jito.wtf"
        print(f"\nTesting Jito RPC endpoint: {endpoint}")
        
        client = JitoRpcClient(endpoint)
        
        # Try getting tip accounts which should be public
        print("Attempting to get tip accounts...")
        tip_accounts = client.get_tip_accounts()
        
        if tip_accounts:
            print("Successfully connected to Jito RPC!")
            print(f"Found {len(tip_accounts)} tip accounts")
            return True
        else:
            print("Failed to retrieve tip accounts")
            return False
            
    except Exception as e:
        print(f"Error connecting to Jito: {str(e)}")
        return False

if __name__ == "__main__":
    result = asyncio.run(test_jito_connection())
    sys.exit(0 if result else 1)