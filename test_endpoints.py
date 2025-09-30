import requests
import sys
import asyncio
import aiohttp
from config import Config
import json
import time

def verify_solana_rpc(endpoint):
    print("\n--- Testing Solana RPC Connection ---")
    try:
        response = requests.post(endpoint, json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getHealth",
            "params": []
        }, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            print("✓ Successfully connected to Solana RPC")
            print(f"  Response: {result}")
            return True
        else:
            print(f"✗ Error with Solana RPC: {response.text}")
            return False
    except Exception as e:
        print(f"✗ Error verifying Solana RPC: {str(e)}")
        return False

def verify_raydium_api(endpoint):
    print("\n--- Testing Raydium API Connection ---")
    try:
        url = f"{endpoint}/v2/ammV3/ammPools"
        headers = {
            'Accept': 'application/json',
            'User-Agent': 'Mozilla/5.0',
            'Origin': 'https://raydium.io'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            json_response = response.json()
            if isinstance(json_response, dict) and 'data' in json_response:
                data = json_response['data']
                if isinstance(data, list):
                    print("✓ Successfully connected to Raydium")
                    print(f"  Found {len(data)} AMM pools")
                    if len(data) > 0:
                        pool = data[0]
                        print("\n  Sample Pool Details:")
                        print(f"    ID: {pool.get('id')}")
                        print(f"    Base Token: {pool.get('baseSymbol')}")
                        print(f"    Quote Token: {pool.get('quoteSymbol')}")
                    return True
            print("✗ Unexpected response format")
            return False
        else:
            print(f"✗ Error with Raydium API: {response.text}")
            return False
    except Exception as e:
        print(f"✗ Error verifying Raydium API: {str(e)}")
        return False

async def main():
    print("=" * 60)
    print("     BLOCKCHAIN CONNECTION TESTS")
    print("=" * 60)
    
    config = Config()
    
    # Test individual services
    solana_success = verify_solana_rpc(config.RPC_ENDPOINT)
    raydium_success = verify_raydium_api(config.RAYDIUM_API_ENDPOINT)
    
    # Summary
    print("\n" + "=" * 60)
    print("     CONNECTIVITY TEST RESULTS")
    print("=" * 60)
    print(f"Solana RPC:   {'✓ Connected' if solana_success else '✗ Failed'}")
    print(f"Raydium:      {'✓ Connected' if raydium_success else '✗ Failed'}")
    print("=" * 60)
    
    # Success if all tests passed
    all_success = solana_success and raydium_success
    if all_success:
        print("\n✓ All connections successful!")
    else:
        print("\n⚠️ Some connections failed. Check errors above.")
    
    return all_success

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)