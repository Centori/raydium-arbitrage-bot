import aiohttp
import asyncio
import csv
import os
import json
from datetime import datetime
import signal
import sys
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

class QuickTokenChecker:
    def __init__(self, token_file=None, tokens_dict=None):
        """
        Initialize the token checker with either a file path or direct token dictionary
        
        Args:
            token_file: Path to JSON file containing token addresses
            tokens_dict: Direct dictionary of token symbols to addresses
        """
        self.jupiter_base_url = "https://quote-api.jup.ag/v6/quote"
        self.raydium_base_url = "https://api.raydium.io/v2/main/price"
        self.sol_address = 'So11111111111111111111111111111111111111112'
        self.usdc_address = 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v'
        
        # Load tokens from JSON file or direct dictionary
        if token_file and os.path.exists(token_file):
            with open(token_file, 'r') as f:
                data = json.load(f)
                if isinstance(data, dict) and 'tokens' in data:
                    self.token_addresses = {
                        symbol: info['address'] 
                        for symbol, info in data['tokens'].items()
                    }
                else:
                    self.token_addresses = data
            logger.info(f"Loaded {len(self.token_addresses)} tokens from file")
        elif tokens_dict:
            self.token_addresses = tokens_dict
            logger.info(f"Loaded {len(self.token_addresses)} tokens from dictionary")
        else:
            logger.warning("No tokens loaded - please provide token_file or tokens_dict")
            self.token_addresses = {}

    async def get_with_timeout(self, session, url, timeout=5, max_retries=3, **kwargs):
        """Make a GET request with timeout and retry logic"""
        for attempt in range(max_retries):
            try:
                async with asyncio.timeout(timeout):
                    async with session.get(url, **kwargs) as response:
                        if response.status == 429:  # Rate limit hit
                            retry_after = int(response.headers.get('Retry-After', 5))
                            await asyncio.sleep(retry_after)
                            continue
                            
                        status = response.status
                        try:
                            data = await response.json()
                            return status, data
                        except Exception as e:
                            text = await response.text()
                            return status, None
                            
            except asyncio.TimeoutError:
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                continue
            except Exception as e:
                logger.debug(f"Error in get_with_timeout: {str(e)}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                continue
                
        return None, None
    
    async def get_pool_address(self, session, token_address):
        """Get pool address from DexScreener"""
        try:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
            headers = {
                'User-Agent': 'Mozilla/5.0',
                'Accept': 'application/json'
            }
            
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    pairs = data.get('pairs', [])
                    
                    # Find Raydium pair
                    for pair in pairs:
                        if pair.get('dexId') == 'raydium':
                            return {
                                'pair_address': pair.get('pairAddress'),
                                'price': float(pair.get('priceUsd', 0))
                            }
            return None
        except Exception as e:
            logger.debug(f"Error in get_pool_address: {str(e)}")
            return None

    async def check_jupiter(self, session, symbol, address):
        """Check token price on Jupiter"""
        # First get SOL/USDC price
        sol_price_params = {
            'inputMint': self.sol_address,
            'outputMint': self.usdc_address,
            'amount': '1000000000',
            'slippageBps': 50
        }
        
        sol_status, sol_data = await self.get_with_timeout(session, self.jupiter_base_url, params=sol_price_params)
        if not sol_status == 200 or not sol_data or 'outAmount' not in sol_data:
            logger.debug(f"Failed to get SOL price from Jupiter: {sol_status}")
            return False, None
            
        sol_price_usdc = float(sol_data['outAmount']) / 1e6  # Convert to decimal USDC
        
        # Get token/SOL price
        params = {
            'inputMint': address,
            'outputMint': self.sol_address,
            'amount': '1000000000',
            'slippageBps': 50
        }
        
        status, data = await self.get_with_timeout(session, self.jupiter_base_url, params=params)
        
        if status == 200 and data and 'outAmount' in data:
            sol_value = float(data['outAmount']) / float(params['amount'])
            usdc_price = (sol_value * sol_price_usdc) / 1000  # Scale factor
            
            return True, {
                'price': usdc_price
            }
        return False, None

    async def check_raydium(self, session, symbol, address):
        """Check token price on Raydium via DexScreener API"""
        pool_data = await self.get_pool_address(session, address)
        if not pool_data:
            return False, None
            
        return True, {
            'price': pool_data['price']
        }

    async def get_price_difference(self, session, symbol, address):
        """Get price difference between Raydium and Jupiter for a token"""
        try:
            raydium_available, raydium_data = await self.check_raydium(session, symbol, address)
            if raydium_available:
                await asyncio.sleep(0.1)  # Small delay between checks
                jupiter_available, jupiter_data = await self.check_jupiter(session, symbol, address)
                
                if jupiter_available and raydium_data and jupiter_data:
                    ray_price = float(raydium_data['price'])
                    jup_price = float(jupiter_data['price'])
                    
                    diff_percent = abs(ray_price - jup_price) / min(ray_price, jup_price) * 100
                    
                    # Determine buy/sell venues based on prices
                    buy_price = min(ray_price, jup_price)
                    sell_price = max(ray_price, jup_price)
                    buy_on = 'Raydium' if buy_price == ray_price else 'Jupiter'
                    sell_on = 'Jupiter' if sell_price == jup_price else 'Raydium'
                    
                    return {
                        'symbol': symbol,
                        'address': address,
                        'buy_on': buy_on,
                        'sell_on': sell_on,
                        'buy_price': buy_price,
                        'sell_price': sell_price,
                        'difference_percent': diff_percent,
                        'timestamp': datetime.now().isoformat()
                    }
        except Exception as e:
            logger.debug(f"Error checking price difference for {symbol}: {str(e)}")
            
        return None