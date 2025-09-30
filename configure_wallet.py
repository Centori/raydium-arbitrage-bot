#!/usr/bin/env python3
"""
Script to help convert various Solana private key formats to the correct format for the bot
"""
import os
import base58
import binascii
import json
from solders.keypair import Keypair
from dotenv import load_dotenv

def detect_and_convert_private_key(private_key_input):
    """Detect the format of the private key and convert it to base58"""
    
    print("=== PRIVATE KEY FORMAT DETECTION ===")
    print(f"Input length: {len(private_key_input)} characters")
    
    # Try different formats
    formats_to_try = []
    
    # 1. Check if it's already base58 (Phantom wallet format)
    if len(private_key_input) == 88:
        formats_to_try.append(("Base58 (88 chars - likely Phantom)", lambda: base58.b58decode(private_key_input)))
    
    # 2. Check if it's base58 but different length
    elif 80 <= len(private_key_input) <= 90:
        formats_to_try.append(("Base58 (variable length)", lambda: base58.b58decode(private_key_input)))
    
    # 3. Check if it's hex (64 chars = 32 bytes)
    elif len(private_key_input) == 64:
        formats_to_try.append(("Hex (64 chars)", lambda: binascii.unhexlify(private_key_input)))
    
    # 4. Check if it's hex (128 chars = 64 bytes, might need first 32)
    elif len(private_key_input) == 128:
        formats_to_try.append(("Hex (128 chars - first 32 bytes)", lambda: binascii.unhexlify(private_key_input[:64])))
        formats_to_try.append(("Hex (128 chars - full)", lambda: binascii.unhexlify(private_key_input)))
    
    # 5. Check if it's JSON array format
    elif private_key_input.strip().startswith('[') and private_key_input.strip().endswith(']'):
        def parse_json_array():
            data = json.loads(private_key_input)
            if len(data) == 64:
                return bytes(data[:32])  # First 32 bytes are secret key
            elif len(data) == 32:
                return bytes(data)
            else:
                raise ValueError(f"Invalid array length: {len(data)}")
        formats_to_try.append(("JSON Array", parse_json_array))
    
    # Test each format
    for format_name, converter in formats_to_try:
        try:
            print(f"\nTrying {format_name}...")
            secret_bytes = converter()
            
            # Create keypair from secret bytes
            keypair = Keypair.from_bytes(secret_bytes)
            
            # Convert to base58 for storage
            base58_key = base58.b58encode(secret_bytes).decode('ascii')
            
            print(f"✅ SUCCESS! Format: {format_name}")
            print(f"Public Key: {keypair.pubkey()}")
            print(f"Private Key (Base58): {base58_key}")
            
            return {
                'public_key': str(keypair.pubkey()),
                'private_key_base58': base58_key,
                'format_detected': format_name
            }
            
        except Exception as e:
            print(f"❌ Failed: {str(e)}")
    
    print(f"\n❌ Could not detect format. Please check your private key.")
    return None

def update_env_file(public_key, private_key_base58):
    """Update the .env file with the correct wallet information"""
    print(f"\n=== UPDATING .ENV FILE ===")
    
    # Read current .env file
    env_path = ".env"
    if not os.path.exists(env_path):
        print("❌ .env file not found")
        return False
    
    # Create backup
    import shutil
    shutil.copy(env_path, env_path + ".backup")
    print("✅ Created backup of .env file")
    
    # Update the file
    with open(env_path, 'r') as f:
        lines = f.readlines()
    
    # Update relevant lines
    updated_lines = []
    for line in lines:
        if line.startswith('SOLANA_WALLET='):
            updated_lines.append(f'SOLANA_WALLET={public_key}\n')
        elif line.startswith('SOLANA_PRIVATE_KEY='):
            updated_lines.append(f'SOLANA_PRIVATE_KEY={private_key_base58}\n')
        else:
            updated_lines.append(line)
    
    # Write back to file
    with open(env_path, 'w') as f:
        f.writelines(updated_lines)
    
    print("✅ Updated .env file successfully")
    return True

if __name__ == "__main__":
    print("=== SOLANA WALLET CONFIGURATION HELPER ===")
    print("\nThis script will help you configure your existing Solana wallet.")
    print("Please paste your private key below:")
    print("(It can be in Base58, Hex, or JSON array format)")
    
    private_key = input("\nPrivate Key: ").strip()
    
    if not private_key:
        print("❌ No private key provided")
        exit(1)
    
    result = detect_and_convert_private_key(private_key)
    
    if result:
        print(f"\n=== CONFIGURATION SUMMARY ===")
        print(f"Detected Format: {result['format_detected']}")
        print(f"Public Key: {result['public_key']}")
        print(f"Private Key (Base58): {result['private_key_base58']}")
        
        # Ask if user wants to update .env file
        response = input("\nDo you want to update your .env file with this wallet? (y/n): ").strip().lower()
        
        if response == 'y' or response == 'yes':
            if update_env_file(result['public_key'], result['private_key_base58']):
                print("\n✅ Wallet configuration complete!")
                print("\nNext steps:")
                print("1. Make sure your wallet has some SOL for gas fees")
                print("2. Run: python3 test_wallet_simple.py")
                print("3. Run: python3 test_endpoints.py")
            else:
                print("\n❌ Failed to update .env file")
        else:
            print(f"\nYou can manually update your .env file with:")
            print(f"SOLANA_WALLET={result['public_key']}")
            print(f"SOLANA_PRIVATE_KEY={result['private_key_base58']}")
    else:
        print("\n❌ Could not configure wallet. Please check your private key format.")