from typing import Optional, Dict, List
import logging
import time
import json
import aiohttp
import asyncio
from api_client import BlockchainAPIClient, PoolData
from config import Config

logger = logging.getLogger("RaydiumPoolFetcher")

class RaydiumPoolFetcher:
    def __init__(self, config: Config):
        self.config = config
        self.api_client = BlockchainAPIClient(config)
        self.raydium_api_endpoint = getattr(config, 'RAYDIUM_API_ENDPOINT', 'https://api-v3.raydium.io')
        self.jupiter_api_endpoint = "https://quote-api.jup.ag/v6"
        
        # Cache storage for pools
        self.pools_cache = {}
        self.last_update_time = 0
        self.cache_expiry = 60  # Cache expiry in seconds
        
        # Track known pool addresses across sessions
        self.known_pool_addresses = set()
        self.pool_history_file = "data/pool_history.json"
        
        # Load historical pools
        self._load_known_pools()
        
        logger.info(f"RaydiumPoolFetcher initialized with cache expiry: {self.cache_expiry}s")
    
    def _load_known_pools(self):
        """Load previously discovered pool addresses from disk"""
        try:
            import os
            if os.path.exists(self.pool_history_file):
                with open(self.pool_history_file, 'r') as f:
                    pool_data = json.load(f)
                    self.known_pool_addresses = set(pool_data.get("pool_addresses", []))
                    logger.info(f"Loaded {len(self.known_pool_addresses)} historical pool addresses")
        except Exception as e:
            logger.error(f"Error loading pool history: {str(e)}")
            # Initialize empty set on error
            self.known_pool_addresses = set()
    
    def _save_known_pools(self):
        """Save discovered pool addresses to disk"""
        try:
            import os
            os.makedirs(os.path.dirname(self.pool_history_file), exist_ok=True)
            with open(self.pool_history_file, 'w') as f:
                json.dump({"pool_addresses": list(self.known_pool_addresses)}, f)
        except Exception as e:
            logger.error(f"Error saving pool history: {str(e)}")
    
    async def get_pool_data(self, pool_address: str) -> Optional[PoolData]:
        """Fetch Raydium pool data through API or external sources"""
        try:
            logger.debug(f"Fetching pool data for address: {pool_address}")
            
            # If using local server, try API client first
            if self.api_client.use_local_server:
                pool_info = await self.api_client.get_raydium_pool(pool_address)
                if pool_info:
                    self.known_pool_addresses.add(pool_address)
                    logger.debug(f"Successfully retrieved pool data for {pool_address}")
                    return pool_info
            
            # If local server not available or failed, try external APIs
            logger.debug(f"Trying external APIs for pool {pool_address}")
            
            # For now, return None as we'd need to implement specific pool fetching
            # The main pool fetching happens in fetch_all_pools() via external APIs
            logger.debug(f"Individual pool fetching not available for external APIs: {pool_address}")
            return None
                
        except Exception as e:
            logger.error(f"Error fetching pool data for {pool_address}: {str(e)}")
            return None
            
    async def get_multiple_pools(self, pool_addresses: list[str]) -> Dict[str, PoolData]:
        """Fetch multiple pool data"""
        results = {}
        for addr in pool_addresses:
            pool_data = await self.get_pool_data(addr)
            if pool_data:
                results[addr] = pool_data
        return results
    
    async def fetch_raydium_pools_direct(self) -> List[Dict]:
        """Fetch pools directly from Raydium API"""
        try:
            urls = [
                f"{self.raydium_api_endpoint}/pools",
                f"{self.raydium_api_endpoint}/pools/info/ids",
                f"{self.raydium_api_endpoint}/pools/info/mint/So11111111111111111111111111111111111111112"  # fallback example
            ]
            
            async with aiohttp.ClientSession() as session:
                for url in urls:
                    try:
                        async with session.get(url) as response:
                            if response.status == 200:
                                data = await response.json()
                                # Some endpoints may return {data: [...]} wrapper
                                if isinstance(data, dict) and 'data' in data:
                                    items = data.get('data') or []
                                else:
                                    items = data if isinstance(data, list) else []
                                logger.info(f"Fetched {len(items)} pools directly from Raydium API via {url}")
                                return items
                            else:
                                logger.error(f"Error fetching Raydium pools: {response.status} at {url}")
                    except Exception as e:
                        logger.debug(f"Fetch error for {url}: {e}")
                return []
        except Exception as e:
            logger.error(f"Error in direct Raydium pool fetch: {str(e)}")
            return []
    
    async def fetch_jupiter_pairs(self) -> List[Dict]:
        """Fetch trading pairs from Jupiter to discover additional pools"""
        try:
            url = f"{self.jupiter_api_endpoint}/pairs"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"Fetched {len(data)} pairs from Jupiter API")
                        return data
                    else:
                        logger.error(f"Error fetching Jupiter pairs: {response.status}")
                        return []
        except Exception as e:
            logger.error(f"Error in Jupiter pairs fetch: {str(e)}")
            return []
    
    async def fetch_all_pools(self) -> List[PoolData]:
        """Fetch all available Raydium pools including new listings"""
        try:
            current_time = time.time()
            
            # If cached data is still valid, return it
            if self.pools_cache and (current_time - self.last_update_time) < self.cache_expiry:
                logger.debug(f"Using cached pool data ({len(self.pools_cache)} pools)")
                return list(self.pools_cache.values())
            
            # Check API health first
            is_healthy = await self.api_client.check_api_health()
            if not is_healthy:
                raise Exception("API service is not available")
            
            pools = []
            
            # If using local server, get pools from API client
            if self.api_client.use_local_server:
                pools = await self.api_client.get_raydium_pools()
                logger.info(f"Fetched {len(pools)} pools from local API")
            else:
                # Use direct external API fetching
                logger.info("Using external APIs directly for pool data")
                
                # Get pools from direct Raydium API
                raydium_pools_raw = await self.fetch_raydium_pools_direct()
                
                # Convert raw pool data to PoolData objects
                for pool_data in raydium_pools_raw:
                    try:
                        # Convert Raydium API format to our PoolData format
                        converted_pool = self._convert_raydium_api_to_pool_data(pool_data)
                        if converted_pool:
                            pools.append(converted_pool)
                    except Exception as e:
                        logger.debug(f"Error converting pool data: {e}")
                        continue
                
                logger.info(f"Fetched {len(pools)} pools from external Raydium API")
            
            # Get additional pools from known history
            if self.known_pool_addresses:
                known_addresses = set(p.id for p in pools)
                missing_addresses = self.known_pool_addresses - known_addresses
                
                if missing_addresses:
                    logger.info(f"Checking {len(missing_addresses)} additional known pools")
                    for addr in missing_addresses:
                        pool = await self.get_pool_data(addr)
                        if pool:
                            pools.append(pool)
            
            # Update cache
            self.pools_cache = {pool.id: pool for pool in pools}
            self.last_update_time = current_time
            
            # Save discovered pools
            self._save_known_pools()
            
            logger.info(f"Total pools after all sources: {len(pools)}")
            return pools
            
        except Exception as e:
            logger.error(f"Error fetching pools: {str(e)}")
            
            # If we have cached data, return it as fallback
            if self.pools_cache:
                logger.warning(f"Using stale cache data due to fetch error ({len(self.pools_cache)} pools)")
                return list(self.pools_cache.values())
            
            # If API error occurred, wait before retrying
            logger.warning("No cache available, waiting to retry...")
            await asyncio.sleep(5)
            return []

    def _convert_raydium_api_to_pool_data(self, raw_pool_data: Dict) -> Optional[PoolData]:
        """Convert raw Raydium API data to PoolData object. Tries multiple common field names."""
        try:
            from api_client import TokenInfo

            def pick(d: Dict, keys: List[str], default=None):
                for k in keys:
                    if k in d and d[k] not in (None, ""):
                        return d[k]
                return default

            # Extract basic pool info
            pool_id = pick(raw_pool_data, ['id', 'pool_id', 'ammId', 'amm_id', 'poolId'])
            if not pool_id:
                return None
            
            # Extract token addresses
            base_mint = pick(raw_pool_data, ['baseMint', 'mintA', 'mint_a', 'tokenA', 'token_a', 'base_mint'])
            quote_mint = pick(raw_pool_data, ['quoteMint', 'mintB', 'mint_b', 'tokenB', 'token_b', 'quote_mint'])
            if not base_mint or not quote_mint:
                return None

            # Token metadata
            base_dec = int(pick(raw_pool_data, ['baseDecimals', 'decimalsA', 'decimals_a', 'base_decimals'], 9))
            quote_dec = int(pick(raw_pool_data, ['quoteDecimals', 'decimalsB', 'decimals_b', 'quote_decimals'], 6))
            base_sym = pick(raw_pool_data, ['baseSymbol', 'symbolA', 'symbol_a'], 'Unknown')
            quote_sym = pick(raw_pool_data, ['quoteSymbol', 'symbolB', 'symbol_b'], 'Unknown')
            base_name = pick(raw_pool_data, ['baseName', 'nameA', 'name_a'], 'Unknown Token')
            quote_name = pick(raw_pool_data, ['quoteName', 'nameB', 'name_b'], 'Unknown Token')

            base_token = TokenInfo(
                address=str(base_mint), symbol=str(base_sym), name=str(base_name), decimals=base_dec
            )
            quote_token = TokenInfo(
                address=str(quote_mint), symbol=str(quote_sym), name=str(quote_name), decimals=quote_dec
            )

            # Vaults / LP mint
            lp_mint = pick(raw_pool_data, ['lpMint', 'lp_mint', 'lp']) or ''
            base_vault = pick(raw_pool_data, ['baseVault', 'base_vault', 'vaultA', 'vault_a']) or ''
            quote_vault = pick(raw_pool_data, ['quoteVault', 'quote_vault', 'vaultB', 'vault_b']) or ''

            # Reserves / amounts
            base_amount = pick(raw_pool_data, ['baseReserve', 'reserveA', 'reservesA', 'baseAmount', 'tokenAmountA', 'amountA'], '0')
            quote_amount = pick(raw_pool_data, ['quoteReserve', 'reserveB', 'reservesB', 'quoteAmount', 'tokenAmountB', 'amountB'], '0')

            # Version and fee
            version = int(pick(raw_pool_data, ['version', 'poolVersion', 'pool_version'], 4))
            fee_rate = int(pick(raw_pool_data, ['feeRate', 'lpFeeRate', 'tradeFeeRate'], 25))

            return PoolData(
                id=str(pool_id),
                version=version,
                base_token=base_token,
                quote_token=quote_token,
                lp_mint=str(lp_mint),
                base_vault=str(base_vault),
                quote_vault=str(quote_vault),
                base_amount=str(base_amount),
                quote_amount=str(quote_amount),
                fee_rate=fee_rate
            )
        except Exception as e:
            logger.debug(f"Error converting pool data: {e}")
            return None

    async def refresh_pools_async(self) -> List[PoolData]:
        """Asynchronous method to refresh pool data including checking multiple sources"""
        try:
            # Check API health first
            if not self.api_client.check_api_health():
                raise Exception("API service is not available")
            
            # Get pools from primary API
            pools = self.api_client.get_raydium_pools()
            logger.info(f"Fetched {len(pools)} pools from primary API")
            
            # Get additional pools from Raydium API directly
            raydium_pools_raw = await self.fetch_raydium_pools_direct()
            
            # Get Jupiter pairs to discover additional pools
            jupiter_pairs = await self.fetch_jupiter_pairs()
            
            # Track added pools
            new_pools_count = 0
            
            # Process additional pools from Raydium
            for pool_data in raydium_pools_raw:
                pool_id = pool_data.get('id')
                if not pool_id:
                    continue
                
                if not any(p.id == pool_id for p in pools):
                    pool = self.get_pool_data(pool_id)
                    if pool:
                        pools.append(pool)
                        self.known_pool_addresses.add(pool_id)
                        new_pools_count += 1
            
            # Update cache
            self.pools_cache = {pool.id: pool for pool in pools}
            self.last_update_time = time.time()
            
            # Save discovered pools
            self._save_known_pools()
            
            logger.info(f"Refreshed pool data: {len(pools)} pools total, {new_pools_count} new pools added")
            return pools
            
        except Exception as e:
            logger.error(f"Error refreshing pools: {str(e)}")
            # Return cached data as fallback
            return list(self.pools_cache.values()) if self.pools_cache else []