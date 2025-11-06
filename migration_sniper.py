import asyncio
import logging
import json
import time
import aiohttp
from typing import Dict, List, Optional, Set
from decimal import Decimal
from dataclasses import dataclass
from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction
from solana.rpc.async_api import AsyncClient

from config import Config
from raydium_pools import RaydiumPoolFetcher
from pool_analyzer import PoolAnalyzer
from risk_analyzer import RiskAnalyzer
from api_client import BlockchainAPIClient, PoolData
from raydium_pair import RaydiumPair
from security_validator import SecurityValidator
from gmgn_tracker import GMGNTracker

logger = logging.getLogger("migration_sniper")

@dataclass
class MigrationContract:
    address: str
    source_pool: str
    target_pool: str
    migration_deadline: int
    rewards_multiplier: float
    is_active: bool

@dataclass
class PriceImpactAnalysis:
    base_impact: float
    quote_impact: float
    combined_impact: float
    slippage_estimate: float
    confidence_score: float  # 0-1 score based on analysis reliability

@dataclass
class MigrationOpportunity:
    old_pool_id: str
    new_pool_id: str
    base_token: str
    quote_token: str
    price_ratio: float  # New pool price / Old pool price
    liquidity_ratio: float  # New pool liquidity / Old pool liquidity
    estimated_profit: float
    risk_score: float
    price_impact: PriceImpactAnalysis
    migration_contract: Optional[MigrationContract]

class MigrationSniper:
    """Sniper for Raydium pool migrations (V3 to V4)"""
    
    # Raydium Program IDs
    RAYDIUM_V3_PROGRAM_ID = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
    RAYDIUM_V4_PROGRAM_ID = "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK"
    
    def __init__(self, config: Config, pool_fetcher: RaydiumPoolFetcher, pool_analyzer: PoolAnalyzer, executor=None):
        self.config = config
        self.pool_fetcher = pool_fetcher
        self.pool_analyzer = pool_analyzer
        self.risk_analyzer = RiskAnalyzer(config)
        self.api_client = BlockchainAPIClient(config)
        self.security_validator = SecurityValidator(config, self.api_client)
        self.gmgn_tracker = GMGNTracker(config)
        self.executor = executor
        
        # Known V3 pools and their state
        self.v3_pools: Dict[str, PoolData] = {}
        self.migrated_pools: Set[str] = set()
        
        # Migration parameters
        self.min_price_difference = 0.005  # 0.5% minimum price difference
        self.min_liquidity = 50_000  # $50k minimum liquidity
        self.max_risk_score = 40  # Maximum risk score (0-100)
        
        # Initialize RPC client
        self.rpc_client = AsyncClient(config.RPC_ENDPOINT)
        
        # Track migration contract deployments
        self.known_migration_contracts: Set[str] = set()
        
        # Load previous migration data
        self._load_migration_history()
        
    def _load_migration_history(self):
        """Load previously seen migrations"""
        try:
            with open('data/migration_history.json', 'r') as f:
                data = json.load(f)
                self.migrated_pools = set(data.get('migrated_pools', []))
                self.known_migration_contracts = set(data.get('migration_contracts', []))
        except FileNotFoundError:
            logger.info("No migration history found, starting fresh")
        except Exception as e:
            logger.error(f"Error loading migration history: {e}")

    def _save_migration_history(self):
        """Save migration data to disk"""
        try:
            with open('data/migration_history.json', 'w') as f:
                json.dump({
                    'migrated_pools': list(self.migrated_pools),
                    'migration_contracts': list(self.known_migration_contracts)
                }, f)
        except Exception as e:
            logger.error(f"Error saving migration history: {e}")

    async def start_monitoring(self):
        """Main loop to monitor for migration opportunities"""
        logger.info("Starting migration sniper...")
        
        while True:
            try:
                # Fetch current V3 and V4 pools
                v3_pools = await self._fetch_v3_pools()
                v4_pools = await self._fetch_v4_pools()
                
                # Look for migration opportunities
                opportunities = await self._find_migration_opportunities(v3_pools, v4_pools)
                
                # Execute profitable opportunities
                for opp in opportunities:
                    if await self._validate_opportunity(opp):
                        await self._execute_migration(opp)
                
                # Check for new migration contract deployments
                await self._monitor_migration_contracts()
                
                # Sleep to avoid rate limits
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Error in migration monitoring: {e}")
                await asyncio.sleep(5)

    async def _fetch_v3_pools(self) -> List[PoolData]:
        """Fetch all V3 pools"""
        try:
            # Use existing pool fetcher but filter for V3
            all_pools = await self.pool_fetcher.fetch_all_pools()
            v3_pools = [p for p in all_pools if str(p.version) == "3"]
            logger.info(f"Found {len(v3_pools)} V3 pools")
            return v3_pools
        except Exception as e:
            logger.error(f"Error fetching V3 pools: {e}")
            return []

    async def _fetch_v4_pools(self) -> List[PoolData]:
        """Fetch all V4 pools"""
        try:
            # Use existing pool fetcher but filter for V4
            all_pools = await self.pool_fetcher.fetch_all_pools()
            v4_pools = [p for p in all_pools if str(p.version) == "4"]
            logger.info(f"Found {len(v4_pools)} V4 pools")
            return v4_pools
        except Exception as e:
            logger.error(f"Error fetching V4 pools: {e}")
            return []

    async def _analyze_price_impact(self, v3_pool: PoolData, v4_pool: PoolData, position_size: float) -> PriceImpactAnalysis:
        """Perform detailed price impact analysis"""
        try:
            # Create RaydiumPair instances for both pools
            v3_pair = RaydiumPair(
                market_address=v3_pool.id,
                tokens=[v3_pool.base_token.address, v3_pool.quote_token.address]
            )
            v4_pair = RaydiumPair(
                market_address=v4_pool.id,
                tokens=[v4_pool.base_token.address, v4_pool.quote_token.address]
            )
            
            # Set current reserves
            v3_pair.set_reserves(Decimal(v3_pool.base_amount), Decimal(v3_pool.quote_amount))
            v4_pair.set_reserves(Decimal(v4_pool.base_amount), Decimal(v4_pool.quote_amount))
            
            # Calculate impacts for both tokens
            base_impact_v3 = v3_pair.get_price_impact(v3_pool.base_token.address, Decimal(str(position_size)))
            quote_impact_v3 = v3_pair.get_price_impact(v3_pool.quote_token.address, Decimal(str(position_size)))
            base_impact_v4 = v4_pair.get_price_impact(v4_pool.base_token.address, Decimal(str(position_size)))
            quote_impact_v4 = v4_pair.get_price_impact(v4_pool.quote_token.address, Decimal(str(position_size)))
            
            # Combined impact analysis
            base_impact = float(base_impact_v4 - base_impact_v3)
            quote_impact = float(quote_impact_v4 - quote_impact_v3)
            combined_impact = (base_impact + quote_impact) / 2
            
            # Estimate slippage based on impacts and liquidity depth
            v3_liquidity = float(v3_pool.quote_amount)
            v4_liquidity = float(v4_pool.quote_amount)
            liquidity_ratio = min(v4_liquidity / v3_liquidity, 1) if v3_liquidity > 0 else 0
            slippage_estimate = combined_impact * (1 + (1 - liquidity_ratio))
            
            # Calculate confidence score
            confidence_factors = [
                1 if v3_liquidity > self.min_liquidity else v3_liquidity / self.min_liquidity,
                1 if v4_liquidity > self.min_liquidity else v4_liquidity / self.min_liquidity,
                1 - (combined_impact / 0.1),  # Lower impact = higher confidence
                liquidity_ratio
            ]
            confidence_score = sum(confidence_factors) / len(confidence_factors)
            
            return PriceImpactAnalysis(
                base_impact=base_impact,
                quote_impact=quote_impact,
                combined_impact=combined_impact,
                slippage_estimate=slippage_estimate,
                confidence_score=max(0, min(1, confidence_score))
            )
            
        except Exception as e:
            logger.error(f"Error analyzing price impact: {e}")
            return PriceImpactAnalysis(0, 0, 0, 0, 0)
    
    async def _find_migration_opportunities(
        self, v3_pools: List[PoolData], v4_pools: List[PoolData]
    ) -> List[MigrationOpportunity]:
        """Find profitable migration opportunities"""
        opportunities = []
        
        for v3_pool in v3_pools:
            try:
                # Skip already migrated pools
                if v3_pool.id in self.migrated_pools:
                    continue
                    
                # Find matching V4 pool with same tokens
                matching_v4 = next(
                    (p for p in v4_pools if (
                        p.base_token.address == v3_pool.base_token.address and
                        p.quote_token.address == v3_pool.quote_token.address
                    )), None
                )
                
                if matching_v4:
                    # Calculate price ratio
                    v3_price = float(v3_pool.quote_amount) / float(v3_pool.base_amount)
                    v4_price = float(matching_v4.quote_amount) / float(matching_v4.base_amount)
                    price_ratio = v4_price / v3_price if v3_price > 0 else 0
                    
                    # Calculate liquidity ratio
                    v3_liquidity = float(v3_pool.quote_amount) * 2  # Simplified USD estimate
                    v4_liquidity = float(matching_v4.quote_amount) * 2
                    liquidity_ratio = v4_liquidity / v3_liquidity if v3_liquidity > 0 else 0
                    
                    # Skip if liquidity is too low
                    if v4_liquidity < self.min_liquidity:
                        continue
                    
                    # Calculate potential profit
                    price_difference = abs(1 - price_ratio)
                    if price_difference > self.min_price_difference:
                        # Get risk score
                        risk_score = self.risk_analyzer.analyze_pool_risk(matching_v4)
                        if risk_score > self.max_risk_score:
                            continue
                            
                        # Calculate estimated profit
                        position_size = min(v3_liquidity, v4_liquidity) * 0.1  # 10% of smaller pool
                        
                        # Analyze price impact
                        price_impact = await self._analyze_price_impact(v3_pool, matching_v4, position_size)
                        
                        # Adjust profit estimate based on price impact and confidence
                        adjusted_size = position_size * (1 - price_impact.slippage_estimate)
                        estimated_profit = (
                            adjusted_size * 
                            price_difference * 
                            0.95 * # Base efficiency
                            price_impact.confidence_score  # Confidence adjustment
                        )
                        
                        # Get associated migration contract if any
                        migration_contract = next(
                            (c for c in self.known_migration_contracts 
                             if c.source_pool == v3_pool.id and c.target_pool == matching_v4.id),
                            None
                        )
                        
                        opportunities.append(MigrationOpportunity(
                            old_pool_id=v3_pool.id,
                            new_pool_id=matching_v4.id,
                            base_token=v3_pool.base_token.address,
                            quote_token=v3_pool.quote_token.address,
                            price_ratio=price_ratio,
                            liquidity_ratio=liquidity_ratio,
                            estimated_profit=estimated_profit,
                            risk_score=risk_score,
                            price_impact=price_impact,
                            migration_contract=migration_contract
                        ))
                        
            except Exception as e:
                logger.error(f"Error analyzing pool {v3_pool.id}: {e}")
                continue
        
        # Sort by estimated profit
        opportunities.sort(key=lambda x: x.estimated_profit, reverse=True)
        return opportunities

    async def _validate_opportunity(self, opp: MigrationOpportunity) -> bool:
        """Additional validation of migration opportunity"""
        try:
            # Check if pools still exist
            v3_pool = await self.pool_fetcher.get_pool_data(opp.old_pool_id)
            v4_pool = await self.pool_fetcher.get_pool_data(opp.new_pool_id)
            if not v3_pool or not v4_pool:
                return False
            
            # RUN SECURITY CHECKS on base token
            base_token = opp.base_token
            if not self.security_validator.is_blacklisted(base_token):
                security_report = await self.security_validator.validate_token(base_token)
                
                if not security_report.tradeable:
                    logger.warning(f"Token {base_token} FAILED security checks: {security_report.warnings}")
                    self.security_validator.blacklist_token(base_token, "Failed security validation")
                    return False
                
                if security_report.overall_risk_score > 50:
                    logger.warning(f"Token {base_token} has high risk score: {security_report.overall_risk_score}/100")
                    return False
            else:
                logger.info(f"Skipping blacklisted token: {base_token}")
                return False
            
            # CHECK SMART MONEY via GMGN.ai
            smart_money_check = await self.gmgn_tracker.monitor_smart_money_for_token(base_token)
            if not smart_money_check:
                logger.info(f"Token {base_token} has no smart money interest (GMGN)")
                # Don't reject completely, but lower confidence
            else:
                logger.info(f"Token {base_token} has smart money backing (GMGN)")
            
            # Verify price difference still exists
            current_v3_price = float(v3_pool.quote_amount) / float(v3_pool.base_amount)
            current_v4_price = float(v4_pool.quote_amount) / float(v4_pool.base_amount)
            current_ratio = current_v4_price / current_v3_price
            
            price_change = abs(current_ratio - opp.price_ratio)
            if price_change > 0.01:  # Price has moved more than 1%
                return False
            
            # Check migration contract is active
            migration_contract = await self._get_migration_contract(opp.old_pool_id)
            if not migration_contract:
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating opportunity: {e}")
            return False

    async def _get_migration_contract(self, pool_id: str) -> Optional[str]:
        """Find migration contract for a V3 pool"""
        try:
            # This would search for the migration contract by analyzing program logs
            # and recent transactions. For now, we just return None as placeholder
            return None
        except Exception as e:
            logger.error(f"Error finding migration contract: {e}")
            return None

    async def _monitor_migration_contracts(self):
        """Monitor for new migration contract deployments"""
        try:
            # Get recent program transactions
            signatures = await self.api_client.get_program_transactions(self.RAYDIUM_V4_PROGRAM_ID, limit=50)
            for sig_info in signatures:
                if not sig_info.get('slot') or not sig_info.get('signature'):
                    continue
                    
                # Get transaction details via JSON-RPC
                tx_payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getTransaction",
                    "params": [sig_info['signature'], {"maxSupportedTransactionVersion": 0}]
                }
                
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.post(self.config.RPC_ENDPOINT, json=tx_payload) as resp:
                            tx_data = await resp.json()
                            tx = tx_data.get("result")
                except Exception as e:
                    logger.error(f"Error fetching tx details: {e}")
                    continue
                
                if not tx or not tx.get('meta', {}).get('logMessages'):
                    continue
                    
                # Look for migration contract creation instruction
                for log in tx['meta']['logMessages']:
                    if "Initialize Migration" in log:
                        # Parse migration parameters
                        contract_address = self._parse_migration_contract_address(log)
                        if contract_address and contract_address not in self.known_migration_contracts:
                            contract = await self._analyze_migration_contract(contract_address)
                            if contract:
                                self.known_migration_contracts.add(contract_address)
                                self._save_migration_history()
                                logger.info(f"Found new migration contract: {contract_address}")
                                
        except Exception as e:
            logger.error(f"Error monitoring migration contracts: {e}")
            
    def _parse_migration_contract_address(self, log: str) -> Optional[str]:
        """Parse migration contract address from program log"""
        try:
            # Example log: "Program XYZ: Initialize Migration ABC for pool DEF"
            parts = log.split()
            if len(parts) > 3:
                return parts[3]  # Extract contract address
            return None
        except Exception as e:
            logger.error(f"Error parsing contract address: {e}")
            return None
            
    async def _analyze_migration_contract(self, address: str) -> Optional[MigrationContract]:
        """Analyze a migration contract's parameters"""
        try:
            # Fetch contract account data via JSON-RPC
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getAccountInfo",
                "params": [address, {"encoding": "base64"}]
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.config.RPC_ENDPOINT, json=payload) as resp:
                    data = await resp.json()
                    if not data.get('result') or not data['result'].get('data'):
                        return None
                    
                    import base64
                    raw_data = base64.b64decode(data['result']['data'][0])
                    
                    # This would need to match Raydium's actual data layout
                    source_pool = raw_data[0:32].hex()
                    target_pool = raw_data[32:64].hex()
                    deadline = int.from_bytes(raw_data[64:72], 'little')
                    multiplier = int.from_bytes(raw_data[72:80], 'little') / 10000
            
            return MigrationContract(
                address=address,
                source_pool=source_pool,
                target_pool=target_pool,
                migration_deadline=deadline,
                rewards_multiplier=multiplier,
                is_active=True
            )
            
        except Exception as e:
            logger.error(f"Error analyzing migration contract: {e}")
            return None

    async def _execute_migration(self, opp: MigrationOpportunity):
        """Execute a migration opportunity"""
        try:
            # Verify opportunity is still valid
            if not await self._validate_opportunity(opp):
                return
            
            # SEND PRE-TRADE NOTIFICATION
            await self._send_trade_notification(opp)
            
            logger.info(f"Executing migration for pool {opp.old_pool_id} -> {opp.new_pool_id}")
            logger.info(f"Expected profit: ${opp.estimated_profit:.2f}")

            # Prepare a minimal migration contract placeholder if missing
            contract = opp.migration_contract or MigrationContract(
                address="mock_contract",
                source_pool=opp.old_pool_id,
                target_pool=opp.new_pool_id,
                migration_deadline=int(time.time()) + 3600,
                rewards_multiplier=1.0,
                is_active=True,
            )

            # Use configured trade amount
            from decimal import Decimal
            trade_amount = Decimal(str(self.config.TRADE_AMOUNT_SOL))

            if not self.executor:
                logger.warning("No executor configured; skipping on-chain execution. Trading logic present but disabled.")
            else:
                try:
                    result = await self.executor.execute_migration(
                        migration_info=contract,
                        amount=trade_amount,
                        slippage_tolerance=Decimal(str(self.config.SLIPPAGE_BPS / 10_000))
                    )
                    if result.success:
                        logger.info(f"Migration executed: {result.tx_signature}")
                    else:
                        logger.error(f"Migration failed: {result.error_message}")
                except Exception as e:
                    logger.error(f"Executor error: {e}")
            
            # Mark pool as migrated
            self.migrated_pools.add(opp.old_pool_id)
            self._save_migration_history()
            
        except Exception as e:
            logger.error(f"Error executing migration: {e}")

    async def _send_trade_notification(self, opp: MigrationOpportunity):
        """Send notification before executing trade"""
        try:
            # Calculate estimated ROI
            position_value = self.config.TRADE_AMOUNT_SOL * opp.price_ratio
            estimated_roi = (opp.estimated_profit / (self.config.TRADE_AMOUNT_SOL * opp.price_ratio)) * 100 if position_value > 0 else 0
            
            # Get GMGN signal if available
            gmgn_signal = self.gmgn_tracker.get_signal_for_token(opp.base_token)
            
            notification = f"""
🎯 MIGRATION SNIPE TARGET DETECTED

💰 Token: {opp.base_token[:8]}...
📊 Old Pool: {opp.old_pool_id[:8]}...
📈 New Pool: {opp.new_pool_id[:8]}...

💵 Trade Amount: {self.config.TRADE_AMOUNT_SOL} SOL
📈 Estimated Profit: ${opp.estimated_profit:.2f}
📊 Estimated ROI: {estimated_roi:.1f}%
⚠️ Risk Score: {opp.risk_score}/100

💎 Liquidity Ratio: {opp.liquidity_ratio:.2f}x
📉 Price Impact: {opp.price_impact.combined_impact*100:.2f}%
✅ Confidence: {opp.price_impact.confidence_score*100:.0f}%
"""
            
            if gmgn_signal:
                notification += f"""
🧠 GMGN Smart Money:
   Action: {gmgn_signal['action'].upper()}
   Confidence: {gmgn_signal['confidence']}%
   Holders: {gmgn_signal['smart_money_holders']}
   24h Flow: ${gmgn_signal['net_flow_24h']:,.0f}
"""
            
            notification += "\n⏰ Executing in 5 seconds..."
            
            logger.critical(notification)
            
            # Wait 5 seconds for review (optional - can be disabled)
            # await asyncio.sleep(5)
            
        except Exception as e:
            logger.error(f"Error sending trade notification: {e}")
    
    def get_pending_migrations(self) -> List[MigrationOpportunity]:
        """Get list of currently pending migration opportunities"""
        try:
            # Get current pools
            v3_pools = [p for p in self.pool_fetcher.fetch_all_pools() if str(p.version) == "3"]
            v4_pools = [p for p in self.pool_fetcher.fetch_all_pools() if str(p.version) == "4"]
            
            # Find opportunities
            loop = asyncio.get_event_loop()
            opportunities = loop.run_until_complete(self._find_migration_opportunities(v3_pools, v4_pools))
            return opportunities
            
        except Exception as e:
            logger.error(f"Error getting pending migrations: {e}")
            return []
