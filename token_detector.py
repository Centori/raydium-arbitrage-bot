from typing import Dict, List, Set, Optional, Tuple
import logging
import re
import json
import time
import os
import requests
from datetime import datetime, timedelta
from config import Config
from api_client import BlockchainAPIClient, TokenInfo

logger = logging.getLogger("TokenDetector")

class TokenDetector:
    """
    Filter and detect interesting tokens for arbitrage opportunities
    with focus on SOL-based pairs and cross-DEX opportunities
    """
    
    def __init__(self, config: Config):
        self.config = config
        self.api_client = BlockchainAPIClient(config)
        
        # Common stablecoin addresses on Solana
        self.stablecoin_addresses = {
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
            "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
            "DUKWyZYQ6Zg5wLGQ34oUbpkYdym4CpD6fLpJ6PaRiy1n",  # BUSD
            "8f3iJjJz4mMvHvKQzGwPEz5C7Z5BgXDYRsVP9Q1GHwXK",  # UXD
            "7dHbWXmci3dT8UFYWYZweBLXgycu7Y3iL6trKn1Y7ARj",  # DAI
        }
        
        # SOL and SOL derivative tokens (including liquid staking derivatives)
        self.sol_tokens = {
            "So11111111111111111111111111111111111111112",  # SOL
            "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So",  # mSOL (Marinade)
            "7dHbWXmci3dT8UFYWYZweBLXgycu7Y3iL6trKn1Y7ARj",  # jitoSOL
            "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn",  # bSOL (Blaze)
            "bSo13r4TkiE4KumL71LsHTPpL2euBYLFx6h9HP3piy1",  # bSOL
            "7Q2afV64in6N6SeZsyTDDBpaCGojiMaWQvpWdm2qS1U5",  # scnSOL
            "5oVNBeEEQvYi1cX3ir8Dx5n1P7pdxydbGF2X4TxVusJm",  # stSOL (Lido)
        }
        
        # Major DEX tokens to track
        self.dex_tokens = {
            "orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE",  # ORCA
            "METAEVYgQvJS8LQTM21vV4CK4R47ePuHRKKFg5pmhQL",  # METEORA
            "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",  # RAY
            "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",  # JUP
        }
        
        # Dedicated meme coin addresses (expanded from previous popular_tokens)
        self.meme_tokens = {
            # Established meme coins with significant volume
            "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",  # BONK
            "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",  # SAMO
            "HxRELUQfvvjToVbacjr9YECdfQMUqGgPYB68jVDYxkbr",  # POPCAT
            "CAsRhmzgRx4S8AA1ViDTUP3uqcKjRrYprcoqjjgP4xj",   # CLAY
            "EchesyfXePKdLtoiZSL8pBe8Myagyy8ZRqsACNCFGnvp",  # BERN
            "dogecoin1111111111111111111111111111111111",    # DOGE
            "F9CpWoyeBJfoRB8f2pBe2ZNPbPsEE76mWZWme2QKDsxN",  # WIF
            "4ThReWAbAVZjNVgs5Ui9Pk3cZ5TYaD9u6Y89fp6EFzoF",  # BINU
            "D9bPefcLWM5rkm8UmR1PVeV7a7rky4QthMoz9ucwE2kE",  # ELEPHANT
            "9nEqaUcb16sQ3Tn1psbkWqyhPdLmfHWjKGymREjsAgTE",  # COPE
            "CpZ83dXPm1FvVBgx3FF5gXXvbJLKVPJV9MCcxbJ3henK",  # BCANDY
            "9fQjP3TCFG8M81PeHX6VLYRwH9ZJHtBcxZBT8eBuKYWF",  # BOOP
            "4tzBkLQKhAMagZMcCTBGx4yvLY3kPy6kkJQ2aJKy7znf",  # CAT
            "GsNzxJfFn6zQdJGeYsupJWzUAm57Ba7335mfXNuXns66",  # CHART
            "9WMwGcY6TcbSfy9XPpQymY26xbVP5DmhQH56zLkDYXkJ",  # WEN
        }
        
        # Popular non-meme tokens with high volume
        self.popular_tokens = {
            "kinXdEcpDQeHPEuQnqmUgtYykqKGVFq6CeVX5iAHJq6",   # KIN
            "AFbX8oGjGpmVFywbVouvhQSRmiW2aR1mohfahi4Y2AdB",  # GST
            "7i5KKsX2weiTkry7jA4ZwSuXGhs5eJBEjY8vVxR4pfRx",  # GMT
        }
        
        # ETH wrapped tokens
        self.eth_tokens = {
            "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs",  # ETH (Wormhole)
            "2FPyTwcZLUg1MDrwsyoP4D6s1tM7hAkHYRjkNb5w6Pxk",  # ETH (Sollet)
        }
        
        # Blacklisted addresses - tokens with known issues or scams
        self.blacklisted_addresses = {
            # Add any blacklisted token addresses here
        }
        
        # Common patterns in meme coin names
        self.meme_name_patterns = [
            r'dog(e|gy|go)?', r'shib(a)?', r'cat', r'pepe', r'frog',
            r'wen', r'moon', r'elon', r'mars', r'wojak', r'chad',
            r'inu', r'floki', r'rocket', r'safe', r'cum', r'baby',
            r'meme', r'food', r'poop', r'poo', r'shit', r'bull', r'bear',
            r'monkey', r'ape', r'wojak', r'chad', r'whale', r'degen'
        ]
        
        # Meme token detection sensitivity (higher = more tokens classified as memes)
        self.meme_detection_sensitivity = 0.7  # 0.0 to 1.0
        
        # Lists for pools and tokens that meet criteria
        self.valid_pool_addresses = set()
        
        # All valid tokens we'll consider for arbitrage
        self.valid_token_addresses = (
            self.stablecoin_addresses.union(self.sol_tokens)
            .union(self.dex_tokens).union(self.meme_tokens)
            .union(self.popular_tokens).union(self.eth_tokens)
        )
        
        # Token metadata cache for quicker lookups
        self.token_metadata_cache = {}
        
        # Track new pools and tokens
        self.new_pools_cache = {}
        self.new_tokens_cache = {}
        self.token_liquidity_cache = {}  # NEW: Cache for token liquidity data
        self.token_volume_cache = {}     # NEW: Cache for token volume data
        self.last_scan_time = 0
        self.scan_interval = 60 * 15  # 15 minutes between full scans
        
        # Cache file paths
        self.metadata_cache_file = os.path.join("data", "token_metadata.json")
        self.new_pools_cache_file = os.path.join("data", "new_pools.json")
        self.new_tokens_cache_file = os.path.join("data", "new_tokens.json")
        self.token_liquidity_file = os.path.join("data", "token_liquidity.json") # NEW
        self.token_volume_file = os.path.join("data", "token_volume.json") # NEW
        
        # Cross-DEX tracking (NEW)
        self.cross_dex_opportunities = {}
        self.price_divergence_threshold = 0.02  # 2% price difference threshold for cross-DEX
        
        # Load cached metadata if it exists
        self._load_cached_metadata()
        
        logger.info(f"TokenDetector initialized with {len(self.valid_token_addresses)} valid tokens")
    
    def _load_cached_metadata(self):
        """Load cached token metadata from disk"""
        try:
            if os.path.exists(self.metadata_cache_file):
                with open(self.metadata_cache_file, 'r') as f:
                    data = json.load(f)
                    for addr, info in data.items():
                        self.token_metadata_cache[addr] = TokenInfo(**info)
                logger.info(f"Loaded {len(self.token_metadata_cache)} tokens from cache")
            
            if os.path.exists(self.new_tokens_cache_file):
                with open(self.new_tokens_cache_file, 'r') as f:
                    self.new_tokens_cache = json.load(f)
                logger.info(f"Loaded {len(self.new_tokens_cache)} new tokens from cache")
            
            # NEW: Load token liquidity data
            if os.path.exists(self.token_liquidity_file):
                with open(self.token_liquidity_file, 'r') as f:
                    self.token_liquidity_cache = json.load(f)
                logger.info(f"Loaded liquidity data for {len(self.token_liquidity_cache)} tokens")
                
            # NEW: Load token volume data
            if os.path.exists(self.token_volume_file):
                with open(self.token_volume_file, 'r') as f:
                    self.token_volume_cache = json.load(f)
                logger.info(f"Loaded volume data for {len(self.token_volume_cache)} tokens")
                
        except Exception as e:
            logger.error(f"Error loading cached metadata: {e}")
    
    def _save_cached_metadata(self):
        """Save token metadata cache to disk"""
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(self.metadata_cache_file), exist_ok=True)
            
            # Convert TokenInfo objects to dictionaries
            serializable_cache = {}
            for addr, token_info in self.token_metadata_cache.items():
                if isinstance(token_info, TokenInfo):
                    serializable_cache[addr] = token_info.__dict__
                else:
                    serializable_cache[addr] = token_info
                    
            with open(self.metadata_cache_file, 'w') as f:
                json.dump(serializable_cache, f)
                
            with open(self.new_tokens_cache_file, 'w') as f:
                json.dump(self.new_tokens_cache, f)
            
            # NEW: Save token liquidity data
            with open(self.token_liquidity_file, 'w') as f:
                json.dump(self.token_liquidity_cache, f)
                
            # NEW: Save token volume data
            with open(self.token_volume_file, 'w') as f:
                json.dump(self.token_volume_cache, f)
                
            logger.info(f"Saved {len(self.token_metadata_cache)} tokens to cache")
        except Exception as e:
            logger.error(f"Error saving cached metadata: {e}")
            
    def is_token_valid(self, base_token: str, quote_token: str) -> bool:
        """
        Determine if a token pair is valid for arbitrage based on our criteria
        """
        # Skip blacklisted tokens
        if base_token in self.blacklisted_addresses or quote_token in self.blacklisted_addresses:
            logger.debug(f"Skipping blacklisted token: {base_token[:8]}.../{quote_token[:8]}...")
            return False
            
        # PRIORITY 1: Accept all SOL-based pairs
        # If either token is SOL or a SOL derivative
        is_sol_pair = (base_token in self.sol_tokens or quote_token in self.sol_tokens)
        if is_sol_pair:
            logger.debug(f"Accepting SOL-based pair: {base_token[:8]}.../{quote_token[:8]}...")
            self._add_to_valid_tokens(base_token, quote_token)
            return True
        
        # PRIORITY 2: Accept all stablecoin pairs
        is_stablecoin_pair = (base_token in self.stablecoin_addresses or 
                              quote_token in self.stablecoin_addresses)
        if is_stablecoin_pair:
            logger.debug(f"Accepting stablecoin pair: {base_token[:8]}.../{quote_token[:8]}...")
            self._add_to_valid_tokens(base_token, quote_token)
            return True
        
        # PRIORITY 3: Accept pairs with DEX tokens (potential ORCA/RAY/JUP arbitrage)
        is_dex_pair = (base_token in self.dex_tokens or quote_token in self.dex_tokens)
        if is_dex_pair:
            logger.debug(f"Accepting DEX token pair: {base_token[:8]}.../{quote_token[:8]}...")
            self._add_to_valid_tokens(base_token, quote_token)
            return True
            
        # PRIORITY 4: Accept meme token pairs - high volatility can create arbitrage opportunities
        is_meme_pair = (base_token in self.meme_tokens or quote_token in self.meme_tokens)
        if is_meme_pair:
            logger.debug(f"Accepting meme token pair: {base_token[:8]}.../{quote_token[:8]}...")
            self._add_to_valid_tokens(base_token, quote_token)
            return True
        
        # PRIORITY 5: Accept popular tokens (non-meme high volume)
        is_popular_pair = (base_token in self.popular_tokens or quote_token in self.popular_tokens)
        if is_popular_pair:
            logger.debug(f"Accepting popular token pair: {base_token[:8]}.../{quote_token[:8]}...")
            self._add_to_valid_tokens(base_token, quote_token)
            return True
        
        # PRIORITY 6: Check if it might be a new meme token we don't know yet
        base_info = self.get_token_info(base_token)
        quote_info = self.get_token_info(quote_token)
        
        if base_info and self.is_likely_meme_token(base_info):
            logger.debug(f"Accepting likely meme token: {base_token[:8]}... ({base_info.symbol})")
            self._add_to_valid_tokens(base_token, quote_token)
            return True
            
        if quote_info and self.is_likely_meme_token(quote_info):
            logger.debug(f"Accepting likely meme token: {quote_token[:8]}... ({quote_info.symbol})")
            self._add_to_valid_tokens(base_token, quote_token)
            return True
        
        # NEW: PRIORITY 7: Check for high liquidity or volume tokens using our cache
        if base_token in self.token_liquidity_cache and self.token_liquidity_cache[base_token] > 100000:  # >$100k liquidity
            logger.debug(f"Accepting high liquidity token: {base_token[:8]}...")
            self._add_to_valid_tokens(base_token, quote_token)
            return True
            
        if quote_token in self.token_liquidity_cache and self.token_liquidity_cache[quote_token] > 100000:
            logger.debug(f"Accepting high liquidity token: {quote_token[:8]}...")
            self._add_to_valid_tokens(base_token, quote_token)
            return True
            
        # NEW: PRIORITY 8: Check for cross-DEX opportunities by comparing with historical price data
        if self._has_cross_dex_opportunity(base_token, quote_token):
            logger.debug(f"Accepting potential cross-DEX pair: {base_token[:8]}.../{quote_token[:8]}...")
            self._add_to_valid_tokens(base_token, quote_token)
            return True
                
        # If we're specifically looking for cross-DEX opportunities on SOL tokens,
        # we can be more restrictive and only accept the pairs we've already identified
        logger.debug(f"Rejecting token pair: {base_token[:8]}.../{quote_token[:8]}...")
        return False
    
    def is_likely_meme_token(self, token_info: TokenInfo) -> bool:
        """
        Determine if a token is likely to be a meme token based on various characteristics
        Returns a boolean indicating whether the token is likely a meme coin
        """
        # If we already know it's a meme token
        if token_info.address in self.meme_tokens:
            return True
        
        score = 0.0
        max_score = 5.0
        
        # Check symbol and name for meme patterns
        if token_info.symbol and token_info.name:
            symbol_lower = token_info.symbol.lower()
            name_lower = token_info.name.lower()
            
            # Check for common meme coin patterns in name and symbol
            for pattern in self.meme_name_patterns:
                if re.search(pattern, symbol_lower) or re.search(pattern, name_lower):
                    score += 1.0
                    break
            
            # Check for all caps symbol (common in meme tokens)
            if token_info.symbol.isupper() and len(token_info.symbol) <= 5:
                score += 0.5
                
            # Check for excessive emojis or special characters (common in meme tokens)
            emoji_pattern = re.compile("["
                                    u"\U0001F600-\U0001F64F"  # emoticons
                                    u"\U0001F300-\U0001F5FF"  # symbols & pictographs
                                    u"\U0001F680-\U0001F6FF"  # transport & map symbols
                                    u"\U0001F700-\U0001F77F"  # alchemical symbols
                                    u"\U0001F780-\U0001F7FF"  # Geometric Shapes
                                    u"\U0001F800-\U0001F8FF"  # Supplemental Arrows-C
                                    u"\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
                                    u"\U0001FA00-\U0001FA6F"  # Chess Symbols
                                    u"\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
                                    u"\U00002702-\U000027B0"  # Dingbats
                                    "]+", flags=re.UNICODE)
            
            if emoji_pattern.search(name_lower) or emoji_pattern.search(symbol_lower):
                score += 1.0
                
            # Check for special characters and numbers in symbol
            if re.search(r'[^a-zA-Z]', token_info.symbol):
                score += 0.5
            
            # Check for obvious meme coin naming patterns
            if any(word in name_lower for word in ["moon", "safe", "elon", "doge", "shib", "inu", "pepe", "wojak"]):
                score += 1.5
                
        # Check decimals (meme coins often have unusual decimal places)
        if hasattr(token_info, 'decimals') and token_info.decimals > 9:
            score += 0.5
            
        # Calculate final probability
        probability = score / max_score
        logger.debug(f"Meme token score for {token_info.symbol}: {score}/{max_score} = {probability:.2f}")
        
        # Compare with sensitivity threshold
        return probability >= self.meme_detection_sensitivity
    
    def get_arbitrage_paths_for_meme_tokens(self) -> List[List[str]]:
        """Find potential arbitrage paths specifically for meme tokens"""
        paths = []
        
        # Priority 1: Meme token <-> SOL <-> Meme token (different meme)
        for meme1 in self.meme_tokens:
            for meme2 in self.meme_tokens:
                if meme1 == meme2:
                    continue
                    
                for sol_token in self.sol_tokens:
                    paths.append([meme1, sol_token, meme2, meme1])
        
        # Priority 2: Meme token <-> Stablecoin <-> Meme token (different meme)
        for meme1 in self.meme_tokens:
            for meme2 in self.meme_tokens:
                if meme1 == meme2:
                    continue
                    
                for stable in self.stablecoin_addresses:
                    paths.append([meme1, stable, meme2, meme1])
        
        # Priority 3: Meme <-> SOL <-> Stable <-> Meme (triangular)
        for meme in self.meme_tokens:
            for sol_token in self.sol_tokens:
                for stable in self.stablecoin_addresses:
                    paths.append([meme, sol_token, stable, meme])
        
        logger.info(f"Generated {len(paths)} potential meme token arbitrage paths")
        return paths
    
    # REPLACEMENT FOR BITQUERY API: Detect new tokens using Raydium pools
    def detect_new_tokens(self, limit: int = 50) -> List[Dict]:
        """
        Detect newly created tokens on Solana by scanning Raydium pools
        
        Args:
            limit: Maximum number of new tokens to return
            
        Returns:
            List of dictionaries containing token information
        """
        try:
            current_time = time.time()
            # Only do a full scan periodically to avoid overloading the API
            if current_time - self.last_scan_time < self.scan_interval:
                logger.debug(f"Skipping full scan, last scan was {int(current_time - self.last_scan_time)} seconds ago")
                return list(self.new_tokens_cache.values())[:limit]
            
            self.last_scan_time = current_time
            logger.info("Scanning for new tokens via Raydium pools...")
            
            # Get all Raydium pools
            pools = self.api_client.get_raydium_pools()
            
            # Track newly discovered tokens
            new_tokens = []
            seen_tokens = set(self.token_metadata_cache.keys())
            seen_tokens.update(self.new_tokens_cache.keys())
            
            # Process each pool
            for pool in pools:
                base_token = pool.base_token.address
                quote_token = pool.quote_token.address
                
                # Skip if we already have both tokens
                if base_token in seen_tokens and quote_token in seen_tokens:
                    continue
                
                # Process any new tokens we find
                for token_address, token_info in [
                    (base_token, pool.base_token), 
                    (quote_token, pool.quote_token)
                ]:
                    if token_address not in seen_tokens:
                        seen_tokens.add(token_address)
                        
                        # Store token info in our cache
                        self.token_metadata_cache[token_address] = token_info
                        
                        # Get token liquidity data (use the pool data)
                        base_usd_price = self._estimate_token_price(base_token)
                        quote_usd_price = self._estimate_token_price(quote_token)
                        
                        try:
                            base_amount = float(pool.base_amount) / (10 ** pool.base_token.decimals)
                            quote_amount = float(pool.quote_amount) / (10 ** pool.quote_token.decimals)
                            
                            base_liquidity = base_amount * base_usd_price
                            quote_liquidity = quote_amount * quote_usd_price
                            
                            # Store liquidity info
                            self.token_liquidity_cache[base_token] = base_liquidity
                            self.token_liquidity_cache[quote_token] = quote_liquidity
                            
                            # Check if it's a meme token
                            is_meme = self.is_likely_meme_token(token_info)
                            
                            # Add new token to our tracking
                            new_token = {
                                'address': token_address,
                                'symbol': token_info.symbol,
                                'name': token_info.name,
                                'decimals': token_info.decimals,
                                'discovery_time': int(current_time),
                                'liquidity_usd': base_liquidity if token_address == base_token else quote_liquidity,
                                'is_meme': is_meme
                            }
                            
                            # Store in our new tokens cache
                            self.new_tokens_cache[token_address] = new_token
                            new_tokens.append(new_token)
                            
                            # If it's a meme token, add it to our meme tokens set
                            if is_meme:
                                self.meme_tokens.add(token_address)
                                self.valid_token_addresses.add(token_address)
                                
                            logger.info(f"Discovered new token: {token_info.symbol} ({token_address[:8]}...)")
                        except Exception as e:
                            logger.error(f"Error processing token liquidity: {e}")
            
            # Save updated cache
            self._save_cached_metadata()
            
            # Sort by discovery time (newest first)
            sorted_tokens = sorted(
                new_tokens, 
                key=lambda x: x.get('discovery_time', 0), 
                reverse=True
            )
            
            logger.info(f"Detected {len(new_tokens)} new tokens")
            return sorted_tokens[:limit]
                
        except Exception as e:
            logger.error(f"Error detecting new tokens: {e}")
            return []
    
    def _estimate_token_price(self, token_address: str) -> float:
        """
        Estimate token price in USD using Jupiter API
        Falls back to known prices for stablecoins
        """
        try:
            # Default USDC address as quote
            usdc_address = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
            
            # Special cases for known tokens
            if token_address in self.stablecoin_addresses:
                return 1.0  # Stablecoins are ~$1
                
            # Try to get price from Jupiter
            price = self.api_client.get_jupiter_price(token_address, usdc_address)
            return price
        except Exception as e:
            logger.error(f"Error estimating token price: {e}")
            return 0.0
    
    def get_recent_meme_tokens(self, limit: int = 10) -> List[Dict]:
        """
        Get the most recently created meme tokens from our cache
        
        Args:
            limit: Maximum number of tokens to return
            
        Returns:
            List of dictionaries containing token information, sorted by creation time
        """
        try:
            # Get new tokens if we haven't already
            if not self.new_tokens_cache:
                self.detect_new_tokens(limit=100)
            
            # Filter for meme tokens only
            meme_tokens = [
                token for addr, token in self.new_tokens_cache.items() 
                if token.get('is_meme', False) or addr in self.meme_tokens
            ]
            
            # Sort by discovery time (newest first)
            meme_tokens.sort(key=lambda x: x.get('discovery_time', 0), reverse=True)
            
            # Take only the requested number
            recent_meme_tokens = meme_tokens[:limit]
            
            logger.info(f"Retrieved {len(recent_meme_tokens)} recent meme tokens")
            return recent_meme_tokens
            
        except Exception as e:
            logger.error(f"Error fetching recent meme tokens: {e}")
            return []
    
    # NEW: Function to track token prices across different DEXes
    def track_cross_dex_prices(self):
        """
        Track token prices across different DEXes to identify arbitrage opportunities
        """
        try:
            logger.info("Scanning for cross-DEX price differences...")
            
            # Define key tokens to monitor (SOL, meme tokens, popular tokens)
            key_tokens = list(self.sol_tokens) + list(self.meme_tokens.intersection(self.valid_token_addresses))
            key_tokens = key_tokens[:20]  # Limit to avoid API overload
            
            # Define USDC as the quote token for price comparison
            usdc = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
            
            # Check Jupiter API for each token
            for token in key_tokens:
                # Get Jupiter price as baseline
                jupiter_price = self.api_client.get_jupiter_price(token, usdc)
                
                # Check Raydium pools for the same token
                raydium_price = self._get_raydium_price(token, usdc)
                
                # If we have prices from both sources, check for divergence
                if jupiter_price > 0 and raydium_price > 0:
                    # Calculate price difference percentage
                    price_diff = abs(jupiter_price - raydium_price) / jupiter_price
                    
                    # If price difference exceeds threshold, mark as opportunity
                    if price_diff > self.price_divergence_threshold:
                        token_info = self.get_token_info(token)
                        symbol = token_info.symbol if token_info else token[:8]
                        
                        logger.info(f"Cross-DEX opportunity: {symbol} price difference: {price_diff:.2%} " +
                                   f"(Jupiter: ${jupiter_price:.6f}, Raydium: ${raydium_price:.6f})")
                        
                        # Store the opportunity
                        self.cross_dex_opportunities[token] = {
                            "token": token,
                            "symbol": symbol,
                            "jupiter_price": jupiter_price,
                            "raydium_price": raydium_price,
                            "diff_percent": price_diff * 100,
                            "timestamp": int(time.time())
                        }
            
            # Return the number of opportunities found
            return len(self.cross_dex_opportunities)
                
        except Exception as e:
            logger.error(f"Error tracking cross-DEX prices: {e}")
            return 0
    
    def _get_raydium_price(self, token_address: str, quote_address: str) -> float:
        """Get token price from Raydium pools"""
        try:
            # Get all Raydium pools
            pools = self.api_client.get_raydium_pools()
            
            # Find pools that contain both tokens
            for pool in pools:
                # Check if this pool has our token pair
                if ((pool.base_token.address == token_address and pool.quote_token.address == quote_address) or
                    (pool.base_token.address == quote_address and pool.quote_token.address == token_address)):
                    
                    # Calculate price based on pool ratio
                    if pool.base_token.address == token_address:
                        base_amount = float(pool.base_amount) / (10 ** pool.base_token.decimals)
                        quote_amount = float(pool.quote_amount) / (10 ** pool.quote_token.decimals)
                        if base_amount > 0:
                            return quote_amount / base_amount
                    else:
                        base_amount = float(pool.base_amount) / (10 ** pool.base_token.decimals)
                        quote_amount = float(pool.quote_amount) / (10 ** pool.quote_token.decimals)
                        if quote_amount > 0:
                            return base_amount / quote_amount
            
            # If we reach here, no direct pool was found
            return 0.0
            
        except Exception as e:
            logger.error(f"Error getting Raydium price: {e}")
            return 0.0
    
    def _has_cross_dex_opportunity(self, token1: str, token2: str) -> bool:
        """Check if there's a potential cross-DEX opportunity for this token pair"""
        return token1 in self.cross_dex_opportunities or token2 in self.cross_dex_opportunities
    
    def monitor_new_tokens(self, interval_seconds: int = 300):
        """
        Continuously monitor for new token creations and cross-DEX opportunities
        
        Args:
            interval_seconds: How often to check for new tokens (in seconds)
        """
        while True:
            try:
                logger.info("Scanning for new tokens and opportunities...")
                new_tokens = self.detect_new_tokens(limit=50)
                
                # Also scan for cross-DEX price differences
                cross_dex_count = self.track_cross_dex_prices()
                
                # Log any new meme tokens
                meme_tokens = [t for t in new_tokens if t.get('is_meme', False)]
                if meme_tokens:
                    logger.info(f"Found {len(meme_tokens)} new potential meme tokens:")
                    for token in meme_tokens:
                        logger.info(f"  {token['symbol']} ({token['address']}): {token['name']}")
                
                # Log any cross-DEX opportunities
                if cross_dex_count > 0:
                    logger.info(f"Found {cross_dex_count} cross-DEX arbitrage opportunities")
                
                # Sleep until next check
                time.sleep(interval_seconds)
            except Exception as e:
                logger.error(f"Error in token monitoring: {e}")
                time.sleep(60)  # Shorter sleep on error
    
    def _add_to_valid_tokens(self, *tokens):
        """Add tokens to the valid token tracking list"""
        for token in tokens:
            self.valid_token_addresses.add(token)
    
    def get_token_info(self, token_address: str) -> Optional[TokenInfo]:
        """Get token info from API client with caching"""
        # Check cache first
        if token_address in self.token_metadata_cache:
            return self.token_metadata_cache[token_address]
            
        try:
            # Try to get token info from API first
            token_info = self.api_client.get_token_info(token_address)
            if token_info:
                # Cache the result
                self.token_metadata_cache[token_address] = token_info
                return token_info
                
            # Fallback to basic info for known tokens
            if token_address in self.stablecoin_addresses:
                name = "Stablecoin"
                symbol = "STABLE"
                decimals = 6
            elif token_address in self.sol_tokens:
                name = "SOL Token"
                symbol = "SOL"
                decimals = 9
            elif token_address in self.dex_tokens:
                name = "DEX Token"
                symbol = "DEX"
                decimals = 9
            elif token_address in self.meme_tokens:
                name = "Meme Token"
                symbol = "MEME"
                decimals = 9
            elif token_address in self.popular_tokens:
                name = "Popular Token"
                symbol = "POPULAR"
                decimals = 9
            else:
                name = "Unknown Token"
                symbol = "UNKNOWN"
                decimals = 9
                
            token_info = TokenInfo(
                address=token_address,
                symbol=symbol,
                name=name,
                decimals=decimals
            )
            
            # Cache the result
            self.token_metadata_cache[token_address] = token_info
            return token_info
        except Exception as e:
            logger.error(f"Error getting token info: {e}")
            return None
    
    # NEW: Get all cross-DEX arbitrage opportunities
    def get_cross_dex_opportunities(self, min_diff_percent: float = 1.0) -> List[Dict]:
        """
        Get all current cross-DEX arbitrage opportunities
        
        Args:
            min_diff_percent: Minimum price difference percentage to include
            
        Returns:
            List of dictionaries containing opportunity information
        """
        try:
            # Make sure we have recent data
            if not self.cross_dex_opportunities:
                self.track_cross_dex_prices()
                
            # Filter opportunities by the minimum difference threshold
            opportunities = [
                opp for opp in self.cross_dex_opportunities.values()
                if opp['diff_percent'] >= min_diff_percent
            ]
            
            # Sort by price difference (highest first)
            opportunities.sort(key=lambda x: x['diff_percent'], reverse=True)
            
            return opportunities
        except Exception as e:
            logger.error(f"Error getting cross-DEX opportunities: {e}")
            return []
    
    def find_arbitrage_paths(self, token_addresses: List[str]) -> List[List[str]]:
        """Find potential arbitrage paths between tokens"""
        paths = []
        
        # Generate paths for SOL/Stablecoin arbitrage (highest priority)
        # SOL -> Stablecoin -> SOL paths
        for sol_token in self.sol_tokens:
            if sol_token not in token_addresses:
                continue
                
            for stablecoin in self.stablecoin_addresses:
                if stablecoin not in token_addresses:
                    continue
                    
                # Create SOL -> USDC -> SOL path
                paths.append([sol_token, stablecoin, sol_token])
        
        # Generate DEX token arbitrage paths
        # DEX1 -> DEX2 -> DEX1 paths
        dex_tokens_list = list(self.dex_tokens.intersection(token_addresses))
        for i in range(len(dex_tokens_list)):
            for j in range(i+1, len(dex_tokens_list)):
                dex1 = dex_tokens_list[i]
                dex2 = dex_tokens_list[j]
                
                # Create DEX1 -> DEX2 -> DEX1 path
                paths.append([dex1, dex2, dex1])
        
        # Generate meme token arbitrage paths
        meme_tokens_list = list(self.meme_tokens.intersection(token_addresses))
        for meme in meme_tokens_list:
            # Create MEME -> SOL -> MEME paths
            for sol_token in self.sol_tokens:
                if sol_token not in token_addresses:
                    continue
                    
                paths.append([meme, sol_token, meme])
                
            # Create MEME -> USDC -> MEME paths
            for stablecoin in self.stablecoin_addresses:
                if stablecoin not in token_addresses:
                    continue
                    
                paths.append([meme, stablecoin, meme])
                
            # Create MEME -> OTHER_MEME -> MEME paths (meme-to-meme swaps)
            for other_meme in meme_tokens_list:
                if other_meme == meme:
                    continue
                
                paths.append([meme, other_meme, meme])
        
        # Generate triangle paths
        # SOL -> Token1 -> Token2 -> SOL
        for sol_token in self.sol_tokens:
            if sol_token not in token_addresses:
                continue
                
            for token1 in token_addresses:
                if token1 == sol_token or token1 in self.sol_tokens:
                    continue
                    
                for token2 in token_addresses:
                    if token2 == sol_token or token2 == token1 or token2 in self.sol_tokens:
                        continue
                        
                    # Create triangle path
                    paths.append([sol_token, token1, token2, sol_token])
        
        # NEW: Add paths for tokens with cross-DEX opportunities
        cross_dex_tokens = [
            token for token in token_addresses 
            if token in self.cross_dex_opportunities
        ]
        
        for token in cross_dex_tokens:
            # For each cross-DEX token, create paths through SOL and stablecoins
            for sol_token in self.sol_tokens:
                if sol_token in token_addresses:
                    paths.append([token, sol_token, token])
                    
            for stable in self.stablecoin_addresses:
                if stable in token_addresses:
                    paths.append([token, stable, token])
        
        logger.info(f"Generated {len(paths)} potential arbitrage paths")
        return paths
    
    # NEW: Track token volume data
    def update_token_volume_data(self):
        """Update volume data for tracked tokens using Jupiter API"""
        try:
            # USDC for price conversion
            usdc = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
            
            # Process a subset of valid tokens (to avoid API overload)
            tokens_to_check = list(self.valid_token_addresses)[:50]
            
            for token in tokens_to_check:
                # Get volume data for this token
                try:
                    # Try to get 24h volume from Jupiter API
                    volume_data = self.api_client.get_token_volume(token, usdc)
                    if volume_data and volume_data > 0:
                        self.token_volume_cache[token] = volume_data
                        logger.debug(f"Updated volume for {token}: ${volume_data:.2f}")
                except Exception as e:
                    logger.error(f"Error getting volume for {token}: {e}")
                    
            # Save updated data
            self._save_cached_metadata()
            return len(self.token_volume_cache)
                
        except Exception as e:
            logger.error(f"Error updating token volume data: {e}")
            return 0