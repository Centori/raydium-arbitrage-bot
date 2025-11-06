#!/usr/bin/env python3
"""
On-Chain Smart Money Detector
Analyzes recent transactions to identify whale wallets and successful traders
"""

import asyncio
import logging
from typing import List, Dict, Set, Optional
from collections import defaultdict
from dataclasses import dataclass
from solana.rpc.async_api import AsyncClient
from solders.pubkey import Pubkey

logger = logging.getLogger("SmartMoneyDetector")


@dataclass
class WalletActivity:
    """Track wallet trading activity"""
    address: str
    total_volume_sol: float = 0.0
    buy_count: int = 0
    sell_count: int = 0
    tokens_traded: Set[str] = None
    avg_trade_size_sol: float = 0.0
    
    def __post_init__(self):
        if self.tokens_traded is None:
            self.tokens_traded = set()
    
    def add_trade(self, token: str, amount_sol: float, is_buy: bool):
        """Record a trade"""
        self.total_volume_sol += amount_sol
        self.tokens_traded.add(token)
        
        if is_buy:
            self.buy_count += 1
        else:
            self.sell_count += 1
        
        # Update average
        total_trades = self.buy_count + self.sell_count
        if total_trades > 0:
            self.avg_trade_size_sol = self.total_volume_sol / total_trades
    
    def is_whale(self, min_volume: float = 10.0, min_avg_size: float = 1.0) -> bool:
        """Check if wallet qualifies as whale"""
        return (self.total_volume_sol >= min_volume and 
                self.avg_trade_size_sol >= min_avg_size)
    
    def is_active_trader(self, min_trades: int = 5) -> bool:
        """Check if wallet is actively trading"""
        return (self.buy_count + self.sell_count) >= min_trades


class SmartMoneyDetector:
    """Detect smart money wallets from on-chain activity"""
    
    def __init__(self, rpc_client: AsyncClient):
        self.client = rpc_client
        self.known_whales: Dict[str, WalletActivity] = {}
        self.last_scan_signature: Optional[str] = None
        self.last_rpc_call = 0.0  # Track last RPC call for rate limiting
        
        # Whale detection thresholds
        self.min_whale_volume = 10.0  # 10 SOL total volume
        self.min_whale_trade_size = 1.0  # 1 SOL avg trade size
        self.min_trades_for_active = 5
        
        # Rate limiting (avoid 429 errors)
        self.min_rpc_delay = 0.5  # Minimum 500ms between RPC calls
        self.batch_delay = 2.0  # 2 second delay between transaction batches
        
    async def scan_token_transactions(self, token_address: str, limit: int = 100) -> Dict[str, WalletActivity]:
        """
        Scan recent transactions for a token to find whale wallets
        Returns dict of wallet_address -> WalletActivity
        """
        try:
            wallets = defaultdict(lambda: WalletActivity(address=""))
            
            # Get token account (need to query properly)
            token_pubkey = Pubkey.from_string(token_address)
            
            # Get recent signatures for this token
            # Note: This is a simplified version - production would need to:
            # 1. Get the token's SPL token program transactions
            # 2. Parse swap instructions from Raydium/Jupiter/Orca
            # 3. Extract wallet addresses and amounts
            
            try:
                # Rate limit before RPC call
                await self._rate_limit()
                
                # Get recent signatures
                sigs_resp = await self.client.get_signatures_for_address(
                    token_pubkey,
                    limit=limit
                )
                
                if not sigs_resp.value:
                    logger.warning(f"No signatures found for {token_address}")
                    return {}
                
                signatures = sigs_resp.value[:limit]
                logger.info(f"Analyzing {len(signatures)} transactions for {token_address[:8]}...")
                
                # Fetch and parse transactions in smaller batches
                batch_size = 5  # Process 5 transactions at a time
                for i in range(0, min(20, len(signatures)), batch_size):
                    batch = signatures[i:i+batch_size]
                    
                    for sig_info in batch:
                        try:
                            sig = str(sig_info.signature)
                            
                            # Rate limit before each RPC call
                            await self._rate_limit()
                            
                            # Get transaction details
                            tx_resp = await self.client.get_transaction(
                                sig,
                                encoding="jsonParsed",
                                max_supported_transaction_version=0
                            )
                            
                            if not tx_resp.value:
                                continue
                            
                            tx = tx_resp.value
                            
                            # Parse transaction to extract wallet activity
                            parsed_wallets = self._parse_transaction(tx, token_address)
                            
                            for wallet_addr, activity in parsed_wallets.items():
                                if wallet_addr not in wallets:
                                    wallets[wallet_addr].address = wallet_addr
                                
                                # Merge activity
                                for token in activity.tokens_traded:
                                    wallets[wallet_addr].add_trade(
                                        token,
                                        activity.avg_trade_size_sol,
                                        activity.buy_count > 0
                                    )
                        
                        except Exception as e:
                            logger.debug(f"Error parsing transaction {sig}: {e}")
                            continue
                    
                    # Delay between batches to avoid rate limits
                    if i + batch_size < min(20, len(signatures)):
                        logger.debug(f"Batch complete, waiting {self.batch_delay}s...")
                        await asyncio.sleep(self.batch_delay)
                        
                
                # Filter for whales and active traders
                smart_wallets = {
                    addr: wallet for addr, wallet in wallets.items()
                    if wallet.is_whale(self.min_whale_volume, self.min_whale_trade_size)
                    or wallet.is_active_trader(self.min_trades_for_active)
                }
                
                logger.info(f"Found {len(smart_wallets)} smart money wallets for {token_address[:8]}")
                
                # Update known whales
                self.known_whales.update(smart_wallets)
                
                return smart_wallets
                
            except Exception as e:
                logger.error(f"Error fetching signatures: {e}")
                return {}
                
        except Exception as e:
            logger.error(f"Error in scan_token_transactions: {e}")
            return {}
    
    def _parse_transaction(self, tx, token_address: str) -> Dict[str, WalletActivity]:
        """
        Parse transaction to extract wallet activity
        Simplified version - production needs full swap instruction parsing
        """
        wallets = {}
        
        try:
            # Get transaction details
            transaction = tx.transaction
            meta = tx.meta
            
            if not meta:
                return wallets
            
            # Extract accounts involved
            if hasattr(transaction, 'message'):
                message = transaction.message
                
                # Get account keys
                account_keys = []
                if hasattr(message, 'account_keys'):
                    account_keys = [str(key) for key in message.account_keys]
                
                # Look at pre/post balances to estimate trade sizes
                pre_balances = meta.pre_balances if hasattr(meta, 'pre_balances') else []
                post_balances = meta.post_balances if hasattr(meta, 'post_balances') else []
                
                for i, account in enumerate(account_keys):
                    if i < len(pre_balances) and i < len(post_balances):
                        pre = pre_balances[i]
                        post = post_balances[i]
                        
                        # SOL balance change (in lamports)
                        balance_change = abs(post - pre) / 1e9
                        
                        # If significant change (> 0.1 SOL), consider it a trade
                        if balance_change > 0.1:
                            is_buy = post < pre  # Spent SOL = buying token
                            
                            activity = WalletActivity(address=account)
                            activity.add_trade(token_address, balance_change, is_buy)
                            wallets[account] = activity
            
        except Exception as e:
            logger.debug(f"Error parsing transaction: {e}")
        
        return wallets
    
    async def _rate_limit(self):
        """Enforce rate limiting between RPC calls"""
        import time as time_module
        
        current_time = time_module.time()
        time_since_last_call = current_time - self.last_rpc_call
        
        if time_since_last_call < self.min_rpc_delay:
            delay = self.min_rpc_delay - time_since_last_call
            await asyncio.sleep(delay)
        
        self.last_rpc_call = time_module.time()
    
    async def is_smart_money_in_token(self, token_address: str) -> bool:
        """
        Check if smart money wallets are trading this token
        Returns True if whales/active traders are present
        """
        try:
            # Scan recent transactions
            smart_wallets = await self.scan_token_transactions(token_address, limit=50)
            
            if not smart_wallets:
                logger.info(f"No smart money detected in {token_address[:8]}")
                return False
            
            # Check if any whale is present
            whale_count = sum(1 for w in smart_wallets.values() if w.is_whale())
            active_count = sum(1 for w in smart_wallets.values() if w.is_active_trader())
            
            logger.info(f"🐋 Found {whale_count} whales, {active_count} active traders in {token_address[:8]}")
            
            # Require at least 1 whale OR 3+ active traders
            return whale_count >= 1 or active_count >= 3
            
        except Exception as e:
            logger.error(f"Error checking smart money: {e}")
            return False
    
    def get_whale_summary(self) -> Dict:
        """Get summary of tracked whales"""
        total_whales = len(self.known_whales)
        total_volume = sum(w.total_volume_sol for w in self.known_whales.values())
        
        return {
            'total_whales': total_whales,
            'total_volume_sol': total_volume,
            'top_whales': sorted(
                self.known_whales.values(),
                key=lambda w: w.total_volume_sol,
                reverse=True
            )[:10]
        }


async def test_detector():
    """Test the smart money detector"""
    from config import Config
    
    config = Config()
    client = AsyncClient(config.RPC_ENDPOINT)
    
    detector = SmartMoneyDetector(client)
    
    # Test with a known token (USDC for testing)
    test_token = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    
    print(f"Scanning {test_token[:8]}... for smart money...")
    is_smart_money = await detector.is_smart_money_in_token(test_token)
    
    print(f"Smart money detected: {is_smart_money}")
    
    summary = detector.get_whale_summary()
    print(f"\nWhale Summary:")
    print(f"  Total Whales: {summary['total_whales']}")
    print(f"  Total Volume: {summary['total_volume_sol']:.2f} SOL")
    
    await client.close()


if __name__ == "__main__":
    asyncio.run(test_detector())
