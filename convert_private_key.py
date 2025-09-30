#!/usr/bin/env python3
"""
Script to convert base58 private key to JSON array format and update wallet
"""
import json
import base58
from solders.keypair import Keypair

def convert_and_update_wallet():
    """Convert base58 private key to JSON array and update wallet file"""
    try:
        # The base58 private key you provided
        base58_private_key = "53b7ap4XZJdz7doFMEEmiKdGixbqzzKnCLGoGT4QoCTRiAgKsLcAR128XjqFf6ap4tmwNKGSmjKTcjdYcrSWGv3S"
        
        print(f"Converting base58 private key: {base58_private_key}")
        
        # Decode base58 to bytes
        private_key_bytes = base58.b58decode(base58_private_key)
        
        print(f"Decoded to {len(private_key_bytes)} bytes")
        
        # Convert bytes to array format for JSON
        private_key_array = list(private_key_bytes)
        
        print(f"Converted to array with {len(private_key_array)} elements")
        
        # Create keypair to verify the address
        keypair = Keypair.from_bytes(private_key_bytes)
        wallet_address = str(keypair.pubkey())
        
        print(f"Wallet address from private key: {wallet_address}")
        
        # Verify this matches the expected address
        expected_address = "3ZuknncRcj8nhChyXApTqdcBp5mcqEBDsjokNs4L3V1z"
        
        if wallet_address == expected_address:
            print("✅ MATCH: Private key corresponds to the expected wallet address!")
            
            # Update the wallet file
            wallet_file_path = '/Users/lm/Desktop/raydium-arbitrage-bot/keys/wallet-keypair.json'
            
            # Backup the existing file first
            import shutil
            shutil.copy(wallet_file_path, wallet_file_path + '.backup')
            print(f"Created backup: {wallet_file_path}.backup")
            
            # Write the new private key array
            with open(wallet_file_path, 'w') as f:
                json.dump(private_key_array, f)
            
            print(f"✅ Updated wallet file: {wallet_file_path}")
            print(f"Wallet address: {wallet_address}")
            
            return True
        else:
            print("❌ ERROR: Private key does NOT correspond to the expected address")
            print(f"Expected: {expected_address}")
            print(f"Actual:   {wallet_address}")
            return False
            
    except Exception as e:
        print(f"Error converting private key: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Converting base58 private key to JSON array format...")
    convert_and_update_wallet()