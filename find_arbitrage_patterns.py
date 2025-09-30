#!/usr/bin/env python3
"""
Jito Arbitrage Pattern Detector
This script analyzes successful arbitrage transactions and Jito bundles
to identify profitable trading patterns and replicate successful strategies.
"""

import os
import json
import time
import base64
from datetime import datetime, timedelta
import requests
from typing import Dict, List, Any, Optional
import asyncio
import signal
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
from requests.exceptions import HTTPError

# Configuration - adjust as needed
TOKEN_PAIRS = [
    {"name": "SOL/USDC", "base": "So11111111111111111111111111111111111111112", "quote": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"},
    {"name": "SOL/USDT", "base": "So11111111111111111111111111111111111111112", "quote": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"},
    {"name": "ETH/USDC", "base": "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs", "quote": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"},
    {"name": "ETH/USDT", "base": "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs", "quote": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"},
    {"name": "USDC/USDT", "base": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "quote": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"},
]

# Known arbitrage program IDs
ARBITRAGE_PROGRAMS = {
    "JitoEBftV8P1Bw26ZmUj5byZiot1WJ1Jb6ybGzDUzWM": "Jito MEV",
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc": "Whirlpools",
    "JUP4Fb2cqiRUcaTHdrPC8h2gNsA2ETXiPDD33WcGuJB": "Jupiter v4",
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": "Jupiter v6",
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "Raydium AMM",
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc": "Orca Whirlpools",
    "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK": "Raydium Concentrated",
}

# Token symbols for display
TOKEN_SYMBOLS = {
    "So11111111111111111111111111111111111111112": "SOL",
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": "USDT",
    "7dHbWXmci3dT8UFYWYZweBLXgycu7Y3iL6trKn1Y7ARj": "DAI",
    "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So": "mSOL",
    "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R": "RAY",
    "orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE": "ORCA",
    "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263": "BONK",
    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN": "JUP",
    "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs": "ETH",
}

class JitoArbitrageFinder:
    def __init__(self, rpc_endpoint=None, jito_auth_token=None):
        self.rpc_endpoint = rpc_endpoint or os.getenv("RPC_ENDPOINT", "https://api.mainnet-beta.solana.com")
        self.jito_auth_token = jito_auth_token or os.getenv("JITO_AUTH_TOKEN")
        self.arbitrage_txs = []
        self.output_dir = "data/arbitrage_analysis"
        self.bundle_dir = "data/bundles"
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.bundle_dir, exist_ok=True)
        self.running = False
        self.analysis_interval = 300  # 5 minutes

    async def start_background_analysis(self):
        """Start background pattern analysis"""
        self.running = True
        while self.running:
            try:
                print("\n=== Running Pattern Analysis ===")
                # Scan recent patterns
                await self.scan_jito_bundles_async(hours_back=1)  # Look at last hour
                patterns = self.analyze_profitable_patterns()
                
                self._print_analysis_results(patterns)
                
                # Wait for next interval
                await asyncio.sleep(self.analysis_interval)
            except Exception as e:
                print(f"Error in background analysis: {str(e)}")
                await asyncio.sleep(60)  # Wait a minute on error
    
    def stop_background_analysis(self):
        """Stop background pattern analysis"""
        self.running = False

    async def scan_jito_bundles_async(self, hours_back=24):
        """Async version of scan_jito_bundles"""
        print(f"Scanning Jito bundles from the last {hours_back} hours...")
        
        start_time = datetime.now() - timedelta(hours=hours_back)
        bundles = await self._get_jito_bundles_async(start_time)
        print(f"Found {len(bundles)} Jito bundles to analyze")
        
        analyses = []
        for bundle in bundles:
            bundle_info = await self._analyze_jito_bundle_async(bundle)
            if bundle_info.get("is_profitable"):
                self._save_profitable_bundle(bundle, bundle_info)
                analyses.append(bundle_info)
        
        return analyses

    async def _get_jito_bundles_async(self, start_time):
        """Async version of _get_jito_bundles"""
        if not self.jito_auth_token:
            print("Warning: No Jito auth token provided. Using public RPC instead.")
            return await self._get_recent_signatures_async(100)
        
        try:
            headers = {
                "Authorization": f"Bearer {self.jito_auth_token}",
                "Content-Type": "application/json"
            }
            payload = {
                "start_time": int(start_time.timestamp()),
                "end_time": int(datetime.now().timestamp())
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://searcher-api.jito.wtf/api/v1/bundles",
                    headers=headers,
                    json=payload
                ) as response:
                    if response.status != 200:
                        print(f"Error fetching bundles: {response.status}")
                        return []
                    data = await response.json()
                    return data.get("bundles", [])
        except Exception as e:
            print(f"Error fetching Jito bundles: {str(e)}")
            return []

    async def _get_recent_signatures_async(self, limit=100):
        """Async version of _get_recent_signatures"""
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getSignaturesForAddress",
                "params": [
                    "JitoEBftV8P1Bw26ZmUj5byZiot1WJ1Jb6ybGzDUzWM",
                    {
                        "limit": limit,
                        "commitment": "confirmed"
                    }
                ]
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.rpc_endpoint,
                    headers={"Content-Type": "application/json"},
                    json=payload
                ) as response:
                    if response.status != 200:
                        print(f"Error fetching signatures: {response.status}")
                        return []
                    result = await response.json()
                    if "error" in result:
                        print(f"RPC error: {result['error']}")
                        return []
                    return [tx["signature"] for tx in result.get("result", [])]
        except Exception as e:
            print(f"Error getting signatures: {str(e)}")
            return []

    async def _get_transaction_async(self, signature):
        """Async version of getting transaction data with retry logic"""
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTransaction",
                "params": [
                    signature,
                    {"encoding": "json", "commitment": "confirmed", "maxSupportedTransactionVersion": 0}
                ]
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.rpc_endpoint,
                    headers={"Content-Type": "application/json"},
                    json=payload
                ) as response:
                    if response.status != 200:
                        print(f"Error fetching transaction: {response.status}")
                        return None
                    result = await response.json()
                    if "error" in result:
                        print(f"RPC error: {result['error']}")
                        return None
                    return result.get("result")
                    
        except Exception as e:
            print(f"Error getting transaction data: {str(e)}")
            return None

    async def _analyze_jito_bundle_async(self, bundle):
        """Async version of _analyze_jito_bundle"""
        result = {
            "is_profitable": False,
            "profit": 0,
            "pattern": None,
            "dexes_used": [],
            "token_path": [],
            "instructions": [],
            "pool_states": [],
            "price_impact": {},
            "execution_time": None,
            "gas_used": 0
        }
        
        try:
            if isinstance(bundle, str):
                # If bundle is just a signature, get the full transaction
                tx_data = await self._get_transaction_async(bundle)
                if tx_data:
                    tx_analysis = self._analyze_for_arbitrage(tx_data)
                    if tx_analysis and tx_analysis.get("is_arbitrage"):
                        result.update({
                            "is_profitable": True,
                            "profit": tx_analysis.get("profit", 0),
                            "dexes_used": tx_analysis.get("programs", []),
                            "token_path": tx_analysis.get("tokens", []),
                            "instructions": tx_analysis.get("instructions", []),
                            "pattern": tx_analysis.get("pattern")
                        })
            elif isinstance(bundle, dict):
                # Process full bundle object
                transactions = bundle.get("transactions", [])
                if transactions:
                    total_profit = 0
                    dexes_used = set()
                    token_path = []
                    gas_total = 0
                    
                    for tx in transactions:
                        tx_analysis = self._analyze_for_arbitrage(tx)
                        if tx_analysis.get("is_arbitrage"):
                            total_profit += tx_analysis.get("profit", 0)
                            dexes_used.update(tx_analysis.get("programs", []))
                            token_path.extend(tx_analysis.get("tokens", []))
                            result["instructions"].extend(tx_analysis.get("instructions", []))
                            gas_total += tx_analysis.get("gas_used", 0)
                    
                    result.update({
                        "is_profitable": total_profit > 0,
                        "profit": total_profit,
                        "dexes_used": list(dexes_used),
                        "token_path": token_path,
                        "gas_used": gas_total,
                        "execution_time": bundle.get("execution_time")
                    })
                    
                    if total_profit > 0 and gas_total > 0:
                        result["profit_per_gas"] = total_profit / gas_total
            
        except Exception as e:
            print(f"Error analyzing bundle: {str(e)}")
            
        return result

    def analyze_profitable_patterns(self):
        """Analyze stored arbitrage transactions to identify profitable patterns"""
        patterns = {}
        
        # Load all saved bundle analyses
        bundle_files = []
        for root, _, files in os.walk(self.bundle_dir):
            for file in files:
                if file.endswith('.json'):
                    try:
                        with open(os.path.join(root, file), 'r') as f:
                            bundle_data = json.load(f)
                            if bundle_data.get('is_profitable'):
                                bundle_files.append(bundle_data)
                    except Exception as e:
                        print(f"Error loading bundle file {file}: {str(e)}")
        
        if not bundle_files:
            # Fallback to analyzing public DEX transactions
            print("No profitable bundles found, analyzing public DEX transactions...")
            public_patterns = self._analyze_public_dex_patterns()
            if public_patterns:
                return public_patterns
            return {}

        # Group transactions by pattern type
        for bundle in bundle_files:
            pattern_key = bundle.get('pattern', 'Unknown')
            if pattern_key not in patterns:
                patterns[pattern_key] = {
                    'count': 0,
                    'total_profit': 0,
                    'dexes': set(),
                    'tokens': set(),
                    'avg_profit': 0,
                    'gas_stats': {'min': float('inf'), 'max': 0, 'total': 0},
                    'last_seen': None
                }
            
            pattern = patterns[pattern_key]
            pattern['count'] += 1
            pattern['total_profit'] += bundle.get('profit', 0)
            pattern['dexes'].update(bundle.get('dexes_used', []))
            pattern['tokens'].update(bundle.get('token_path', []))
            
            gas_used = bundle.get('gas_used', 0)
            if gas_used > 0:
                pattern['gas_stats']['min'] = min(pattern['gas_stats']['min'], gas_used)
                pattern['gas_stats']['max'] = max(pattern['gas_stats']['max'], gas_used)
                pattern['gas_stats']['total'] += gas_used
            
            timestamp = bundle.get('timestamp')
            if timestamp:
                pattern['last_seen'] = max(pattern['last_seen'] or timestamp, timestamp)
        
        # Calculate averages and cleanup
        for pattern in patterns.values():
            if pattern['count'] > 0:
                pattern['avg_profit'] = pattern['total_profit'] / pattern['count']
                if pattern['gas_stats']['total'] > 0:
                    pattern['avg_gas'] = pattern['gas_stats']['total'] / pattern['count']
        
        return patterns

    def _analyze_public_dex_patterns(self):
        """Analyze public DEX transactions when no Jito bundles are available"""
        try:
            # First check Raydium pools
            print("Analyzing Raydium pool transactions...")
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getSignaturesForAddress",
                "params": [
                    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",  # Raydium AMM
                    {"limit": 50}
                ]
            }
            
            response = requests.post(self.rpc_endpoint, json=payload)
            if response.status_code == 200:
                result = response.json()
                if "result" in result:
                    signatures = [tx["signature"] for tx in result["result"]]
                    
                    patterns = {}
                    for sig in signatures:
                        tx_data = self._get_transaction(sig)
                        if tx_data:
                            analysis = self._analyze_for_arbitrage(tx_data)
                            if analysis and analysis.get("is_arbitrage"):
                                pattern_key = analysis.get("pattern", "Unknown")
                                if pattern_key not in patterns:
                                    patterns[pattern_key] = {
                                        "count": 0,
                                        "total_profit": 0,
                                        "dexes": set(),
                                        "tokens": set(),
                                        "gas_stats": {"min": float('inf'), "max": 0, "total": 0}
                                    }
                                
                                pattern = patterns[pattern_key]
                                pattern["count"] += 1
                                pattern["total_profit"] += analysis.get("profit", 0)
                                pattern["dexes"].update(analysis.get("programs", []))
                                pattern["tokens"].update(analysis.get("tokens", []))
                                
                                gas = analysis.get("gas_used", 0)
                                if gas > 0:
                                    pattern["gas_stats"]["min"] = min(pattern["gas_stats"]["min"], gas)
                                    pattern["gas_stats"]["max"] = max(pattern["gas_stats"]["max"], gas)
                                    pattern["gas_stats"]["total"] += gas
                    
                    return patterns
            
            return {}
            
        except Exception as e:
            print(f"Error analyzing public DEX patterns: {str(e)}")
            return {}

    def _print_analysis_results(self, patterns):
        """Print detailed analysis results"""
        print("\n=== Arbitrage Pattern Analysis ===")
        if not patterns:
            print("No patterns found in this analysis period")
            return

        for pattern_key, data in patterns.items():
            print(f"\n📊 Pattern: {pattern_key}")
            print(f"   Count: {data['count']} trades")
            print(f"   Avg Profit: {data['avg_profit']:.6f} SOL")
            print(f"   Total Profit: {data.get('total_profit', 0):.6f} SOL")
            
            if data.get('dexes'):
                print(f"   DEXes Used: {', '.join(list(data['dexes']))}")
            
            if data.get('tokens'):
                print(f"   Tokens: {', '.join(list(data['tokens']))}")
            
            if 'gas_stats' in data:
                print(f"   Gas Stats:")
                print(f"     Min: {data['gas_stats'].get('min', 0)}")
                print(f"     Max: {data['gas_stats'].get('max', 0)}")
                print(f"     Avg: {data['gas_stats'].get('total', 0) / data['count'] if data['count'] > 0 else 0:.2f}")
            
            if data.get('min_profit_threshold'):
                print(f"   Min Profit Threshold: {data['min_profit_threshold']:.6f} SOL")
            
            print("   Status: " + ("✅ Active" if self._is_pattern_active(data) else "❌ Inactive"))
            print("   ----------------------")

    def _is_pattern_active(self, pattern_data):
        """Check if a pattern is currently active"""
        # Pattern is considered active if:
        # 1. It has occurred in the last hour
        # 2. Has positive average profit
        # 3. Has occurred more than once
        return (pattern_data.get('count', 0) > 1 and 
                pattern_data.get('avg_profit', 0) > 0)

async def main_async():
    finder = JitoArbitrageFinder()
    
    print("Starting arbitrage pattern analysis...")
    
    # Start background analysis
    analysis_task = asyncio.create_task(finder.start_background_analysis())
    
    try:
        # Keep the main program running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping pattern analysis...")
        finder.stop_background_analysis()
        await analysis_task
        print("Pattern analysis stopped")

if __name__ == "__main__":
    try:
        import aiohttp
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\nExiting...")