import pytest
import asyncio
from config import Config
from raydium_pools import RaydiumPoolFetcher

@pytest.mark.asyncio
async def test_raydium_pool_fetch():
    # RAY-USDC pool address (v4)
    pool_address = "7quYw4f4dBPJw3qYyTbeFb5NfYbJyRYkBHGZp9R7JIj5"
    
    config = Config()
    fetcher = RaydiumPoolFetcher(config)
    
    try:
        # Test single pool fetch
        print(f"\nFetching pool data for {pool_address}...")
        pool_data = await fetcher.get_pool_data(pool_address)
        assert pool_data is not None, "Failed to fetch pool data"
        
        print("\nPool data details:")
        print(f"Version: {pool_data.version}")
        print(f"Base Token Mint: {pool_data.base_token_mint}")
        print(f"Quote Token Mint: {pool_data.quote_token_mint}")
        print(f"LP Mint: {pool_data.lp_mint}")
        print(f"Base Amount: {pool_data.base_amount_without_decimals}")
        print(f"Quote Amount: {pool_data.quote_amount_without_decimals}")
        print(f"Fee Rate: {pool_data.fee_rate}")
        
        # Test multiple pools fetch
        pools = [
            pool_address,
            "EJwZgeZrdC8TXTQbQBoL6bfuAnFUUy1PVCMB4DYPzVaS"  # USDC-USDT pool
        ]
        
        print("\nFetching multiple pools...")
        multi_pool_data = await fetcher.get_multiple_pools(pools)
        assert len(multi_pool_data) > 0, "Failed to fetch multiple pools"
        print(f"\nSuccessfully fetched {len(multi_pool_data)} pools")
        
    except Exception as e:
        pytest.fail(f"Test failed with exception: {str(e)}")
    finally:
        # Ensure we close the client
        await fetcher.close()