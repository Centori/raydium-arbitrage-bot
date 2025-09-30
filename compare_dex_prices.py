#!/usr/bin/env python3
"""
DEX Price Comparison Tool for Solana

This script compares SOL/token prices across multiple DEXes to identify
arbitrage opportunities with detailed price differences in USD and percentages.
"""

import asyncio
import json
import time
import os
import requests
import argparse
from typing import Dict, List, Tuple, Optional
from tabulate import tabulate
from dataclasses import dataclass
import backoff

# Token metadata for price calculation
SOL_ADDRESS = "So11111111111111111111111111111111111111112"
USDC_ADDRESS = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDT_ADDRESS = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"

# Constants
SOL_PRICE_USD = 100  # Default SOL price in USD, will be updated during execution

# Use public endpoints directly
# Updated API endpoints
JUPITER_API = "https://quote-api.jup.ag/v6"
JUPITER_PRICE_API = "https://price.jup.ag/v6/price"
RAYDIUM_API = "https://api.raydium.io/v2"
ORCA_API = "https://api.orca.so"  # Example, may need adjustment
SOLANA_RPC = "https://api.mainnet-beta.solana.com"

# Error codes and their meanings
ERROR_CODES = {
    "0x1771": "Slippage tolerance exceeded (final amount < minimum amount)"
}

@dataclass
class Token:
    address: str
    symbol: str
    decimals: int

@dataclass
class PoolData:
    id: str
    address: str
    base_token: Token
    quote_token: Token
    base_amount: float
    quote_amount: float
    liquidity: float

class DexPriceComparer:
    """Tool for comparing token prices across different DEXes"""
    
    def __init__(self, max_tokens=10, min_liquidity=50000):
        self.dex_prices = {}
        self.token_metadata = {}
        self.sol_price_usd = SOL_PRICE_USD
        self.session = requests.Session()
        # Maximum number of tokens to analyze (to prevent API rate limits)
        self.max_tokens = max_tokens
        # Minimum liquidity in USD to consider a token
        self.min_liquidity = min_liquidity
        # Save all SOL pairs found
        self.all_sol_pairs = []
        
        # Use a more up-to-date User-Agent to avoid being blocked
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
        })
        
    @backoff.on_exception(backoff.expo, 
                         (requests.exceptions.RequestException, 
                          json.JSONDecodeError),
                         max_tries=3)
    async def update_sol_price(self):
        """Update current SOL price in USD using Jupiter API with retry logic"""
        try:
            # Try multiple sources for SOL price
            # First try CoinGecko as it's more reliable
            url = "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd"
            response = self.session.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if 'solana' in data and 'usd' in data['solana']:
                    self.sol_price_usd = data['solana']['usd']
                    print(f"Updated SOL price from CoinGecko: ${self.sol_price_usd:.2f}")
                    return self.sol_price_usd
            
            # Fallback to Jupiter price API
            url = f"{JUPITER_PRICE_API}?ids={SOL_ADDRESS}&vsToken={USDC_ADDRESS}"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if 'data' in data and SOL_ADDRESS in data.get('data', {}):
                self.sol_price_usd = data['data'][SOL_ADDRESS]['price']
                print(f"Updated SOL price from Jupiter: ${self.sol_price_usd:.2f}")
            return self.sol_price_usd
        except requests.exceptions.Timeout:
            print("Timeout while fetching SOL price, using default")
            return None
        except requests.exceptions.HTTPError as e:
            print(f"HTTP error updating SOL price: {e.response.status_code}")
            return None
        except Exception as e:
            print(f"Error updating SOL price: {str(e)}")
            return None
            
    @backoff.on_exception(backoff.expo, 
                         requests.exceptions.RequestException,
                         max_tries=3)
    async def fetch_raydium_pools(self) -> Dict[str, PoolData]:
        """Fetch Raydium pools and organize them by token pair with retry logic"""
        pools_by_pair = {}
        
        try:
            print("Fetching Raydium pools...")
            url = f"{RAYDIUM_API}/main/pairs"
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            pairs_data = response.json()
            
            print(f"Fetched {len(pairs_data)} Raydium pools")
            
            for pair in pairs_data:
                if not isinstance(pair, dict):
                    continue
                    
                # Create token objects
                base_token = Token(
                    address=pair.get('baseMint', ''),
                    symbol=pair.get('baseSymbol', 'UNKNOWN'),
                    decimals=pair.get('baseDecimals', 9)
                )
                
                quote_token = Token(
                    address=pair.get('quoteMint', ''),
                    symbol=pair.get('quoteSymbol', 'UNKNOWN'),
                    decimals=pair.get('quoteDecimals', 9)
                )
                
                # Always put SOL first if it's part of the pair
                if base_token.address == SOL_ADDRESS or quote_token.address == SOL_ADDRESS:
                    if quote_token.address == SOL_ADDRESS:
                        # Swap to ensure SOL is base
                        base_token, quote_token = quote_token, base_token
                        base_amount = float(pair.get('quoteVolume', 0))
                        quote_amount = float(pair.get('baseVolume', 0))
                    else:
                        base_amount = float(pair.get('baseVolume', 0))
                        quote_amount = float(pair.get('quoteVolume', 0))
                    
                    # Track all SOL pairs for dynamic analysis
                    liquidity_usd = float(pair.get('liquidity', 0))
                    self.all_sol_pairs.append({
                        'name': f"SOL/{quote_token.symbol}",
                        'base': SOL_ADDRESS,
                        'quote': quote_token.address,
                        'symbol': quote_token.symbol,
                        'liquidity': liquidity_usd,
                        'volume': float(pair.get('volume', 0)) 
                    })
                        
                    pair_key = f"{base_token.symbol}/{quote_token.symbol}"
                    
                    pool = PoolData(
                        id=pair.get('ammId', ''),
                        address=pair.get('ammId', ''),
                        base_token=base_token,
                        quote_token=quote_token,
                        base_amount=base_amount,
                        quote_amount=quote_amount,
                        liquidity=float(pair.get('liquidity', 0))
                    )
                    
                    pools_by_pair[pair_key] = pool
                    
                    # Store token metadata
                    self.token_metadata[base_token.address] = {
                        'symbol': base_token.symbol,
                        'decimals': base_token.decimals
                    }
                    self.token_metadata[quote_token.address] = {
                        'symbol': quote_token.symbol,
                        'decimals': quote_token.decimals
                    }
            
            return pools_by_pair
            
        except requests.exceptions.Timeout:
            print("Timeout while fetching Raydium pools")
            return {}
        except Exception as e:
            print(f"Error fetching Raydium pools: {str(e)}")
            return {}
    
    def get_top_sol_pairs(self):
        """Get top SOL trading pairs based on liquidity and volume"""
        if not self.all_sol_pairs:
            return []
            
        # Sort by liquidity (descending)
        sorted_pairs = sorted(self.all_sol_pairs, key=lambda x: x.get('liquidity', 0), reverse=True)
        
        # Filter by minimum liquidity
        filtered_pairs = [p for p in sorted_pairs if p.get('liquidity', 0) >= self.min_liquidity]
        
        # Limit to max tokens
        return filtered_pairs[:self.max_tokens]
            
    def calculate_raydium_price(self, pool: PoolData) -> float:
        """Calculate token price from Raydium pool data"""
        try:
            if pool.base_amount == 0:
                return 0
                
            # Price = quote/base
            return pool.quote_amount / pool.base_amount
        except Exception as e:
            print(f"Error calculating Raydium price: {str(e)}")
            return 0
    
    @backoff.on_exception(backoff.expo, 
                         (requests.exceptions.RequestException, 
                          json.JSONDecodeError),
                         max_tries=5,  # Increased from 3 to 5
                         max_time=30)  # Maximum backoff time in seconds
    async def get_jupiter_price(self, base_address: str, quote_address: str) -> float:
        """Get token price from Jupiter API directly with retry logic"""
        try:
            # Try multiple API endpoints for Jupiter prices with custom headers
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
                'Accept': 'application/json',
                'Accept-Language': 'en-US,en;q=0.9',
                'Origin': 'https://jup.ag',
                'Referer': 'https://jup.ag/'
            }
            
            # First, try using a direct Jupiter API call
            url = f"{JUPITER_PRICE_API}?ids={base_address}&vsToken={quote_address}"
            response = self.session.get(url, timeout=15, headers=headers)  # Increased timeout
            
            # Handle specific error codes with fallback
            if response.status_code >= 500:
                print(f"Jupiter API server error ({response.status_code}), trying fallback method...")
                return await self.get_jupiter_price_via_quote(base_address, quote_address)
                
            response.raise_for_status()
            data = response.json()
            
            if 'data' in data and base_address in data.get('data', {}):
                price = data['data'][base_address]['price']
                print(f"Jupiter price for {base_address}: {price}")
                return price
                
            # If that fails, try the fallback
            return await self.get_jupiter_price_via_quote(base_address, quote_address)
                    
        except requests.exceptions.Timeout:
            print(f"Timeout getting Jupiter price for {base_address}/{quote_address}, trying fallback...")
            return await self.get_jupiter_price_via_quote(base_address, quote_address)
        except Exception as e:
            print(f"Error getting Jupiter price: {str(e)}, trying fallback...")
            return await self.get_jupiter_price_via_quote(base_address, quote_address)
            
    async def get_jupiter_price_via_quote(self, base_address: str, quote_address: str) -> float:
        """Get price using Jupiter's quote API as a fallback"""
        try:
            print("Trying to get price via Jupiter quote API...")
            url = f"{JUPITER_API}/quote?inputMint={base_address}&outputMint={quote_address}&amount=1000000000&slippageBps=50"
            
            # Use different headers that mimic a browser request
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
                'Accept': 'application/json',
                'Accept-Language': 'en-US,en;q=0.9',
                'Origin': 'https://jup.ag',
                'Referer': 'https://jup.ag/'
            }
            
            response = self.session.get(url, timeout=15, headers=headers)  # Increased timeout
            
            # If we can't get a quote, return 0
            if response.status_code != 200:
                print(f"Failed to get price via Jupiter quote API: {response.status_code}")
                return 0
                
            data = response.json()
            
            if 'outAmount' in data and 'inAmount' in data:
                # Convert the string amounts to floats and calculate the price
                in_amount = float(data['inAmount'])
                out_amount = float(data['outAmount'])
                if in_amount > 0:
                    price = out_amount / in_amount
                    print(f"Jupiter price (from quote): {price}")
                    return price
            
            return 0
        except Exception as e:
            print(f"Error getting price via Jupiter quote: {str(e)}")
            return 0
    
    @backoff.on_exception(backoff.expo, 
                         requests.exceptions.RequestException,
                         max_tries=3)        
    async def get_orca_price(self, base_address: str, quote_address: str) -> float:
        """Get token price from Orca using Jupiter price API with Orca as source"""
        try:
            # Primary method: Try to use Jupiter price API with Orca as source
            url = f"{JUPITER_PRICE_API}?ids={base_address}&vsToken={quote_address}&sources=Orca"
            response = self.session.get(url, timeout=10)
            
            # Handle HTTP errors without raising exception
            if response.status_code != 200:
                print(f"Error from Jupiter API for Orca prices: {response.status_code}")
                # Try alternate method using Jupiter quote API which includes Orca
                return await self.get_orca_price_via_jupiter_quote(base_address, quote_address)
                
            data = response.json()
            
            if 'data' in data and base_address in data.get('data', {}):
                price = data['data'][base_address].get('price', 0)
                print(f"Successfully fetched Orca price via Jupiter API: {price}")
                return price
                
            # If Jupiter API didn't return Orca prices, try using Jupiter quote API
            return await self.get_orca_price_via_jupiter_quote(base_address, quote_address)
            
        except Exception as e:
            print(f"Error getting Orca price: {str(e)}")
            # Try alternate method as a fallback
            return await self.get_orca_price_via_jupiter_quote(base_address, quote_address)
    
    async def get_orca_price_via_jupiter_quote(self, base_address: str, quote_address: str) -> float:
        """Get Orca price using Jupiter's quote API as a fallback"""
        try:
            print("Trying to get Orca price via Jupiter quote API...")
            url = f"{JUPITER_API}/quote?inputMint={base_address}&outputMint={quote_address}&amount=1000000000&slippageBps=50&onlyDirectRoutes=true&excludeDexes=Raydium,Meteora"
            response = self.session.get(url, timeout=10)
            
            # If we can't get a quote, return 0
            if response.status_code != 200:
                print(f"Failed to get Orca price via Jupiter quote API: {response.status_code}")
                return 0
                
            data = response.json()
            
            if 'outAmount' in data and 'inAmount' in data:
                # Convert the string amounts to floats and calculate the price
                in_amount = float(data['inAmount'])
                out_amount = float(data['outAmount'])
                if in_amount > 0:
                    price = out_amount / in_amount
                    print(f"Orca price (from Jupiter quote): {price}")
                    return price
            
            return 0
        except Exception as e:
            print(f"Error getting Orca price via Jupiter quote: {str(e)}")
            return 0
            
    @backoff.on_exception(backoff.expo, 
                         requests.exceptions.RequestException,
                         max_tries=3)        
    async def get_meteora_price(self, base_address: str, quote_address: str) -> float:
        """Get token price from Meteora using Jupiter price API with Meteora as source"""
        try:
            # Primary method: Try to use Jupiter price API with Meteora as source
            url = f"{JUPITER_PRICE_API}?ids={base_address}&vsToken={quote_address}&sources=Meteora"
            response = self.session.get(url, timeout=10)
            
            # Handle HTTP errors without raising exception
            if response.status_code != 200:
                print(f"Error from Jupiter API for Meteora prices: {response.status_code}")
                # Try alternate method using Jupiter quote API which includes Meteora
                return await self.get_meteora_price_via_jupiter_quote(base_address, quote_address)
                
            data = response.json()
            
            if 'data' in data and base_address in data.get('data', {}):
                price = data['data'][base_address].get('price', 0)
                print(f"Successfully fetched Meteora price via Jupiter API: {price}")
                return price
            
            # If Jupiter API didn't return Meteora prices, try using Jupiter quote API
            return await self.get_meteora_price_via_jupiter_quote(base_address, quote_address)
            
        except Exception as e:
            print(f"Error getting Meteora price: {str(e)}")
            # Try alternate method as a fallback
            return await self.get_meteora_price_via_jupiter_quote(base_address, quote_address)
    
    async def get_meteora_price_via_jupiter_quote(self, base_address: str, quote_address: str) -> float:
        """Get Meteora price using Jupiter's quote API as a fallback"""
        try:
            print("Trying to get Meteora price via Jupiter quote API...")
            url = f"{JUPITER_API}/quote?inputMint={base_address}&outputMint={quote_address}&amount=1000000000&slippageBps=50&onlyDirectRoutes=true&excludeDexes=Raydium,Orca"
            response = self.session.get(url, timeout=10)
            
            # If we can't get a quote, return 0
            if response.status_code != 200:
                print(f"Failed to get Meteora price via Jupiter quote API: {response.status_code}")
                return 0
                
            data = response.json()
            
            if 'outAmount' in data and 'inAmount' in data:
                # Convert the string amounts to floats and calculate the price
                in_amount = float(data['inAmount'])
                out_amount = float(data['outAmount'])
                if in_amount > 0:
                    price = out_amount / in_amount
                    print(f"Meteora price (from Jupiter quote): {price}")
                    return price
            
            return 0
        except Exception as e:
            print(f"Error getting Meteora price via Jupiter quote: {str(e)}")
            return 0
    
    async def get_pair_prices(self, base_address: str, quote_address: str, 
                             base_symbol: str, quote_symbol: str) -> Dict[str, float]:
        """Get prices for a token pair across different DEXes"""
        pair_prices = {}
        pair_name = f"{base_symbol}/{quote_symbol}"
        
        # Create tasks for fetching prices from different DEXes concurrently
        jupiter_price_task = asyncio.create_task(
            self.get_jupiter_price(base_address, quote_address)
        )
        
        orca_price_task = asyncio.create_task(
            self.get_orca_price(base_address, quote_address)
        )
        
        meteora_price_task = asyncio.create_task(
            self.get_meteora_price(base_address, quote_address)
        )
        
        # Fetch Raydium pools (this fetches all pools at once)
        raydium_pools = await self.fetch_raydium_pools()
        
        # Wait for all price fetching tasks concurrently
        jupiter_price, orca_price, meteora_price = await asyncio.gather(
            jupiter_price_task, orca_price_task, meteora_price_task
        )
        
        # Add prices to the results dictionary
        if jupiter_price > 0:
            pair_prices['Jupiter'] = jupiter_price
        
        # Get Raydium price from pools
        if pair_name in raydium_pools:
            raydium_price = self.calculate_raydium_price(raydium_pools[pair_name])
            if raydium_price > 0:
                pair_prices['Raydium'] = raydium_price
        
        if orca_price > 0:
            pair_prices['Orca'] = orca_price
            
        if meteora_price > 0:
            pair_prices['Meteora'] = meteora_price
        
        # Log found prices for debugging
        print(f"Prices for {pair_name}: {pair_prices}")
        
        return pair_prices
    
    async def analyze_arbitrage(self, token_address: str, token_symbol: str) -> List[Dict]:
        """Analyze arbitrage opportunities for a SOL/token pair"""
        arbitrage_opportunities = []
        
        # Get SOL/token price across DEXes
        pair_prices = await self.get_pair_prices(
            SOL_ADDRESS, token_address, 'SOL', token_symbol
        )
        
        if len(pair_prices) < 2:
            print(f"Insufficient data for SOL/{token_symbol}: Found {len(pair_prices)} DEX prices")
            return []
        
        # Find min and max prices
        min_price = min(pair_prices.values())
        max_price = max(pair_prices.values())
        min_dex = [dex for dex, price in pair_prices.items() if price == min_price][0]
        max_dex = [dex for dex, price in pair_prices.items() if price == max_price][0]
        
        # Calculate arbitrage metrics
        price_diff = max_price - min_price
        price_diff_pct = (price_diff / min_price) * 100
        price_diff_usd = price_diff * self.sol_price_usd
        
        # Define fee estimates for different DEXes (in %)
        dex_fees = {
            'Jupiter': 0.25,  # Reduced from 0.3 as Jupiter often finds optimal routes
            'Raydium': 0.25,
            'Orca': 0.25,     # Updated from 0.3 to match current Orca fee tiers
            'Meteora': 0.2,   # Meteora often has lower fees for certain pools
        }
        
        # Calculate estimated fees - include an estimation for network fees
        buy_fee_pct = dex_fees.get(min_dex, 0.25)
        sell_fee_pct = dex_fees.get(max_dex, 0.25)
        network_fee_pct = 0.02  # Add estimated network fees (compute units, priority fees)
        total_fee_pct = buy_fee_pct + sell_fee_pct + network_fee_pct
        
        # Calculate adjusted profit percentage (after fees)
        adjusted_profit_pct = price_diff_pct - total_fee_pct
        
        # Check if arbitrage is profitable (considering fees)
        MIN_ARBITRAGE_PCT = 0.2  # Lowered from 0.5% to 0.2% to catch more opportunities
        if adjusted_profit_pct >= MIN_ARBITRAGE_PCT:
            arbitrage_opportunities.append({
                'pair': f"SOL/{token_symbol}",
                'buy_dex': min_dex,
                'buy_price': min_price,
                'sell_dex': max_dex,
                'sell_price': max_price,
                'diff_pct': price_diff_pct,
                'diff_usd': price_diff_usd,
                'fees_pct': total_fee_pct,
                'adj_profit_pct': adjusted_profit_pct,
                'profitable': True
            })
        else:
            # Include opportunity even if not immediately profitable
            arbitrage_opportunities.append({
                'pair': f"SOL/{token_symbol}",
                'buy_dex': min_dex,
                'buy_price': min_price,
                'sell_dex': max_dex,
                'sell_price': max_price,
                'diff_pct': price_diff_pct,
                'diff_usd': price_diff_usd,
                'fees_pct': total_fee_pct,
                'adj_profit_pct': adjusted_profit_pct,
                'profitable': False
            })
            
        # Save price data for historical analysis
        await self.save_price_data(token_address, token_symbol, pair_prices)
        
        return arbitrage_opportunities
        
    async def save_price_data(self, token_address: str, token_symbol: str, prices: Dict[str, float]):
        """Save price data to file for historical analysis"""
        try:
            timestamp = int(time.time())
            date_str = time.strftime("%Y-%m-%d")
            
            # Create directory if it doesn't exist
            os.makedirs("data/price_history", exist_ok=True)
            
            # Create file path for the current date
            filepath = f"data/price_history/{date_str}_{token_symbol}.json"
            
            # Read existing data if file exists
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    data = json.load(f)
            else:
                data = []
            
            # Add new price entry
            entry = {
                "timestamp": timestamp,
                "time": time.strftime("%H:%M:%S"),
                "token": token_symbol,
                "address": token_address,
                "prices": prices,
                "sol_price_usd": self.sol_price_usd
            }
            
            data.append(entry)
            
            # Save updated data
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
                
            # Keep only the last 1000 entries to avoid huge files
            if len(data) > 1000:
                data = data[-1000:]
                with open(filepath, 'w') as f:
                    json.dump(data, f, indent=2)
                    
        except Exception as e:
            print(f"Error saving price data: {str(e)}")
            
    async def analyze_price_trends(self, token_symbol: str):
        """Analyze price trends for a specific token"""
        try:
            date_str = time.strftime("%Y-%m-%d")
            filepath = f"data/price_history/{date_str}_{token_symbol}.json"
            
            if not os.path.exists(filepath):
                return None
                
            with open(filepath, 'r') as f:
                data = json.load(f)
                
            if len(data) < 10:  # Need enough data points for analysis
                return None
                
            # Analyze price spread over time
            spreads = []
            for entry in data:
                prices = entry.get('prices', {})
                if len(prices) >= 2:
                    min_price = min(prices.values())
                    max_price = max(prices.values())
                    spread_pct = ((max_price - min_price) / min_price) * 100
                    spreads.append(spread_pct)
            
            if not spreads:
                return None
                
            # Calculate statistics
            avg_spread = sum(spreads) / len(spreads)
            max_spread = max(spreads)
            min_spread = min(spreads)
            
            # Calculate volatility (standard deviation of spreads)
            variance = sum((x - avg_spread) ** 2 for x in spreads) / len(spreads)
            volatility = variance ** 0.5
            
            return {
                "token": token_symbol,
                "data_points": len(data),
                "avg_spread_pct": avg_spread,
                "max_spread_pct": max_spread,
                "min_spread_pct": min_spread,
                "volatility": volatility,
                "current_vs_avg": spreads[-1] / avg_spread if spreads else 1.0
            }
        except Exception as e:
            print(f"Error analyzing price trends: {str(e)}")
            return None

    def format_opportunities(self, opportunities: List[Dict]) -> str:
        """Format arbitrage opportunities for display"""
        if not opportunities:
            return "No arbitrage opportunities found."
            
        # Sort by adjusted profit percentage (descending)
        opportunities.sort(key=lambda x: x['adj_profit_pct'], reverse=True)
        
        table_data = []
        for opp in opportunities:
            status = "✅ PROFITABLE" if opp['profitable'] else "❌ TOO SMALL"
            table_data.append([
                opp['pair'],
                f"{opp['buy_dex']} (${opp['buy_price']:.6f})",
                f"{opp['sell_dex']} (${opp['sell_price']:.6f})",
                f"{opp['diff_pct']:.2f}%",
                f"${opp['diff_usd']:.6f}",
                f"{opp['fees_pct']:.2f}%",
                f"{opp['adj_profit_pct']:.2f}%",
                status
            ])
        
        return tabulate(
            table_data, 
            headers=["Pair", "Buy DEX", "Sell DEX", "Diff %", "Diff USD", "Est. Fees", "Adj. Profit", "Status"],
            tablefmt="pretty"
        )
    
    def get_transaction_error_info(self, error_code):
        """Get human-readable information about transaction error codes"""
        if error_code in ERROR_CODES:
            return ERROR_CODES[error_code]
        return "Unknown error code"
        
    async def get_execution_tips(self, pair_name, price_diff_pct):
        """Generate execution tips based on the arbitrage opportunity"""
        tips = []
        
        # Add relevant execution tips based on the price differential
        if price_diff_pct > 5.0:
            tips.append("⚠️ High price difference may indicate price impact - consider reducing trade size")
            
        tips.append(f"✅ Use dynamicComputeUnitLimit: true for efficient execution")
        tips.append(f"✅ Set prioritizationFeeLamports: \"auto\" to adjust for network congestion")
        tips.append(f"✅ Consider setting slippage to at least {min(price_diff_pct * 0.3, 1.0):.2f}%")
        
        if price_diff_pct < 1.0:
            tips.append("⚠️ Small price difference - execution must be very efficient")
            
        return tips
        
    async def save_all_token_data(self):
        """Save all SOL-based token data to a file for reference"""
        try:
            if not self.all_sol_pairs:
                return
                
            # Create directory if it doesn't exist
            os.makedirs("data", exist_ok=True)
            
            # Save data to file
            filepath = "data/sol_tokens.json"
            
            # Sort by liquidity
            sorted_pairs = sorted(self.all_sol_pairs, key=lambda x: x.get('liquidity', 0), reverse=True)
            
            data = {
                "timestamp": int(time.time()),
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "total_tokens": len(sorted_pairs),
                "tokens": sorted_pairs
            }
            
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
                
            print(f"Saved {len(sorted_pairs)} SOL-based tokens to {filepath}")
                
        except Exception as e:
            print(f"Error saving token data: {str(e)}")

async def main():
    """Main function to compare prices and identify arbitrage"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='SOL-based token arbitrage finder')
    parser.add_argument('--max-tokens', type=int, default=20, 
                        help='Maximum number of tokens to analyze (default: 20)')
    parser.add_argument('--min-liquidity', type=int, default=50000, 
                        help='Minimum liquidity in USD to consider a token (default: 50000)')
    parser.add_argument('--manual-tokens', action='store_true',
                        help='Use manual token list instead of auto-detecting')
    args = parser.parse_args()
    
    comparer = DexPriceComparer(max_tokens=args.max_tokens, min_liquidity=args.min_liquidity)
    
    try:
        # Update SOL price in USD
        sol_price = await comparer.update_sol_price()
        
        # If we couldn't get SOL price, use a fallback value to continue
        if sol_price is None:
            print("Warning: Using fallback SOL price value. Results may be inaccurate.")
        
        print("\nAnalyzing token pairs for arbitrage opportunities...\n")
        all_opportunities = []
        
        # Fetch Raydium pools first to get all SOL-based tokens
        await comparer.fetch_raydium_pools()
        
        # Save all token data for reference
        await comparer.save_all_token_data()
        
        if args.manual_tokens:
            # Define token pairs to analyze (manual list)
            token_pairs = [
                {"name": "SOL/USDC", "base": SOL_ADDRESS, "quote": USDC_ADDRESS},
                {"name": "SOL/USDT", "base": SOL_ADDRESS, "quote": USDT_ADDRESS},
                {"name": "SOL/BONK", "base": SOL_ADDRESS, "quote": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"},
                {"name": "SOL/JTO", "base": SOL_ADDRESS, "quote": "jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL"},
                {"name": "SOL/JUP", "base": SOL_ADDRESS, "quote": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN"},
                {"name": "SOL/RNDR", "base": SOL_ADDRESS, "quote": "rndrizKT3MK1iimdxRdWabcF7Zg7AR5T3nFH9zSQpQE"},
                {"name": "SOL/WIF", "base": SOL_ADDRESS, "quote": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"},
                {"name": "SOL/PYTH", "base": SOL_ADDRESS, "quote": "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3"},
                {"name": "SOL/SHDW", "base": SOL_ADDRESS, "quote": "SHDWyBxihqiCj6YekG2GUr7wqKLeLAMK1gHZck9pL6y"},
            ]
        else:
            # Get dynamically discovered tokens from Raydium pools
            token_pairs = comparer.get_top_sol_pairs()
            print(f"Analyzing {len(token_pairs)} SOL-based tokens with highest liquidity...")
        
        # Analyze each token pair
        for pair in token_pairs:
            base_address = pair['base'] if isinstance(pair, dict) else SOL_ADDRESS
            quote_address = pair['quote'] if isinstance(pair, dict) else pair
            token_symbol = pair['symbol'] if isinstance(pair, dict) and 'symbol' in pair else pair['name'].split('/')[1]
            
            # Only analyze SOL pairs
            if base_address == SOL_ADDRESS:
                opportunities = await comparer.analyze_arbitrage(
                    quote_address, token_symbol
                )
                all_opportunities.extend(opportunities)
        
        # Display arbitrage opportunities
        print(comparer.format_opportunities(all_opportunities))
        
        # For profitable opportunities, display execution tips
        profitable_opportunities = [o for o in all_opportunities if o['profitable']]
        if profitable_opportunities:
            print("\n\n=== Execution Tips for Profitable Opportunities ===")
            for opp in profitable_opportunities:
                print(f"\n{opp['pair']} ({opp['buy_dex']} → {opp['sell_dex']}):")
                tips = await comparer.get_execution_tips(opp['pair'], opp['diff_pct'])
                for tip in tips:
                    print(f"  {tip}")
            
            print("\nCommon Error Codes:")
            print(f"  0x1771: {comparer.get_transaction_error_info('0x1771')}")
        elif len(all_opportunities) == 0:
            print("\nTroubleshooting Tips:")
            print("  1. Check your internet connection - multiple API endpoints are failing")
            print("  2. Jupiter API (price.jup.ag) may be experiencing issues - try again later")
            print("  3. Try using a VPN if API access is geo-restricted")
            print("  4. Consider adding retry logic with longer timeouts")
            print("  5. Run 'curl https://price.jup.ag/v6/price?ids=So11111111111111111111111111111111111111112&vsToken=EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v' to test Jupiter API directly")
        
        print(f"\nAnalyzed {len(token_pairs)} SOL-based tokens across multiple DEXes")
        print(f"Found {len(all_opportunities)} arbitrage opportunities, {len(profitable_opportunities)} potentially profitable")
        
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())