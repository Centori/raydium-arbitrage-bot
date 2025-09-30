#!/usr/bin/env python3
"""
Generate a new valid keypair and show how to update .env
"""
import os
import base58
import binascii
from solders.keypair import Keypair
from dotenv import load_dotenv

def generate_new_keypair():
    print("=== GENERATING NEW VALID KEYPAIR ===")
    
    # Generate new keypair
    keypair = Keypair()
    
    # Get the secret key bytes
    secret_bytes = bytes(keypair)[:32]  # First 32 bytes are the secret key
    
    # Convert to different formats
    base58_key = base58.b58encode(secret_bytes).decode('ascii')
    hex_key = binascii.hexlify(secret_bytes).decode('ascii')
    
    print(f"Public Key: {keypair.pubkey()}")
    print(f"Private Key (Base58): {base58_key}")
    print(f"Private Key (Hex): {hex_key}")
    
    print("\n=== UPDATE YOUR .ENV FILE ===")
    print("Replace your current SOLANA_PRIVATE_KEY with either:")
    print(f"SOLANA_PRIVATE_KEY={base58_key}")
    print("OR")
    print(f"SOLANA_PRIVATE_KEY={hex_key}")
    
    return base58_key

def test_existing_keypair_file():
    """Check if there's a valid keypair file"""
    keypair_path = "/Users/lm/Desktop/raydium-arbitrage-bot/keys/wallet-keypair.json"
    if os.path.exists(keypair_path):
        try:
            import json
            with open(keypair_path, 'r') as f:
                keypair_data = json.load(f)
            
            # Convert from array format to bytes
            if isinstance(keypair_data, list) and len(keypair_data) == 64:
                secret_key = bytes(keypair_data[:32])
                keypair = Keypair.from_bytes(secret_key)
                
                base58_key = base58.b58encode(secret_key).decode('ascii')
                hex_key = binascii.hexlify(secret_key).decode('ascii')
                
                print(f"\n=== FOUND EXISTING KEYPAIR FILE ===")
                print(f"Public Key: {keypair.pubkey()}")
                print(f"You can use this in your .env:")
                print(f"SOLANA_PRIVATE_KEY={base58_key}")
                
                return base58_key
        except Exception as e:
            print(f"Error reading existing keypair file: {e}")
    
    return None

if __name__ == "__main__":
    # First try to use existing keypair file
    existing_key = test_existing_keypair_file()
    
    if not existing_key:
        # Generate new keypair
        new_key = generate_new_keypair()
        
        print(f"\n=== NEXT STEPS ===")
        print("1. Update your .env file with the new private key")
        print("2. Fund the wallet with some SOL for gas fees")
        print("3. Run the bot tests again")