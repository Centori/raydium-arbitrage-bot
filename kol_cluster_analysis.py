"""
KOL Cluster Analysis - Find Similar Profitable Wallets
======================================================
Given a seed wallet address, finds other wallets with similar trading patterns:
- Shared token holdings
- Similar timing patterns
- Correlated trading behavior
- Connected wallet networks

Usage:
    python3 kol_cluster_analysis.py DgNNo6zFTB5N8QGjEYkKxszMtb1a12NjwZZdgSQkBDJJ

Author: Quantitative Trading System
"""

import asyncio
import aiohttp
import json
import sys
from typing import Dict, List, Set, Tuple
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from dotenv import load_dotenv
import os

load_dotenv()


class KOLClusterAnalyzer:
    """Analyze wallet clusters and find correlated traders"""
    
    def __init__(self, helius_api_key: str):
        self.helius_api_key = helius_api_key
        self.base_url = f"https://mainnet.helius-rpc.com/?api-key={helius_api_key}"
        
        # Analysis results
        self.seed_wallet_data = {}
        self.correlated_wallets = {}
        self.shared_tokens = defaultdict(set)  # token -> set of wallets
        self.wallet_similarity_scores = {}
    
    async def analyze_seed_wallet(self, wallet_address: str, transaction_limit: int = 1000) -> Dict:
        """
        Analyze the seed wallet to understand its trading patterns
        
        Returns:
            Dict with wallet profile data
        """
        print(f"\n{'='*70}")
        print(f"🎯 ANALYZING SEED WALLET")
        print(f"{'='*70}")
        print(f"Address: {wallet_address}")
        print(f"{'='*70}\n")
        
        # Get transaction signatures
        print("📊 Fetching transaction history...")
        signatures = await self._get_signatures(wallet_address, transaction_limit)
        
        if not signatures:
            print("❌ No transactions found")
            return {}
        
        print(f"✅ Found {len(signatures)} transactions\n")
        
        # Analyze transactions to extract:
        # 1. Tokens traded
        # 2. Trading partners (other wallets in same transactions)
        # 3. Timing patterns
        
        print("🔍 Analyzing transaction patterns...")
        tokens_traded = set()
        trading_partners = Counter()
        transaction_timestamps = []
        token_first_buy = {}  # token -> timestamp
        
        sample_size = min(len(signatures), 200)  # Analyze first 200 for speed
        
        for i, sig_data in enumerate(signatures[:sample_size]):
            sig = sig_data['signature']
            timestamp = sig_data.get('blockTime', 0)
            
            if timestamp:
                transaction_timestamps.append(timestamp)
            
            # Get transaction details
            tx_details = await self._get_transaction(sig)
            
            if tx_details:
                # Extract tokens and wallets involved
                tx_tokens = self._extract_tokens_from_tx(tx_details)
                tx_wallets = self._extract_wallets_from_tx(tx_details)
                
                tokens_traded.update(tx_tokens)
                
                # Track which wallets appear with seed wallet
                for wallet in tx_wallets:
                    if wallet != wallet_address:
                        trading_partners[wallet] += 1
                
                # Track first buy timestamp for each token
                for token in tx_tokens:
                    if token not in token_first_buy and timestamp:
                        token_first_buy[token] = timestamp
            
            if (i + 1) % 20 == 0:
                print(f"   ⏳ Processed {i + 1}/{sample_size} transactions...")
            
            await asyncio.sleep(0.05)  # Rate limiting
        
        print(f"\n✅ Analysis complete!\n")
        
        # Compile seed wallet profile
        profile = {
            'address': wallet_address,
            'total_transactions': len(signatures),
            'tokens_traded': list(tokens_traded),
            'token_count': len(tokens_traded),
            'trading_partners': dict(trading_partners.most_common(50)),  # Top 50
            'frequent_partners': [w for w, c in trading_partners.most_common(20)],
            'token_first_buy': token_first_buy,
            'analysis_timestamp': datetime.now().isoformat()
        }
        
        # Calculate trading activity metrics
        if transaction_timestamps:
            timestamps_sorted = sorted(transaction_timestamps)
            profile['first_activity'] = datetime.fromtimestamp(timestamps_sorted[0]).isoformat()
            profile['last_activity'] = datetime.fromtimestamp(timestamps_sorted[-1]).isoformat()
            profile['active_days'] = (timestamps_sorted[-1] - timestamps_sorted[0]) / 86400
        
        self.seed_wallet_data = profile
        
        # Print summary
        print(f"📋 SEED WALLET PROFILE:")
        print(f"   • Total Transactions: {profile['total_transactions']}")
        print(f"   • Unique Tokens Traded: {profile['token_count']}")
        print(f"   • Frequent Trading Partners: {len(profile['frequent_partners'])}")
        print(f"   • Active Period: {profile.get('active_days', 0):.0f} days\n")
        
        return profile
    
    async def find_correlated_wallets(self, max_wallets: int = 100) -> List[Dict]:
        """
        Find wallets with similar trading patterns to seed wallet
        
        Correlation factors:
        1. Shared tokens (especially early on same tokens)
        2. Frequent co-trading (appearing in same transactions)
        3. Similar timing patterns
        
        Returns:
            List of correlated wallet profiles with similarity scores
        """
        print(f"\n{'='*70}")
        print(f"🔗 FINDING CORRELATED WALLETS")
        print(f"{'='*70}\n")
        
        if not self.seed_wallet_data:
            print("❌ No seed wallet data. Run analyze_seed_wallet first.")
            return []
        
        seed_tokens = set(self.seed_wallet_data['tokens_traded'])
        seed_first_buy = self.seed_wallet_data['token_first_buy']
        
        # Strategy 1: Analyze frequent trading partners
        print("🔍 Strategy 1: Analyzing frequent trading partners...")
        candidate_wallets = set(self.seed_wallet_data['frequent_partners'][:50])
        
        # Strategy 2: Find wallets trading same tokens
        print("🔍 Strategy 2: Finding wallets trading same tokens...")
        
        for token in list(seed_tokens)[:20]:  # Analyze top 20 tokens
            print(f"   Analyzing token: {token[:10]}...")
            token_signatures = await self._get_signatures(token, limit=500)
            
            # Extract wallets from these transactions
            for sig_data in token_signatures[:100]:  # Sample 100
                sig = sig_data['signature']
                tx = await self._get_transaction(sig)
                
                if tx:
                    wallets = self._extract_wallets_from_tx(tx)
                    candidate_wallets.update(wallets)
            
            await asyncio.sleep(0.5)  # Rate limiting
            
            if len(candidate_wallets) >= max_wallets * 2:
                break  # Enough candidates
        
        # Remove seed wallet
        candidate_wallets.discard(self.seed_wallet_data['address'])
        
        print(f"\n✅ Found {len(candidate_wallets)} candidate wallets\n")
        
        # Calculate similarity scores for each candidate
        print("📊 Calculating similarity scores...\n")
        
        correlated = []
        
        for i, candidate in enumerate(list(candidate_wallets)[:max_wallets]):
            try:
                # Get candidate's token holdings
                candidate_signatures = await self._get_signatures(candidate, limit=100)
                
                if not candidate_signatures:
                    continue
                
                candidate_tokens = set()
                candidate_first_buy = {}
                
                for sig_data in candidate_signatures[:50]:
                    sig = sig_data['signature']
                    timestamp = sig_data.get('blockTime', 0)
                    
                    try:
                        tx = await self._get_transaction(sig)
                        
                        if tx:
                            tokens = self._extract_tokens_from_tx(tx)
                            candidate_tokens.update(tokens)
                            
                            for token in tokens:
                                if token not in candidate_first_buy and timestamp:
                                    candidate_first_buy[token] = timestamp
                    except Exception:
                        continue  # Skip failed transactions
                    
                    await asyncio.sleep(0.02)
            except Exception as e:
                print(f"   ⚠️  Error analyzing wallet {candidate[:10]}: {str(e)[:50]}")
                continue
            
            # Calculate similarity score
            score = self._calculate_similarity(
                seed_tokens,
                candidate_tokens,
                seed_first_buy,
                candidate_first_buy
            )
            
            if score > 0:
                shared_tokens = seed_tokens.intersection(candidate_tokens)
                
                correlated.append({
                    'address': candidate,
                    'similarity_score': score,
                    'shared_token_count': len(shared_tokens),
                    'shared_tokens': list(shared_tokens)[:10],  # Top 10
                    'total_tokens': len(candidate_tokens),
                    'correlation_type': self._get_correlation_type(score)
                })
            
            if (i + 1) % 10 == 0:
                print(f"   ⏳ Analyzed {i + 1}/{min(len(candidate_wallets), max_wallets)} wallets...")
        
        # Sort by similarity score
        correlated.sort(key=lambda x: x['similarity_score'], reverse=True)
        
        self.correlated_wallets = {w['address']: w for w in correlated}
        
        print(f"\n✅ Found {len(correlated)} correlated wallets\n")
        
        return correlated
    
    def _calculate_similarity(self, 
                             seed_tokens: Set[str],
                             candidate_tokens: Set[str],
                             seed_first_buy: Dict[str, int],
                             candidate_first_buy: Dict[str, int]) -> float:
        """
        Calculate similarity score between seed and candidate wallet
        
        Scoring factors:
        - Shared tokens (Jaccard similarity): 0-50 points
        - Early co-investment (bought same token within 24h): 0-30 points
        - Portfolio overlap: 0-20 points
        
        Returns:
            Similarity score (0-100)
        """
        if not seed_tokens or not candidate_tokens:
            return 0.0
        
        # 1. Jaccard similarity (shared tokens)
        shared = seed_tokens.intersection(candidate_tokens)
        union = seed_tokens.union(candidate_tokens)
        jaccard = len(shared) / len(union) if union else 0
        jaccard_score = jaccard * 50
        
        # 2. Early co-investment score
        early_coinvest = 0
        for token in shared:
            if token in seed_first_buy and token in candidate_first_buy:
                time_diff = abs(seed_first_buy[token] - candidate_first_buy[token])
                
                # Within 1 hour: 5 points
                if time_diff <= 3600:
                    early_coinvest += 5
                # Within 24 hours: 3 points
                elif time_diff <= 86400:
                    early_coinvest += 3
                # Within 1 week: 1 point
                elif time_diff <= 604800:
                    early_coinvest += 1
        
        early_score = min(early_coinvest, 30)
        
        # 3. Portfolio overlap (what % of candidate's portfolio overlaps)
        overlap_ratio = len(shared) / len(candidate_tokens) if candidate_tokens else 0
        overlap_score = overlap_ratio * 20
        
        total_score = jaccard_score + early_score + overlap_score
        
        return min(total_score, 100.0)
    
    def _get_correlation_type(self, score: float) -> str:
        """Get human-readable correlation type"""
        if score >= 80:
            return "🔥 VERY STRONG"
        elif score >= 60:
            return "⭐ STRONG"
        elif score >= 40:
            return "✨ MODERATE"
        elif score >= 20:
            return "💫 WEAK"
        else:
            return "📍 MINIMAL"
    
    async def _get_signatures(self, address: str, limit: int = 1000) -> List[Dict]:
        """Get transaction signatures for an address"""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getSignaturesForAddress",
            "params": [address, {"limit": limit}]
        }
        
        timeout = aiohttp.ClientTimeout(total=30)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.base_url, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get('result', [])
                    return []
        except (asyncio.TimeoutError, aiohttp.ClientError) as e:
            print(f"   ⚠️  Timeout/Error fetching signatures for {address[:10]}...")
            return []
    
    async def _get_transaction(self, signature: str) -> Dict:
        """Get transaction details"""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTransaction",
            "params": [
                signature,
                {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}
            ]
        }
        
        timeout = aiohttp.ClientTimeout(total=10)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.base_url, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get('result', {})
                    return {}
        except (asyncio.TimeoutError, aiohttp.ClientError) as e:
            return {}
    
    def _extract_tokens_from_tx(self, tx: Dict) -> Set[str]:
        """Extract token mint addresses from transaction"""
        tokens = set()
        
        if not tx or not tx.get('transaction'):
            return tokens
        
        transaction = tx['transaction']
        message = transaction.get('message', {})
        
        # Look for token mints in account keys
        account_keys = message.get('accountKeys', [])
        
        for account in account_keys:
            if isinstance(account, dict):
                pubkey = account.get('pubkey')
                if pubkey:
                    tokens.add(pubkey)
            elif isinstance(account, str):
                tokens.add(account)
        
        # Also check instructions for SPL token transfers
        instructions = message.get('instructions', [])
        for instruction in instructions:
            if isinstance(instruction, dict):
                parsed = instruction.get('parsed', {})
                if parsed:
                    info = parsed.get('info', {})
                    if 'mint' in info:
                        tokens.add(info['mint'])
        
        return tokens
    
    def _extract_wallets_from_tx(self, tx: Dict) -> Set[str]:
        """Extract wallet addresses from transaction"""
        wallets = set()
        
        if not tx or not tx.get('transaction'):
            return wallets
        
        transaction = tx['transaction']
        message = transaction.get('message', {})
        account_keys = message.get('accountKeys', [])
        
        for account in account_keys:
            if isinstance(account, dict):
                pubkey = account.get('pubkey')
                if pubkey:
                    wallets.add(pubkey)
            elif isinstance(account, str):
                wallets.add(account)
        
        return wallets
    
    def export_results(self, output_file: str = "kol_cluster_analysis.json"):
        """Export cluster analysis results"""
        results = {
            'analysis_timestamp': datetime.now().isoformat(),
            'seed_wallet': self.seed_wallet_data,
            'correlated_wallets': list(self.correlated_wallets.values()),
            'summary': {
                'total_correlated': len(self.correlated_wallets),
                'very_strong': len([w for w in self.correlated_wallets.values() if w['similarity_score'] >= 80]),
                'strong': len([w for w in self.correlated_wallets.values() if 60 <= w['similarity_score'] < 80]),
                'moderate': len([w for w in self.correlated_wallets.values() if 40 <= w['similarity_score'] < 60])
            }
        }
        
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"✅ Results exported to: {output_file}")
    
    def print_results(self, top_n: int = 20):
        """Print formatted results"""
        print(f"\n{'='*70}")
        print(f"🏆 TOP {top_n} CORRELATED WALLETS")
        print(f"{'='*70}\n")
        
        sorted_wallets = sorted(
            self.correlated_wallets.values(),
            key=lambda x: x['similarity_score'],
            reverse=True
        )[:top_n]
        
        for i, wallet in enumerate(sorted_wallets, 1):
            print(f"{i:2d}. {wallet['correlation_type']}")
            print(f"    Address: {wallet['address'][:15]}...{wallet['address'][-15:]}")
            print(f"    Similarity Score: {wallet['similarity_score']:.1f}/100")
            print(f"    Shared Tokens: {wallet['shared_token_count']}")
            print(f"    Total Tokens: {wallet['total_tokens']}")
            print()


async def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print("Usage: python3 kol_cluster_analysis.py <seed_wallet_address>")
        print("\nExample:")
        print("  python3 kol_cluster_analysis.py DgNNo6zFTB5N8QGjEYkKxszMtb1a12NjwZZdgSQkBDJJ")
        sys.exit(1)
    
    seed_wallet = sys.argv[1]
    
    # Get Helius API key
    helius_api_key = os.getenv('HELIUS_API_KEY')
    if not helius_api_key:
        print("❌ HELIUS_API_KEY not found in .env file")
        sys.exit(1)
    
    # Initialize analyzer
    analyzer = KOLClusterAnalyzer(helius_api_key)
    
    # Analyze seed wallet
    await analyzer.analyze_seed_wallet(seed_wallet, transaction_limit=1000)
    
    # Find correlated wallets
    correlated = await analyzer.find_correlated_wallets(max_wallets=50)
    
    # Print results
    analyzer.print_results(top_n=20)
    
    # Export
    output_file = f"cluster_analysis_{seed_wallet[:10]}.json"
    analyzer.export_results(output_file)
    
    # Create watchlist
    watchlist = {
        'created_at': datetime.now().isoformat(),
        'seed_wallet': seed_wallet,
        'cluster_size': len(correlated),
        'wallets': [
            {
                'address': w['address'],
                'similarity_score': w['similarity_score'],
                'shared_tokens': w['shared_token_count'],
                'priority': 'high' if w['similarity_score'] >= 60 else 'medium',
                'alert_on_new_position': True
            }
            for w in correlated[:30]  # Top 30
        ]
    }
    
    watchlist_file = f"watchlist_{seed_wallet[:10]}.json"
    with open(watchlist_file, 'w') as f:
        json.dump(watchlist, f, indent=2)
    
    print(f"✅ Watchlist exported to: {watchlist_file}")
    
    print(f"\n{'='*70}")
    print("✨ CLUSTER ANALYSIS COMPLETE")
    print(f"{'='*70}")
    print(f"Seed Wallet: {seed_wallet}")
    print(f"Correlated Wallets Found: {len(correlated)}")
    print(f"Very Strong Correlation (≥80): {len([w for w in correlated if w['similarity_score'] >= 80])}")
    print(f"Strong Correlation (60-79): {len([w for w in correlated if 60 <= w['similarity_score'] < 80])}")
    print(f"Moderate Correlation (40-59): {len([w for w in correlated if 40 <= w['similarity_score'] < 60])}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    asyncio.run(main())
