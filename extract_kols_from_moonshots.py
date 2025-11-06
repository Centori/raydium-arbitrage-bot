"""
Extract KOL Wallets from Moonshot Tokens
========================================
Uses Helius API to fetch transaction data and identify wallet addresses
of traders who achieved massive returns.

Usage:
    python3 extract_kols_from_moonshots.py data/kol_test/kol_discovery_results.json
"""

import asyncio
import aiohttp
import json
import sys
from typing import List, Dict, Set
from datetime import datetime
from collections import defaultdict
from dotenv import load_dotenv
import os

load_dotenv()

async def get_token_transactions_helius(token_mint: str, helius_api_key: str, limit: int = 1000) -> List[Dict]:
    """Get transaction signatures for a token using Helius"""
    url = f"https://mainnet.helius-rpc.com/?api-key={helius_api_key}"
    
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getSignaturesForAddress",
        "params": [token_mint, {"limit": limit}]
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as response:
            if response.status != 200:
                print(f"❌ Helius API error: {response.status}")
                return []
            
            data = await response.json()
            return data.get('result', [])


async def extract_wallets_from_transactions(signatures: List[Dict], helius_api_key: str, sample_size: int = 50) -> Set[str]:
    """Extract unique wallet addresses from transactions"""
    url = f"https://mainnet.helius-rpc.com/?api-key={helius_api_key}"
    wallets = set()
    
    print(f"   📊 Analyzing {min(len(signatures), sample_size)} transactions...")
    
    async with aiohttp.ClientSession() as session:
        for i, sig_data in enumerate(signatures[:sample_size]):
            sig = sig_data['signature']
            
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTransaction",
                "params": [
                    sig,
                    {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}
                ]
            }
            
            try:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        result = data.get('result')
                        
                        if result and result.get('transaction'):
                            tx = result['transaction']
                            message = tx.get('message', {})
                            account_keys = message.get('accountKeys', [])
                            
                            # Extract wallet addresses
                            for account in account_keys:
                                if isinstance(account, dict):
                                    pubkey = account.get('pubkey')
                                    if pubkey:
                                        wallets.add(pubkey)
                                elif isinstance(account, str):
                                    wallets.add(account)
                
                if (i + 1) % 10 == 0:
                    print(f"   ⏳ Processed {i + 1}/{min(len(signatures), sample_size)} transactions...")
                
                await asyncio.sleep(0.05)  # Rate limiting
                
            except Exception as e:
                print(f"   ⚠️  Error processing transaction {i}: {e}")
                continue
    
    return wallets


async def analyze_moonshot_file(filepath: str):
    """Main analysis function"""
    helius_api_key = os.getenv('HELIUS_API_KEY')
    if not helius_api_key:
        print("❌ HELIUS_API_KEY not found in .env file")
        return
    
    print(f"\n🔍 Loading moonshot data from: {filepath}\n")
    
    # Load moonshot data
    with open(filepath, 'r') as f:
        data = json.load(f)
    
    moonshots = data.get('moonshots', [])
    
    if not moonshots:
        print("❌ No moonshots found in file")
        return
    
    print(f"✅ Found {len(moonshots)} moonshot tokens\n")
    
    # Track all unique wallets and their token interactions
    all_kol_wallets = defaultdict(lambda: {
        'tokens_traded': [],
        'moonshot_count': 0,
        'max_roi': 0
    })
    
    # Process each moonshot
    for i, moonshot in enumerate(moonshots, 1):
        mint = moonshot['mint']
        symbol = moonshot['symbol']
        roi = moonshot['max_roi']
        
        print(f"{'='*60}")
        print(f"🚀 Moonshot #{i}: {symbol}")
        print(f"   Address: {mint}")
        print(f"   ROI: {roi:,.1f}x")
        print(f"   Volume 24h: ${moonshot['volume_24h']:,.0f}")
        print(f"   Liquidity: ${moonshot['liquidity_usd']:,.0f}")
        print(f"{'='*60}\n")
        
        # Get transactions
        print(f"   🔄 Fetching transactions from Helius...")
        signatures = await get_token_transactions_helius(mint, helius_api_key, limit=1000)
        
        if not signatures:
            print(f"   ⚠️  No transactions found\n")
            continue
        
        print(f"   ✅ Found {len(signatures)} transactions\n")
        
        # Extract wallets
        wallets = await extract_wallets_from_transactions(signatures, helius_api_key, sample_size=100)
        
        print(f"\n   ✅ Extracted {len(wallets)} unique wallet addresses\n")
        
        # Update KOL database
        for wallet in wallets:
            all_kol_wallets[wallet]['tokens_traded'].append(mint)
            all_kol_wallets[wallet]['moonshot_count'] += 1
            all_kol_wallets[wallet]['max_roi'] = max(
                all_kol_wallets[wallet]['max_roi'],
                roi
            )
        
        # Rate limiting between tokens
        await asyncio.sleep(1)
    
    # Calculate KOL scores and rank
    print(f"\n{'='*60}")
    print("📊 KOL ANALYSIS RESULTS")
    print(f"{'='*60}\n")
    
    kol_list = []
    for wallet, data in all_kol_wallets.items():
        # Calculate score
        score = 50  # Base
        score += data['moonshot_count'] * 15  # +15 per moonshot
        score += min(data['max_roi'] / 100, 20)  # +0.01 per 1x ROI, capped at 20
        
        kol_list.append({
            'address': wallet,
            'moonshot_count': data['moonshot_count'],
            'max_roi': data['max_roi'],
            'tokens_traded': len(data['tokens_traded']),
            'score': min(score, 100)
        })
    
    # Sort by score
    kol_list.sort(key=lambda x: x['score'], reverse=True)
    
    # Show top 20 KOLs
    print(f"🏆 TOP 20 KOL WALLETS:\n")
    for i, kol in enumerate(kol_list[:20], 1):
        tier = "🌟 LEGENDARY" if kol['score'] >= 90 else "⭐ ELITE" if kol['score'] >= 80 else "✨ SKILLED"
        print(f"{i:2d}. {tier}")
        print(f"    Address: {kol['address'][:10]}...{kol['address'][-10:]}")
        print(f"    Score: {kol['score']:.1f}")
        print(f"    Moonshots: {kol['moonshot_count']}")
        print(f"    Max ROI: {kol['max_roi']:,.1f}x")
        print(f"    Tokens Traded: {kol['tokens_traded']}")
        print()
    
    # Export results
    output_file = filepath.replace('.json', '_with_kols.json')
    
    export_data = {
        'analysis_timestamp': datetime.now().isoformat(),
        'original_moonshots': len(moonshots),
        'total_unique_wallets': len(all_kol_wallets),
        'elite_kols': len([k for k in kol_list if k['score'] >= 80]),
        'moonshots': moonshots,
        'top_kols': kol_list[:100]  # Top 100
    }
    
    with open(output_file, 'w') as f:
        json.dump(export_data, f, indent=2)
    
    print(f"\n✅ Results exported to: {output_file}")
    
    # Create monitoring watchlist
    watchlist_file = filepath.replace('.json', '_watchlist.json')
    
    watchlist = {
        'created_at': datetime.now().isoformat(),
        'kol_count': len(kol_list[:50]),
        'wallets': [
            {
                'address': kol['address'],
                'score': kol['score'],
                'moonshot_count': kol['moonshot_count'],
                'priority': 'high' if kol['score'] >= 80 else 'medium',
                'alert_on_new_position': True,
                'min_trade_size_usd': 1000
            }
            for kol in kol_list[:50]  # Top 50 for monitoring
        ]
    }
    
    with open(watchlist_file, 'w') as f:
        json.dump(watchlist, f, indent=2)
    
    print(f"✅ Watchlist exported to: {watchlist_file}")
    
    print(f"\n{'='*60}")
    print("✨ SUMMARY")
    print(f"{'='*60}")
    print(f"Total Moonshots Analyzed: {len(moonshots)}")
    print(f"Total Unique Wallets: {len(all_kol_wallets):,}")
    print(f"Elite KOLs (score ≥80): {len([k for k in kol_list if k['score'] >= 80])}")
    print(f"Top KOLs in Watchlist: {len(watchlist['wallets'])}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 extract_kols_from_moonshots.py <path_to_kol_discovery_results.json>")
        sys.exit(1)
    
    filepath = sys.argv[1]
    
    if not os.path.exists(filepath):
        print(f"❌ File not found: {filepath}")
        sys.exit(1)
    
    asyncio.run(analyze_moonshot_file(filepath))
