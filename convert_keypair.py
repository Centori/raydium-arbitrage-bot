import json
import base64
import sys
from pathlib import Path

def convert_keypair_to_base64(keypair_path: str) -> str:
    """Convert a Solana keypair JSON file to base64 format"""
    try:
        # Read the keypair file
        with open(keypair_path, 'r') as f:
            keypair_bytes = bytes(json.load(f))
        
        # Convert to base64
        keypair_base64 = base64.b64encode(keypair_bytes).decode('utf-8')
        return keypair_base64
        
    except Exception as e:
        print(f"Error converting keypair: {e}")
        return None

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python convert_keypair.py path/to/keypair.json")
        sys.exit(1)
        
    keypair_path = sys.argv[1]
    if not Path(keypair_path).exists():
        print(f"Keypair file not found: {keypair_path}")
        sys.exit(1)
        
    base64_keypair = convert_keypair_to_base64(keypair_path)
    if base64_keypair:
        print("Add this to your .env file as JITO_AUTH_KEYPAIR_BASE64:")
        print(base64_keypair)