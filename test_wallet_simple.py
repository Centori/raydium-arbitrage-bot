#!/usr/bin/env python3
"""
Simple wallet verification script to test private key loading
"""
import os
from dotenv import load_dotenv
import base58
import binascii
from solders.keypair import Keypair

def test_wallet_loading():
    load_dotenv()
    
    print("=== WALLET VERIFICATION TEST ===")
    
    private_key = os.getenv('SOLANA_PRIVATE_KEY')
    if not private_key:
        print("❌ No SOLANA_PRIVATE_KEY found in .env file")
        return False
    
    print(f"✓ Found private key in .env (length: {len(private_key)})")
    
    # Test different loading methods
    methods = [
        ("Base58", lambda pk: Keypair.from_bytes(base58.b58decode(pk))),
        ("Hex", lambda pk: Keypair.from_bytes(binascii.unhexlify(pk))),
    ]
    
    for method_name, method_func in methods:
        try:
            keypair = method_func(private_key)
            print(f"✓ {method_name} format - SUCCESS")
            print(f"  Public key: {keypair.pubkey()}")
            return True
        except Exception as e:
            print(f"❌ {method_name} format - FAILED: {str(e)}")
    
    print("❌ All wallet loading methods failed")
    return False

if __name__ == "__main__":
    test_wallet_loading()