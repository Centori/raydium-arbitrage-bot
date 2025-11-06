"""
Fast KOL Cluster Analysis - Optimized Version
==============================================
Faster version that prioritizes high-value correlations and reduces API calls.

Usage:
    python3 kol_cluster_fast.py DgNNo6zFTB5N8QGjEYkKxszMtb1a12NjwZZdgSQkBDJJ
"""

import asyncio
import aiohttp
import json
import sys
from typing import Dict, List, Set
from datetime import datetime
from collections import defaultdict, Counter
from dotenv import load_dotenv
import os

load_dotenv()


async def analyze_wallet_fast(wallet: str, helius_key: str, max_sigs: int = 100) -> Dict:
    """Quick wallet analysis - tokens only"""
    url = f"https://mainnet.helius-rpc.com/?api-key={helius_key}"
    
    # Get signatures
    payload = {"jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress", 
               "params": [wallet, {"limit": max_sigs}]}
    
    timeout = aiohttp.ClientTimeout(total=20)
    tokens = set()
    timestamps = {}
    
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    sigs = data.get('result', [])
                    
                    # Sample transactions
                    for sig_data in sigs[:50]:
                        sig = sig_data['signature']
                        ts = sig_data.get('blockTime', 0)
                        
                        # Get transaction
                        tx_payload = {"jsonrpc": "2.0", "id": 1, "method": "getTransaction",
                                    "params": [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]}
                        
                        try:
                            async with session.post(url, json=tx_payload) as tx_resp:
                                if tx_resp.status == 200:
                                    tx_data = await tx_resp.json()
                                    result = tx_data.get('result', {})
                                    
                                    if result and result.get('transaction'):
                                        message = result['transaction'].get('message', {})
                                        accounts = message.get('accountKeys', [])
                                        
                                        for acc in accounts:
                                            addr = acc.get('pubkey') if isinstance(acc, dict) else acc
                                            if addr:
                                                tokens.add(addr)
                                                if addr not in timestamps and ts:
                                                    timestamps[addr] = ts
                        except:
                            continue
                        
                        await asyncio.sleep(0.03)
        
        return {'tokens': tokens, 'timestamps': timestamps, 'count': len(tokens)}
    
    except Exception as e:
        return {'tokens': set(), 'timestamps': {}, 'count': 0}


async def main():
    if len(sys.argv) < 2:
        print("Usage: python3 kol_cluster_fast.py <wallet_address>")
        sys.exit(1)
    
    seed_wallet = sys.argv[1]
    helius_key = os.getenv('HELIUS_API_KEY')
    
    if not helius_key:
        print("❌ HELIUS_API_KEY not found")
        sys.exit(1)
    
    print(f"\n{'='*70}")
    print(f"🎯 FAST CLUSTER ANALYSIS")
    print(f"{'='*70}")
    print(f"Seed Wallet: {seed_wallet}\n")
    
    # Analyze seed
    print("📊 Analyzing seed wallet...")
    seed_data = await analyze_wallet_fast(seed_wallet, helius_key, max_sigs=200)
    seed_tokens = seed_data['tokens']
    seed_ts = seed_data['timestamps']
    
    print(f"✅ Seed wallet trades {len(seed_tokens)} unique tokens\n")
    
    # Get candidate wallets from top tokens
    print("🔍 Finding candidate wallets from top tokens...")
    candidates = set()
    
    for i, token in enumerate(list(seed_tokens)[:15]):  # Top 15 tokens only
        print(f"   Scanning token {i+1}/15: {token[:10]}...")
        
        url = f"https://mainnet.helius-rpc.com/?api-key={helius_key}"
        payload = {"jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress",
                  "params": [token, {"limit": 200}]}
        
        timeout = aiohttp.ClientTimeout(total=20)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        sigs = data.get('result', [])
                        
                        # Get wallets from first 30 transactions
                        for sig_data in sigs[:30]:
                            sig = sig_data['signature']
                            
                            tx_payload = {"jsonrpc": "2.0", "id": 1, "method": "getTransaction",
                                        "params": [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]}
                            
                            try:
                                async with session.post(url, json=tx_payload) as tx_resp:
                                    if tx_resp.status == 200:
                                        tx_data = await tx_resp.json()
                                        result = tx_data.get('result', {})
                                        
                                        if result and result.get('transaction'):
                                            message = result['transaction'].get('message', {})
                                            accounts = message.get('accountKeys', [])
                                            
                                            for acc in accounts:
                                                addr = acc.get('pubkey') if isinstance(acc, dict) else acc
                                                if addr and addr != seed_wallet and addr != token:
                                                    candidates.add(addr)
                            except:
                                continue
                            
                            await asyncio.sleep(0.02)
        except:
            continue
        
        await asyncio.sleep(0.3)
        
        if len(candidates) >= 40:
            break
    
    candidates.discard(seed_wallet)
    print(f"\n✅ Found {len(candidates)} candidate wallets\n")
    
    # Analyze candidates
    print("📊 Analyzing candidates for correlation...\n")
    
    correlated = []
    
    for i, candidate in enumerate(list(candidates)[:30]):  # Top 30 only
        print(f"   Analyzing {i+1}/30: {candidate[:10]}...")
        
        cand_data = await analyze_wallet_fast(candidate, helius_key, max_sigs=100)
        cand_tokens = cand_data['tokens']
        cand_ts = cand_data['timestamps']
        
        if not cand_tokens:
            continue
        
        # Calculate similarity
        shared = seed_tokens.intersection(cand_tokens)
        
        if len(shared) < 3:  # Need at least 3 shared tokens
            continue
        
        # Jaccard similarity
        union = seed_tokens.union(cand_tokens)
        jaccard = len(shared) / len(union) * 50
        
        # Early co-investment
        early_score = 0
        for token in list(shared)[:20]:
            if token in seed_ts and token in cand_ts:
                diff = abs(seed_ts[token] - cand_ts[token])
                if diff <= 3600:  # 1 hour
                    early_score += 5
                elif diff <= 86400:  # 24 hours
                    early_score += 3
        
        early_score = min(early_score, 30)
        
        # Portfolio overlap
        overlap = len(shared) / len(cand_tokens) * 20
        
        score = jaccard + early_score + overlap
        
        if score >= 20:  # Minimum threshold
            tier = "🔥 VERY STRONG" if score >= 80 else "⭐ STRONG" if score >= 60 else "✨ MODERATE" if score >= 40 else "💫 WEAK"
            
            correlated.append({
                'address': candidate,
                'score': score,
                'shared': len(shared),
                'total': len(cand_tokens),
                'tier': tier
            })
    
    # Sort by score
    correlated.sort(key=lambda x: x['score'], reverse=True)
    
    # Print results
    print(f"\n{'='*70}")
    print(f"🏆 TOP CORRELATED WALLETS")
    print(f"{'='*70}\n")
    
    for i, w in enumerate(correlated[:20], 1):
        print(f"{i:2d}. {w['tier']}")
        print(f"    Address: {w['address'][:15]}...{w['address'][-15:]}")
        print(f"    Score: {w['score']:.1f}/100")
        print(f"    Shared Tokens: {w['shared']}")
        print(f"    Total Tokens: {w['total']}")
        print()
    
    # Export
    results = {
        'timestamp': datetime.now().isoformat(),
        'seed_wallet': seed_wallet,
        'seed_token_count': len(seed_tokens),
        'candidates_analyzed': len(candidates),
        'correlated_wallets': correlated
    }
    
    output_file = f"cluster_fast_{seed_wallet[:10]}.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"✅ Results exported to: {output_file}")
    
    # Create watchlist
    watchlist = {
        'created_at': datetime.now().isoformat(),
        'seed_wallet': seed_wallet,
        'wallets': [
            {
                'address': w['address'],
                'score': w['score'],
                'shared_tokens': w['shared'],
                'priority': 'high' if w['score'] >= 60 else 'medium'
            }
            for w in correlated[:20]
        ]
    }
    
    watchlist_file = f"watchlist_fast_{seed_wallet[:10]}.json"
    with open(watchlist_file, 'w') as f:
        json.dump(watchlist, f, indent=2)
    
    print(f"✅ Watchlist exported to: {watchlist_file}")
    
    print(f"\n{'='*70}")
    print("✨ ANALYSIS COMPLETE")
    print(f"{'='*70}")
    print(f"Correlated Wallets: {len(correlated)}")
    print(f"Very Strong (≥80): {len([w for w in correlated if w['score'] >= 80])}")
    print(f"Strong (60-79): {len([w for w in correlated if 60 <= w['score'] < 80])}")
    print(f"Moderate (40-59): {len([w for w in correlated if 40 <= w['score'] < 60])}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    asyncio.run(main())
