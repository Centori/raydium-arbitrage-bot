"""
Standalone KOL Discovery using DexScreener (No API Keys Required)
==================================================================
Discovers moonshot tokens and identifies KOLs using only public DexScreener API.
Integrates with existing velocity/liquidity monitoring system.

Features:
- No API keys required (uses DexScreener public endpoints)
- Identifies 1000x+ traders automatically
- Integrates with monitor.py for velocity analysis
- Exports KOL watchlist for real-time monitoring

Author: Quantitative Trading System
"""

import asyncio
import aiohttp
from typing import Dict, List, Optional, Set, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from collections import defaultdict
import json
import logging
import os
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Import existing monitor for integration
try:
    from monitor import TradingMonitor
    MONITOR_AVAILABLE = True
except ImportError:
    MONITOR_AVAILABLE = False
    logging.warning("monitor.py not found - velocity integration disabled")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("KOLDiscovery")


@dataclass
class MoonshotToken:
    """Token that has achieved significant gains"""
    mint: str
    symbol: str
    name: str
    price_usd: float
    price_change_5m: float
    price_change_1h: float
    price_change_6h: float
    price_change_24h: float
    volume_24h: float
    liquidity_usd: float
    market_cap: float
    pair_created_at: int
    dex: str
    pair_address: str
    
    # Calculated fields
    discovered_at: datetime = None
    max_roi: float = 0.0
    is_moonshot: bool = False
    
    def __post_init__(self):
        if self.discovered_at is None:
            self.discovered_at = datetime.now()
        
        # Calculate max ROI from price changes
        max_change = max(
            self.price_change_24h,
            self.price_change_6h,
            self.price_change_1h,
            self.price_change_5m
        )
        self.max_roi = max_change / 100  # Convert percentage to decimal
        self.is_moonshot = self.max_roi >= 10.0  # 1000%+


@dataclass
class SimpleWalletProfile:
    """Simplified wallet profile for standalone mode"""
    address: str
    tokens_traded: List[str]
    moonshot_count: int
    estimated_roi: float
    first_seen: datetime
    last_seen: datetime
    confidence_score: float  # 0-100


class DexScreenerClient:
    """Client for DexScreener public API (no auth required)"""
    
    BASE_URL = "https://api.dexscreener.com/latest/dex"
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def search_pairs(self, query: str = "SOL", limit: int = 50) -> List[Dict]:
        """Search for trading pairs"""
        url = f"{self.BASE_URL}/search"
        params = {"q": query}
        
        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    pairs = data.get("pairs", [])
                    # Filter for Solana only
                    return [p for p in pairs if p.get("chainId") == "solana"][:limit]
                else:
                    logger.error(f"DexScreener error: {response.status}")
                    return []
        except Exception as e:
            logger.error(f"Error searching pairs: {e}")
            return []
    
    async def get_token_pairs(self, token_address: str) -> List[Dict]:
        """Get all pairs for a specific token"""
        url = f"{self.BASE_URL}/tokens/{token_address}"
        
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("pairs", [])
                else:
                    logger.error(f"DexScreener error: {response.status}")
                    return []
        except Exception as e:
            logger.error(f"Error fetching token pairs: {e}")
            return []
    
    async def get_profile_latest(self) -> Dict:
        """Get latest profile data (top tokens)"""
        url = f"{self.BASE_URL}/tokens/solana"
        
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"DexScreener error: {response.status}")
                    return {}
        except Exception as e:
            logger.error(f"Error fetching profile: {e}")
            return {}


class StandaloneKOLDiscovery:
    """Standalone KOL discovery using only DexScreener"""
    
    def __init__(self, output_dir: str = "data/kol_discovery"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        
        # Discovery state
        self.moonshots: Dict[str, MoonshotToken] = {}
        self.kol_candidates: Dict[str, SimpleWalletProfile] = {}
        self.analyzed_tokens: Set[str] = set()
        
        # Thresholds
        self.min_roi = 10.0  # 1000%+
        self.min_volume = 50000  # $50k
        self.min_liquidity = 25000  # $25k
        
        # Integration with existing monitor
        self.monitor = None
        if MONITOR_AVAILABLE:
            try:
                from config import Config
                self.monitor = TradingMonitor(Config())
                logger.info("✓ Integrated with existing TradingMonitor")
            except Exception as e:
                logger.warning(f"Could not initialize monitor: {e}")
    
    async def scan_for_moonshots(self, timeframe: str = "24h") -> List[MoonshotToken]:
        """
        Scan DexScreener for moonshot tokens
        
        Args:
            timeframe: "5m", "1h", "6h", "24h"
        
        Returns:
            List of moonshot candidates
        """
        logger.info(f"Scanning DexScreener for {timeframe} moonshots...")
        
        moonshots = []
        
        async with DexScreenerClient() as client:
            # Strategy 1: Search for high gainers
            queries = ["100x", "1000x", "moon", "gem", "SOL"]
            
            for query in queries:
                pairs = await client.search_pairs(query, limit=50)
                
                for pair in pairs:
                    token = self._parse_pair_to_token(pair, timeframe)
                    
                    if token and token.is_moonshot:
                        # Check thresholds
                        if (token.volume_24h >= self.min_volume and 
                            token.liquidity_usd >= self.min_liquidity):
                            
                            moonshots.append(token)
                            self.moonshots[token.mint] = token
                            
                            logger.info(
                                f"Found moonshot: {token.symbol} "
                                f"({token.max_roi:.1f}x, "
                                f"${token.volume_24h:,.0f} vol)"
                            )
                
                # Rate limiting
                await asyncio.sleep(1)
        
        # Deduplicate
        unique_moonshots = {m.mint: m for m in moonshots}.values()
        logger.info(f"Discovered {len(unique_moonshots)} unique moonshots")
        
        return list(unique_moonshots)
    
    def _parse_pair_to_token(self, pair: Dict, timeframe: str) -> Optional[MoonshotToken]:
        """Parse DexScreener pair into MoonshotToken"""
        try:
            base_token = pair.get("baseToken", {})
            
            # Get price change for the timeframe
            price_change_map = {
                "5m": pair.get("priceChange", {}).get("m5", 0),
                "1h": pair.get("priceChange", {}).get("h1", 0),
                "6h": pair.get("priceChange", {}).get("h6", 0),
                "24h": pair.get("priceChange", {}).get("h24", 0)
            }
            
            return MoonshotToken(
                mint=base_token.get("address", ""),
                symbol=base_token.get("symbol", "UNKNOWN"),
                name=base_token.get("name", "Unknown"),
                price_usd=float(pair.get("priceUsd", 0)),
                price_change_5m=float(price_change_map.get("5m", 0)),
                price_change_1h=float(price_change_map.get("1h", 0)),
                price_change_6h=float(price_change_map.get("6h", 0)),
                price_change_24h=float(price_change_map.get("24h", 0)),
                volume_24h=float(pair.get("volume", {}).get("h24", 0)),
                liquidity_usd=float(pair.get("liquidity", {}).get("usd", 0)),
                market_cap=float(pair.get("fdv", 0)),
                pair_created_at=int(pair.get("pairCreatedAt", 0)),
                dex=pair.get("dexId", "unknown"),
                pair_address=pair.get("pairAddress", "")
            )
        except Exception as e:
            logger.error(f"Error parsing pair: {e}")
            return None
    
    async def extract_kols_from_onchain_data(self, token_mint: str) -> List[str]:
        """
        Extract wallet addresses of early buyers/sellers from on-chain data using Helius
        
        Returns:
            List of wallet addresses
        """
        logger.info(f"Extracting KOL wallets for {token_mint[:10]}...")
        
        # Load Helius API key from environment
        helius_api_key = os.getenv('HELIUS_API_KEY')
        if not helius_api_key:
            logger.warning("HELIUS_API_KEY not found in environment")
            return []
        
        wallets = set()
        
        try:
            # Use Helius Enhanced Transactions API
            url = f"https://mainnet.helius-rpc.com/?api-key={helius_api_key}"
            
            # Get recent signatures for this token
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getSignaturesForAddress",
                "params": [
                    token_mint,
                    {"limit": 1000}  # Get last 1000 transactions
                ]
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status != 200:
                        logger.error(f"Helius API error: {response.status}")
                        return []
                    
                    data = await response.json()
                    signatures = data.get('result', [])
                    
                    if not signatures:
                        logger.debug(f"No signatures found for {token_mint[:10]}")
                        return []
                    
                    logger.info(f"Found {len(signatures)} transactions for {token_mint[:10]}")
                    
                    # Get parsed transactions in batches
                    batch_size = 100
                    for i in range(0, min(len(signatures), 500), batch_size):  # Limit to 500 total
                        batch_sigs = signatures[i:i+batch_size]
                        sig_strings = [sig['signature'] for sig in batch_sigs]
                        
                        # Get parsed transactions
                        tx_payload = {
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "getTransaction",
                            "params": [
                                sig_strings[0],  # Helius doesn't support batch getTransaction
                                {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}
                            ]
                        }
                        
                        # For each signature, extract wallet addresses
                        for sig in sig_strings[:20]:  # Sample first 20 for speed
                            tx_payload['params'][0] = sig
                            
                            async with session.post(url, json=tx_payload) as tx_response:
                                if tx_response.status == 200:
                                    tx_data = await tx_response.json()
                                    result = tx_data.get('result')
                                    
                                    if result and result.get('transaction'):
                                        # Extract account keys (wallet addresses)
                                        meta = result.get('meta', {})
                                        tx = result.get('transaction', {})
                                        
                                        # Get all account keys
                                        message = tx.get('message', {})
                                        account_keys = message.get('accountKeys', [])
                                        
                                        for account in account_keys:
                                            if isinstance(account, dict):
                                                pubkey = account.get('pubkey')
                                                if pubkey and pubkey != token_mint:
                                                    wallets.add(pubkey)
                                            elif isinstance(account, str) and account != token_mint:
                                                wallets.add(account)
                            
                            await asyncio.sleep(0.1)  # Rate limiting
                        
                        await asyncio.sleep(0.5)  # Batch rate limiting
            
            logger.info(f"Extracted {len(wallets)} unique wallets")
            return list(wallets)
            
        except Exception as e:
            logger.error(f"Error extracting wallets from Helius: {e}")
            return []
    
    def estimate_kol_from_trading_pattern(self, 
                                         token: MoonshotToken,
                                         wallet_addresses: List[str]) -> List[SimpleWalletProfile]:
        """
        Estimate KOL quality from trading patterns
        
        This is a heuristic approach when detailed transaction data isn't available
        """
        profiles = []
        
        for address in wallet_addresses:
            # Create or update profile
            if address not in self.kol_candidates:
                profile = SimpleWalletProfile(
                    address=address,
                    tokens_traded=[token.mint],
                    moonshot_count=1 if token.is_moonshot else 0,
                    estimated_roi=token.max_roi,
                    first_seen=token.discovered_at,
                    last_seen=token.discovered_at,
                    confidence_score=50.0  # Base score
                )
            else:
                profile = self.kol_candidates[address]
                profile.tokens_traded.append(token.mint)
                if token.is_moonshot:
                    profile.moonshot_count += 1
                profile.estimated_roi = max(profile.estimated_roi, token.max_roi)
                profile.last_seen = token.discovered_at
            
            # Calculate confidence score
            profile.confidence_score = self._calculate_confidence(profile, token)
            
            self.kol_candidates[address] = profile
            profiles.append(profile)
        
        return profiles
    
    def _calculate_confidence(self, profile: SimpleWalletProfile, token: MoonshotToken) -> float:
        """Calculate KOL confidence score (0-100)"""
        score = 50.0  # Base
        
        # Moonshot bonus
        score += profile.moonshot_count * 15  # +15 per moonshot
        
        # ROI bonus
        if profile.estimated_roi >= 100:  # 10,000%+
            score += 20
        elif profile.estimated_roi >= 50:  # 5,000%+
            score += 15
        elif profile.estimated_roi >= 10:  # 1,000%+
            score += 10
        
        # Volume bonus (higher volume = more conviction)
        if token.volume_24h >= 1000000:  # $1M+
            score += 10
        elif token.volume_24h >= 500000:  # $500k+
            score += 5
        
        # Liquidity bonus (better execution)
        if token.liquidity_usd >= 100000:  # $100k+
            score += 5
        
        return min(score, 100.0)
    
    def get_top_kols(self, min_score: float = 60.0, min_moonshots: int = 1) -> List[SimpleWalletProfile]:
        """Get top KOL candidates"""
        qualified = [
            kol for kol in self.kol_candidates.values()
            if kol.confidence_score >= min_score and kol.moonshot_count >= min_moonshots
        ]
        
        return sorted(qualified, key=lambda x: x.confidence_score, reverse=True)
    
    def create_monitoring_watchlist(self, top_kols: List[SimpleWalletProfile]) -> Dict:
        """
        Create watchlist for integration with monitor.py
        
        Returns:
            Watchlist configuration for velocity monitoring
        """
        watchlist = {
            "created_at": datetime.now().isoformat(),
            "kol_count": len(top_kols),
            "wallets": []
        }
        
        for kol in top_kols:
            watchlist["wallets"].append({
                "address": kol.address,
                "confidence_score": kol.confidence_score,
                "moonshot_count": kol.moonshot_count,
                "estimated_roi": kol.estimated_roi,
                "tokens_traded": kol.tokens_traded,
                "monitoring_config": {
                    "alert_on_new_position": True,
                    "alert_on_large_trade": True,
                    "min_trade_size_usd": 1000,
                    "priority": "high" if kol.confidence_score >= 80 else "medium"
                }
            })
        
        # Save watchlist
        watchlist_file = os.path.join(self.output_dir, "kol_watchlist.json")
        with open(watchlist_file, 'w') as f:
            json.dump(watchlist, f, indent=2)
        
        logger.info(f"Created monitoring watchlist: {watchlist_file}")
        return watchlist
    
    def export_results(self, filename: str = "kol_discovery_results.json"):
        """Export all discovery results"""
        filepath = os.path.join(self.output_dir, filename)
        
        results = {
            "discovery_summary": {
                "timestamp": datetime.now().isoformat(),
                "total_moonshots": len(self.moonshots),
                "total_kols": len(self.kol_candidates),
                "elite_kols": len(self.get_top_kols(min_score=80)),
            },
            "moonshots": [
                {
                    "mint": m.mint,
                    "symbol": m.symbol,
                    "max_roi": m.max_roi,
                    "volume_24h": m.volume_24h,
                    "liquidity_usd": m.liquidity_usd,
                    "dex": m.dex,
                    "discovered_at": m.discovered_at.isoformat()
                }
                for m in self.moonshots.values()
            ],
            "top_kols": [
                {
                    "address": kol.address,
                    "confidence_score": kol.confidence_score,
                    "moonshot_count": kol.moonshot_count,
                    "estimated_roi": kol.estimated_roi,
                    "tokens_traded_count": len(kol.tokens_traded)
                }
                for kol in self.get_top_kols()
            ]
        }
        
        with open(filepath, 'w') as f:
            json.dump(results, f, indent=2)
        
        logger.info(f"Exported results to {filepath}")
    
    async def continuous_discovery(self, 
                                  interval_minutes: int = 30,
                                  max_iterations: Optional[int] = None):
        """
        Continuously scan for moonshots and update KOL database
        
        Args:
            interval_minutes: Scan interval
            max_iterations: Max iterations (None = infinite)
        """
        logger.info(f"Starting continuous discovery (every {interval_minutes} min)...")
        
        iteration = 0
        while max_iterations is None or iteration < max_iterations:
            try:
                logger.info(f"\n=== Discovery Iteration {iteration + 1} ===")
                
                # Scan for moonshots
                moonshots = await self.scan_for_moonshots(timeframe="24h")
                
                # Process each moonshot
                for token in moonshots:
                    if token.mint not in self.analyzed_tokens:
                        # Extract KOLs (simplified without full transaction data)
                        wallets = await self.extract_kols_from_onchain_data(token.mint)
                        
                        # If we can't get wallets, skip detailed analysis
                        if not wallets:
                            logger.debug(f"No wallet data for {token.symbol}, skipping")
                            continue
                        
                        # Estimate KOL quality
                        kols = self.estimate_kol_from_trading_pattern(token, wallets)
                        
                        self.analyzed_tokens.add(token.mint)
                        logger.info(f"Processed {token.symbol}: {len(kols)} KOL candidates")
                
                # Export results
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                self.export_results(f"kol_discovery_{timestamp}.json")
                
                # Create watchlist
                top_kols = self.get_top_kols(min_score=60)
                self.create_monitoring_watchlist(top_kols)
                
                # Print summary
                logger.info(f"\nCurrent Stats:")
                logger.info(f"  Moonshots discovered: {len(self.moonshots)}")
                logger.info(f"  KOL candidates: {len(self.kol_candidates)}")
                logger.info(f"  Elite KOLs (score ≥80): {len(self.get_top_kols(min_score=80))}")
                
                # Wait
                logger.info(f"Waiting {interval_minutes} minutes...\n")
                await asyncio.sleep(interval_minutes * 60)
                
                iteration += 1
                
            except KeyboardInterrupt:
                logger.info("Discovery stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in discovery loop: {e}")
                await asyncio.sleep(60)


# ============================================================================
# CLI INTERFACE
# ============================================================================

async def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Standalone KOL Discovery (DexScreener only)")
    parser.add_argument("--mode", choices=["once", "continuous"], default="once",
                       help="Run once or continuously")
    parser.add_argument("--interval", type=int, default=30,
                       help="Scan interval in minutes (continuous mode)")
    parser.add_argument("--output", default="data/kol_discovery",
                       help="Output directory")
    
    args = parser.parse_args()
    
    # Initialize discovery engine
    engine = StandaloneKOLDiscovery(output_dir=args.output)
    
    if args.mode == "once":
        print("\n=== KOL Discovery (One-Time Scan) ===\n")
        
        # Scan for moonshots
        moonshots = await engine.scan_for_moonshots(timeframe="24h")
        
        print(f"\n=== Results ===")
        print(f"Moonshots found: {len(moonshots)}")
        
        # Show top moonshots
        print(f"\n=== Top 10 Moonshots ===")
        sorted_moonshots = sorted(moonshots, key=lambda x: x.max_roi, reverse=True)[:10]
        for i, token in enumerate(sorted_moonshots, 1):
            print(f"{i}. {token.symbol}")
            print(f"   ROI: {token.max_roi:.1f}x | Vol: ${token.volume_24h:,.0f}")
            print(f"   Liq: ${token.liquidity_usd:,.0f} | DEX: {token.dex}")
            print()
        
        # Export results
        engine.export_results()
        
        # Create watchlist
        top_kols = engine.get_top_kols(min_score=60)
        if top_kols:
            watchlist = engine.create_monitoring_watchlist(top_kols)
            print(f"\nCreated watchlist with {len(top_kols)} KOLs")
            print(f"Location: {args.output}/kol_watchlist.json")
        else:
            print("\nNo KOLs identified (need on-chain transaction data for full analysis)")
        
    else:  # continuous
        print(f"\n=== KOL Discovery (Continuous Mode) ===")
        print(f"Scanning every {args.interval} minutes")
        print("Press Ctrl+C to stop\n")
        
        await engine.continuous_discovery(interval_minutes=args.interval)


if __name__ == "__main__":
    asyncio.run(main())
