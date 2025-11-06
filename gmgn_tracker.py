import asyncio
import logging
import aiohttp
from typing import List, Dict, Optional
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime

logger = logging.getLogger("gmgn_tracker")

@dataclass
class SmartMoneyWallet:
    """Smart money wallet from GMGN.ai"""
    address: str
    pnl_30d: Decimal
    win_rate: float
    total_trades: int
    realized_profit: Decimal
    unrealized_profit: Decimal
    score: float  # GMGN's internal score

@dataclass
class TokenActivity:
    """Token activity from smart money"""
    token_mint: str
    token_symbol: str
    smart_money_holders: int
    total_smart_money_value: Decimal
    recent_buys: int
    recent_sells: int
    net_flow: Decimal  # Positive = accumulation, Negative = distribution
    avg_entry_price: Decimal

class GMGNTracker:
    """Track smart money using GMGN.ai API (free tier)"""
    
    BASE_URL = "https://gmgn.ai/defi/quotation/v1"
    
    def __init__(self, config):
        self.config = config
        self.smart_wallets_cache = {}
        self.token_activity_cache = {}
        
    async def get_smart_money_wallets(self, chain: str = "sol", limit: int = 100) -> List[SmartMoneyWallet]:
        """
        Get top smart money wallets from GMGN.ai
        Free endpoint - no API key needed
        """
        try:
            url = f"{self.BASE_URL}/smartmoney/sol/walletAddresslist"
            
            params = {
                "limit": limit,
                "orderby": "pnl_30d",  # Sort by 30-day profit
                "direction": "desc"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
                        wallets = []
                        for item in data.get('data', {}).get('rank', []):
                            wallet = SmartMoneyWallet(
                                address=item.get('wallet_address', ''),
                                pnl_30d=Decimal(str(item.get('pnl_30d', 0))),
                                win_rate=float(item.get('winrate', 0)),
                                total_trades=int(item.get('trade_30d', 0)),
                                realized_profit=Decimal(str(item.get('realized_profit', 0))),
                                unrealized_profit=Decimal(str(item.get('unrealized_profit', 0))),
                                score=float(item.get('score', 0))
                            )
                            wallets.append(wallet)
                        
                        logger.info(f"Fetched {len(wallets)} smart money wallets from GMGN.ai")
                        self.smart_wallets_cache = {w.address: w for w in wallets}
                        return wallets
                    else:
                        logger.error(f"GMGN API error: {resp.status}")
                        return []
                        
        except asyncio.TimeoutError:
            logger.warning("GMGN API timeout")
            return []
        except Exception as e:
            logger.error(f"Error fetching smart money wallets: {e}")
            return []
    
    async def get_token_smart_money_activity(self, token_mint: str) -> Optional[TokenActivity]:
        """
        Get smart money activity for a specific token
        Shows if smart money is buying or selling
        """
        try:
            url = f"{self.BASE_URL}/tokens/sol/{token_mint}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        token_data = data.get('data', {})
                        
                        # Get smart money holder info
                        smart_money_data = token_data.get('smart_money', {})
                        
                        activity = TokenActivity(
                            token_mint=token_mint,
                            token_symbol=token_data.get('symbol', 'UNKNOWN'),
                            smart_money_holders=int(smart_money_data.get('holder_count', 0)),
                            total_smart_money_value=Decimal(str(smart_money_data.get('total_value_usd', 0))),
                            recent_buys=int(smart_money_data.get('buy_24h', 0)),
                            recent_sells=int(smart_money_data.get('sell_24h', 0)),
                            net_flow=Decimal(str(smart_money_data.get('net_flow_24h', 0))),
                            avg_entry_price=Decimal(str(smart_money_data.get('avg_cost', 0)))
                        )
                        
                        self.token_activity_cache[token_mint] = activity
                        return activity
                    elif resp.status == 404:
                        logger.debug(f"Token {token_mint} not found on GMGN.ai")
                        return None
                    else:
                        logger.error(f"GMGN API error: {resp.status}")
                        return None
                        
        except asyncio.TimeoutError:
            logger.warning(f"GMGN API timeout for token {token_mint}")
            return None
        except Exception as e:
            logger.error(f"Error fetching token activity: {e}")
            return None
    
    async def get_wallet_positions(self, wallet_address: str) -> List[Dict]:
        """Get current token positions for a wallet"""
        try:
            url = f"{self.BASE_URL}/smartmoney/sol/walletNew/{wallet_address}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        positions = data.get('data', {}).get('holdings', [])
                        
                        parsed_positions = []
                        for pos in positions:
                            parsed_positions.append({
                                'token_address': pos.get('address'),
                                'token_symbol': pos.get('symbol'),
                                'amount': Decimal(str(pos.get('amount', 0))),
                                'value_usd': Decimal(str(pos.get('value_usd', 0))),
                                'cost_usd': Decimal(str(pos.get('cost_usd', 0))),
                                'pnl_usd': Decimal(str(pos.get('pnl', 0))),
                                'pnl_percent': float(pos.get('pnl_percent', 0))
                            })
                        
                        return parsed_positions
                    else:
                        logger.error(f"GMGN API error: {resp.status}")
                        return []
                        
        except Exception as e:
            logger.error(f"Error fetching wallet positions: {e}")
            return []
    
    async def get_trending_tokens(self, timeframe: str = "24h") -> List[Dict]:
        """
        Get trending tokens based on smart money activity
        timeframe: '24h', '12h', '6h', '1h'
        """
        try:
            url = f"{self.BASE_URL}/tokens/sol/trending/{timeframe}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        tokens = data.get('data', [])
                        
                        trending = []
                        for token in tokens:
                            trending.append({
                                'token_address': token.get('address'),
                                'token_symbol': token.get('symbol'),
                                'price': Decimal(str(token.get('price', 0))),
                                'price_change_pct': float(token.get('price_change', 0)),
                                'volume_24h': Decimal(str(token.get('volume_24h', 0))),
                                'smart_money_buy_count': int(token.get('smart_buy_count', 0)),
                                'market_cap': Decimal(str(token.get('market_cap', 0)))
                            })
                        
                        logger.info(f"Fetched {len(trending)} trending tokens")
                        return trending
                    else:
                        logger.error(f"GMGN API error: {resp.status}")
                        return []
                        
        except Exception as e:
            logger.error(f"Error fetching trending tokens: {e}")
            return []
    
    def get_signal_for_token(self, token_mint: str) -> Optional[Dict]:
        """
        Generate trading signal based on smart money activity
        Returns: {'action': 'buy'|'sell'|'hold', 'confidence': 0-100, 'reason': str}
        """
        try:
            activity = self.token_activity_cache.get(token_mint)
            if not activity:
                return None
            
            # Calculate signal strength
            confidence = 0
            reasons = []
            
            # Check net flow
            if activity.net_flow > 0:
                confidence += 40
                reasons.append(f"Smart money accumulating (${float(activity.net_flow):,.0f})")
            elif activity.net_flow < 0:
                confidence -= 40
                reasons.append(f"Smart money distributing (${float(abs(activity.net_flow)):,.0f})")
            
            # Check buy/sell ratio
            if activity.recent_buys > 0 and activity.recent_sells > 0:
                buy_sell_ratio = activity.recent_buys / activity.recent_sells
                if buy_sell_ratio > 2:
                    confidence += 30
                    reasons.append(f"High buy pressure ({activity.recent_buys} buys vs {activity.recent_sells} sells)")
                elif buy_sell_ratio < 0.5:
                    confidence -= 30
                    reasons.append(f"High sell pressure ({activity.recent_sells} sells vs {activity.recent_buys} buys)")
            
            # Check holder count
            if activity.smart_money_holders >= 10:
                confidence += 20
                reasons.append(f"{activity.smart_money_holders} smart money holders")
            elif activity.smart_money_holders < 3:
                confidence -= 10
                reasons.append("Few smart money holders")
            
            # Check total value
            if activity.total_smart_money_value > 50000:
                confidence += 10
                reasons.append(f"High smart money TVL (${float(activity.total_smart_money_value):,.0f})")
            
            # Determine action
            if confidence >= 60:
                action = "buy"
            elif confidence <= -30:
                action = "sell"
            else:
                action = "hold"
            
            return {
                'action': action,
                'confidence': min(100, max(0, confidence + 50)),  # Normalize to 0-100
                'reason': "; ".join(reasons),
                'smart_money_holders': activity.smart_money_holders,
                'net_flow_24h': float(activity.net_flow)
            }
            
        except Exception as e:
            logger.error(f"Error generating signal: {e}")
            return None
    
    async def monitor_smart_money_for_token(self, token_mint: str) -> bool:
        """
        Check if smart money is interested in a token
        Returns True if token passes smart money filter
        """
        try:
            activity = await self.get_token_smart_money_activity(token_mint)
            
            if not activity:
                logger.debug(f"No GMGN data for token {token_mint}")
                return False
            
            # Filter criteria
            if activity.smart_money_holders < 3:
                logger.debug(f"Token {token_mint} has only {activity.smart_money_holders} smart money holders")
                return False
            
            if activity.net_flow < 0:
                logger.debug(f"Token {token_mint} has negative net flow: ${float(activity.net_flow)}")
                return False
            
            if activity.recent_sells > activity.recent_buys:
                logger.debug(f"Token {token_mint} has more sells than buys")
                return False
            
            logger.info(f"Token {token_mint} passes smart money filter: "
                       f"{activity.smart_money_holders} holders, "
                       f"${float(activity.net_flow):,.0f} net flow")
            return True
            
        except Exception as e:
            logger.error(f"Error monitoring smart money: {e}")
            return False
