import asyncio
import pytest
from config import Config
from jito_executor import JitoExecutor
from wallet import WalletManager
from solders.keypair import Keypair
from solana.transaction import Transaction
from solders.system_program import TransferParams, transfer
from solders.pubkey import Pubkey
import base64
import os
from dotenv import load_dotenv
from unittest.mock import patch, AsyncMock, MagicMock

async def test_alchemy_jito_connection():
    """Test Alchemy RPC and Jito connection with base64 keypair"""
    config = Config()
    jito = JitoExecutor(config)
    
    try:
        # Test initialization with base64 keypair
        success = await jito.initialize()
        assert success, "Failed to initialize Jito connection"
        print("Successfully initialized Jito connection")
        
        # Test account data fetching through Alchemy
        test_account = "11111111111111111111111111111111"  # System program account
        account_data = await jito.get_account_data(test_account)
        assert account_data is not None, "Failed to fetch account data through Alchemy"
        print("Successfully fetched account data through Alchemy")
        
        return True
    except Exception as e:
        print(f"Test failed: {e}")
        return False
    finally:
        await jito.close()

async def test_bundle_submission():
    """Test bundle submission with properly configured auth"""
    config = Config()
    jito = JitoExecutor(config)
    
    try:
        # Initialize connection
        success = await jito.initialize()
        if not success:
            print("Failed to initialize Jito connection")
            return False
        
        # Create test transaction
        sender = Keypair()
        recipient = Pubkey.from_string("11111111111111111111111111111111")
        
        tx = Transaction()
        transfer_ix = transfer(
            TransferParams(
                from_pubkey=sender.pubkey(),
                to_pubkey=recipient,
                lamports=1000
            )
        )
        tx.add(transfer_ix)
        tx.sign(sender)
        
        # Submit bundle
        bundle_id = await jito.submit_bundle([tx])
        if bundle_id:
            print(f"Successfully submitted bundle. ID: {bundle_id}")
            return True
        else:
            print("Failed to submit bundle")
            return False
            
    except Exception as e:
        print(f"Bundle submission test failed: {e}")
        return False
    finally:
        await jito.close()

@pytest.mark.asyncio
@patch('wallet.AsyncClient')
async def test_jito_bundle_submission(mock_async_client):
    """Test bundle submission with mocked Jito client"""
    # Setup mock client
    mock_instance = AsyncMock()
    mock_instance.get_balance.return_value = 1000000
    mock_async_client.return_value = mock_instance
    
    # Override config validation
    with patch.object(Config, '__post_init__', return_value=None):
        config = Config()
        wallet = WalletManager(config)
        jito = JitoExecutor(config)
        
        # Mock the Jito client
        mock_jito_client = AsyncMock()
        mock_jito_client.send_bundle.return_value = {"bundleUuid": "test-bundle-123"}
        jito._jito_client = mock_jito_client
        
        try:
            # Create test transaction
            recipient = Pubkey.from_string("11111111111111111111111111111111")
            tx = Transaction()
            transfer_ix = transfer(
                TransferParams(
                    from_pubkey=wallet.keypair.pubkey(),
                    to_pubkey=recipient,
                    lamports=1000
                )
            )
            tx.add(transfer_ix)
            tx.sign(wallet.keypair)
            
            # Submit bundle
            bundle_id = await jito.submit_bundle([tx])
            assert bundle_id == "test-bundle-123", "Bundle submission failed"
            
            # Verify bundle was submitted
            mock_jito_client.send_bundle.assert_called_once()
            print(f"Successfully submitted bundle. ID: {bundle_id}")
            
        except Exception as e:
            pytest.fail(f"Test failed: {e}")
        finally:
            await jito.close()

@pytest.mark.asyncio
async def test_jito_account_data():
    """Test fetching account data through Alchemy"""
    with patch.object(Config, '__post_init__', return_value=None):
        config = Config()
        jito = JitoExecutor(config)
        
        # Mock Alchemy client
        mock_response = MagicMock()
        mock_response.value = MagicMock()
        mock_response.value.data = ["SGVsbG8gV29ybGQ="]  # "Hello World" in base64
        
        with patch.object(jito.alchemy_client, 'get_account_info', 
                         return_value=mock_response):
            account_data = await jito.get_account_data("11111111111111111111111111111111")
            assert account_data is not None, "Failed to fetch account data"
            print("Successfully fetched account data")

if __name__ == "__main__":
    print("\nTesting Jito bundle submission...")
    asyncio.run(test_jito_bundle_submission())
    
    print("\nTesting account data fetching...")
    asyncio.run(test_jito_account_data())