#!/usr/bin/env python3
"""
Trending token fetcher for Solana using DexScreener.
- Fetch recent/high-volume Solana pairs
- Filter for sufficient liquidity and recency
- Return base token addresses to monitor
"""

import aiohttp
import logging
import time
from typing import List, Dict

logger = logging.getLogger("TrendingFetcher")

DEXSCREENER_PAIRS_URL = "https://api.dexscreener.com/latest/dex/pairs/solana"


async def fetch_trending_solana(limit: int = 10,
                                min_liquidity_usd: float = 50000,
                                max_pair_age_minutes: int = 180,
                                min_volume_h1_usd: float = 20000) -> List[str]:
    """
    Fetch trending/new Solana token addresses from DexScreener.
    Filters:
    - Liquidity >= min_liquidity_usd
    - Pair age <= max_pair_age_minutes
    - 1h volume >= min_volume_h1_usd
    Returns list of base token addresses (mint addresses)
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(DEXSCREENER_PAIRS_URL, timeout=10) as resp:
                if resp.status != 200:
                    logger.warning(f"DexScreener pairs status={resp.status}")
                    return []
                data = await resp.json()
                pairs = data.get('pairs', [])
                now_ms = int(time.time() * 1000)
                results: List[Dict] = []
                for p in pairs:
                    try:
                        liq_usd = float((p.get('liquidity') or {}).get('usd') or 0)
                        vol_h1 = float((p.get('volume') or {}).get('h1') or 0)
                        created_at = int(p.get('pairCreatedAt') or 0)
                        age_min = (now_ms - created_at) / 60000 if created_at else 1e9
                        chain_id = p.get('chainId')
                        if chain_id != 'solana':
                            continue
                        base = (p.get('baseToken') or {}).get('address')
                        quote = (p.get('quoteToken') or {}).get('symbol', '').upper()
                        # Skip stable/bluechips as quote to avoid known pairs
                        if not base:
                            continue
                        if liq_usd < min_liquidity_usd:
                            continue
                        if age_min > max_pair_age_minutes:
                            continue
                        if vol_h1 < min_volume_h1_usd:
                            continue
                        # Skip if base is SOL/USDC addresses
                        if base in {
                            'So11111111111111111111111111111111111111112',
                            'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v'
                        }:
                            continue
                        results.append({
                            'base': base,
                            'liq': liq_usd,
                            'vol_h1': vol_h1,
                            'age_min': age_min
                        })
                    except Exception:
                        continue
                # Sort by highest 1h volume, then youngest
                results.sort(key=lambda r: (r['vol_h1'], -r['age_min']), reverse=True)
                addrs = [r['base'] for r in results[:limit]]
                logger.info(f"Trending tokens fetched: {len(addrs)}")
                return addrs
    except Exception as e:
        logger.error(f"Trending fetch failed: {e}")
        return []
