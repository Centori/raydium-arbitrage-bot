#!/usr/bin/env python3
"""
Raydium Data Cache Manager
Handles downloading, filtering, and caching Raydium pairs data
"""

import json
import time
import os
import logging
from typing import List, Dict, Optional
import requests

logger = logging.getLogger("RaydiumCache")

class RaydiumCache:
    def __init__(self, cache_file: str = "data/raydium_cache.json", min_liquidity: float = 50000):
        self.cache_file = cache_file
        self.min_liquidity = min_liquidity
        self.cache_max_age = 600  # 10 minutes
        self.api_url = "https://api.raydium.io/v2/main/pairs"
        
        # Ensure data directory exists
        os.makedirs(os.path.dirname(cache_file), exist_ok=True)
        
    def is_cache_valid(self) -> bool:
        """Check if cache exists and is not stale"""
        if not os.path.exists(self.cache_file):
            return False
        
        try:
            with open(self.cache_file, 'r') as f:
                cache_data = json.load(f)
            
            timestamp = cache_data.get('timestamp', 0)
            age = time.time() - timestamp
            
            if age > self.cache_max_age:
                logger.info(f"Cache is stale ({age:.0f}s old, max {self.cache_max_age}s)")
                return False
            
            logger.info(f"Cache is valid ({age:.0f}s old)")
            return True
            
        except Exception as e:
            logger.error(f"Error checking cache: {e}")
            return False
    
    def load_cache(self) -> Optional[List[Dict]]:
        """Load pairs from cache file"""
        try:
            if not os.path.exists(self.cache_file):
                logger.warning("Cache file not found")
                return None
            
            with open(self.cache_file, 'r') as f:
                cache_data = json.load(f)
            
            pairs = cache_data.get('pairs', [])
            logger.info(f"✅ Loaded {len(pairs)} pairs from cache")
            return pairs
            
        except Exception as e:
            logger.error(f"Error loading cache: {e}")
            return None
    
    def save_cache(self, pairs: List[Dict]):
        """Save pairs to cache file"""
        try:
            cache_data = {
                'timestamp': time.time(),
                'pair_count': len(pairs),
                'min_liquidity': self.min_liquidity,
                'pairs': pairs
            }
            
            with open(self.cache_file, 'w') as f:
                json.dump(cache_data, f, separators=(',', ':'))  # Compact JSON
            
            logger.info(f"✅ Saved {len(pairs)} pairs to cache")
            
        except Exception as e:
            logger.error(f"Error saving cache: {e}")
    
    def download_and_filter(self) -> List[Dict]:
        """Download from Raydium API and filter for high liquidity"""
        logger.info(f"Downloading from Raydium API... (this takes 60-120 seconds)")
        start_time = time.time()
        
        try:
            # Use requests with streaming to handle large response
            response = requests.get(self.api_url, timeout=180, stream=False)
            
            if response.status_code != 200:
                logger.error(f"API returned status {response.status_code}")
                return []
            
            logger.info("Parsing response...")
            all_pairs = response.json()
            
            download_time = time.time() - start_time
            logger.info(f"Downloaded {len(all_pairs):,} pairs in {download_time:.1f}s")
            
            # Filter for high liquidity
            logger.info(f"Filtering for liquidity > ${self.min_liquidity:,.0f}...")
            filtered_pairs = [
                p for p in all_pairs 
                if p.get('liquidity', 0) > self.min_liquidity
            ]
            
            logger.info(f"✅ Filtered to {len(filtered_pairs)} high-liquidity pairs")
            
            return filtered_pairs
            
        except requests.exceptions.Timeout:
            logger.error("API request timed out after 180 seconds")
            return []
        except Exception as e:
            logger.error(f"Error downloading data: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return []
    
    def get_pairs(self, force_refresh: bool = False) -> List[Dict]:
        """
        Get pairs data - from cache if valid, otherwise download
        
        Args:
            force_refresh: Force download even if cache is valid
            
        Returns:
            List of pair dictionaries
        """
        # Check cache first (unless forced refresh)
        if not force_refresh and self.is_cache_valid():
            cached_pairs = self.load_cache()
            if cached_pairs:
                return cached_pairs
        
        # Cache invalid or forced refresh - download new data
        logger.info("Cache invalid or refresh forced - downloading fresh data")
        pairs = self.download_and_filter()
        
        if pairs:
            self.save_cache(pairs)
        else:
            # If download failed, try to use stale cache as fallback
            logger.warning("Download failed, attempting to use stale cache...")
            cached_pairs = self.load_cache()
            if cached_pairs:
                logger.info("Using stale cache as fallback")
                return cached_pairs
            else:
                logger.error("No cache available and download failed!")
        
        return pairs
    
    def refresh_in_background(self):
        """Refresh cache in background thread (non-blocking)"""
        import threading
        
        def refresh_task():
            logger.info("Background refresh started...")
            pairs = self.download_and_filter()
            if pairs:
                self.save_cache(pairs)
                logger.info("Background refresh completed")
            else:
                logger.warning("Background refresh failed")
        
        thread = threading.Thread(target=refresh_task, daemon=True)
        thread.start()
        logger.info("Started background cache refresh")
        
        return thread


# Test function
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("=" * 70)
    print("Testing Raydium Cache Manager")
    print("=" * 70)
    print()
    
    cache = RaydiumCache()
    
    # Test 1: Get pairs (will download if no cache)
    print("Test 1: Getting pairs...")
    pairs = cache.get_pairs()
    print(f"✅ Got {len(pairs)} pairs")
    print()
    
    if pairs:
        # Show sample
        print("Sample pairs:")
        for i, pair in enumerate(pairs[:5], 1):
            print(f"  {i}. {pair['name']:20} Liq: ${pair['liquidity']:>12,.0f}")
        print()
    
    # Test 2: Get from cache (should be instant)
    print("Test 2: Getting from cache (should be instant)...")
    start = time.time()
    pairs2 = cache.get_pairs()
    elapsed = time.time() - start
    print(f"✅ Got {len(pairs2)} pairs in {elapsed:.3f}s")
    print()
    
    # Test 3: Check cache validity
    print("Test 3: Cache validity check...")
    is_valid = cache.is_cache_valid()
    print(f"Cache valid: {is_valid}")
    print()
    
    print("=" * 70)
    print("Cache tests complete!")
