import pytest
import asyncio
from config import Config
from wallet import WalletManager
import os
from dotenv import load_dotenv
import binascii
from unittest.mock import patch, AsyncMock
from solders.keypair import Keypair

@pytest.mark.asyncio
@patch('wallet.AsyncClient')
async def test_wallet_connection(mock_client):
    """Test basic wallet connection and balance check"""
    # Setup mock
    mock_instance = AsyncMock()
    mock_instance.get_balance.return_value = 1000000  # 0.001 SOL
    mock_client.return_value = mock_instance
    
    # Override config validation temporarily
    with patch.object(Config, '__post_init__', return_value=None):
        config = Config()
        wallet = WalletManager(config)
        balance = await wallet.client.get_balance(wallet.keypair.pubkey())
        print(f"Wallet balance: {balance}")
        assert balance == 1000000

@pytest.mark.asyncio
@patch('wallet.AsyncClient')
async def test_hex_keypair_loading(mock_client):
    """Test loading wallet from hex format private key"""
    # Setup mock
    mock_instance = AsyncMock()
    mock_instance.get_balance.return_value = 1000000
    mock_client.return_value = mock_instance
    
    # Save current env var
    load_dotenv()
    original_key = os.getenv('SOLANA_PRIVATE_KEY')
    
    try:
        # Set a test hex private key
        test_hex = "4b9d989cf4748d33c35d2562c5b37d35ad7583556d8742b3f1af2a3fbf95c37fab326c3afaf9b64a79cfb5a1c55bf47bee36e92dd477953d3ad5f03fee875ee2"
        os.environ['SOLANA_PRIVATE_KEY'] = test_hex
        
        # Override config validation temporarily
        with patch.object(Config, '__post_init__', return_value=None):
            config = Config()
            wallet = WalletManager(config)
            
            # Verify the keypair was loaded correctly
            assert wallet.keypair is not None
            
            # Get keypair bytes and compare
            # Note: Using to_bytes() instead of accessing secret_key directly
            loaded_key_bytes = bytes(wallet.keypair)
            loaded_key_hex = binascii.hexlify(loaded_key_bytes).decode('ascii')
            assert test_hex.lower() == loaded_key_hex.lower(), "Loaded keypair doesn't match original hex key"
            
            # Test that we can get the balance
            balance = await wallet.client.get_balance(wallet.keypair.pubkey())
            assert balance == 1000000
            
    finally:
        # Restore original env var
        if original_key:
            os.environ['SOLANA_PRIVATE_KEY'] = original_key
        else:
            del os.environ['SOLANA_PRIVATE_KEY']

if __name__ == "__main__":
    asyncio.run(test_wallet_connection())
    asyncio.run(test_hex_keypair_loading())