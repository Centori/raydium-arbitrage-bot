import requests
from typing import Dict, Optional, List
import aiohttp
from solana.rpc.api import Client
from solana.publickey import PublicKey
import base64
import struct
import asyncio

class RaydiumMarket:
    # Raydium Program IDs
    RAYDIUM_LIQUIDITY_PROGRAM_ID = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
    RAYDIUM_AMM_PROGRAM_ID = "CLMM9tUoggJu2wagPkkqs9eFG4BWhVBZWkP1qv3Sp7tR"
    
    def __init__(self, config):
        self.config = config
        self.amm_pools_endpoint = f"{config.RAYDIUM_API_ENDPOINT}/v2/ammV3/ammPools"
        self.client = Client(config.RPC_ENDPOINT)
        self.headers = {
            'Accept': 'application/json',
            'User-Agent': 'Mozilla/5.0',
            'Origin': 'https://raydium.io'
        }
    
    async def fetch_market_info_async(self) -> Optional[List[Dict]]:
        """Fetch market info from Raydium API"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.amm_pools_endpoint, headers=self.headers) as response:
                    if response.status == 200:
                        json_response = await response.json()
                        if isinstance(json_response, dict) and 'data' in json_response:
                            data = json_response['data']
                            if isinstance(data, list):
                                print(f"Successfully fetched {len(data)} AMM pools")
                                return data
                        print("Unexpected response format")
                        return None
                    else:
                        print(f"Error fetching AMM pools: {response.status}")
                        return None
        except Exception as e:
            print(f"Error in fetch_market_info_async: {str(e)}")
            return None
    
    async def fetch_pools_async(self) -> Optional[List[Dict]]:
        """Fetch pool information from AMM V3 pools endpoint"""
        return await self.fetch_market_info_async()  # Use the same endpoint since it contains pool info
    
    async def _get_program_accounts_async(self, program_id: str):
        """Helper method to fetch program accounts asynchronously"""
        try:
            response = await self.client.get_program_accounts(
                PublicKey(program_id),
                encoding="base64",
            )
            return response.value
        except Exception as e:
            print(f"Error fetching program accounts: {e}")
            return None
    
    def _parse_pool_data(self, data: bytes) -> Optional[Dict]:
        """Parse the raw pool data from the blockchain"""
        try:
            # Decode base64 data
            raw_data = base64.b64decode(data[0])
            
            # Pool data structure (based on Raydium's layout)
            # You may need to adjust these offsets based on actual data structure
            return {
                "lp_mint": str(PublicKey(raw_data[0:32])),
                "token_a_mint": str(PublicKey(raw_data[32:64])),
                "token_b_mint": str(PublicKey(raw_data[64:96])),
                "token_a_vault": str(PublicKey(raw_data[96:128])),
                "token_b_vault": str(PublicKey(raw_data[128:160])),
                "fees_vault": str(PublicKey(raw_data[160:192])),
            }
        except Exception as e:
            print(f"Pool parse error: {e}")
            return None
    
    def _parse_market_data(self, data: bytes) -> Optional[Dict]:
        """Parse the raw market data from the blockchain"""
        try:
            # Decode base64 data
            raw_data = base64.b64decode(data[0])
            return {
                "market_id": str(raw_data[:32])
            }
        except Exception as e:
            print(f"Market parse error: {e}")
            return None