#!/usr/bin/env python3
"""
Script to verify wallet address from private key
"""
import json
from solders.keypair import Keypair
from solders.pubkey import Pubkey

def verify_wallet_address():
    """Verify the wallet address from the private key"""
    try:
        # Read the private key file
        with open('/Users/lm/Desktop/raydium-arbitrage-bot/keys/wallet-keypair.json', 'r') as f:
            secret_key_array = json.load(f)
        
        print(f"Loaded private key array with {len(secret_key_array)} elements")
        
        # Convert to bytes
        secret_key_bytes = bytes(secret_key_array)
        
        # Create keypair from secret key
        keypair = Keypair.from_bytes(secret_key_bytes)
        
        # Get the public key (wallet address)
        wallet_address = str(keypair.pubkey())
        
        print(f"Wallet address from private key: {wallet_address}")
        
        # Compare with the provided address
        expected_address = "3ZuknncRcj8nhChyXApTqdcBp5mcqEBDsjokNs4L3V1z"
        
        if wallet_address == expected_address:
            print("✅ MATCH: The private key corresponds to the expected wallet address!")
            return True
        else:
            print("❌ NO MATCH: The private key does NOT correspond to the expected address")
            print(f"Expected: {expected_address}")
            print(f"Actual:   {wallet_address}")
            return False
            
    except Exception as e:
        print(f"Error verifying wallet address: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Verifying wallet address from private key...")
    verify_wallet_address()