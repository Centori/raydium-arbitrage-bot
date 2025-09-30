from typing import Dict, List, Optional, Set
from dataclasses import dataclass
import logging
import json
import time
import asyncio
from decimal import Decimal
from pathlib import Path

from solders.pubkey import Pubkey
from solders.transaction import Transaction
from api_client import BlockchainAPIClient
from migration_sniper import MigrationContract

logger = logging.getLogger("MigrationContractMonitor")

@dataclass
class MigrationStats:
    """Statistics for a migration contract"""
    total_migrations: int
    total_volume: Decimal
    unique_users: int
    avg_slippage: Decimal
    success_rate: float
    avg_gas_cost: Decimal
    last_migration_time: int

class MigrationContractMonitor:
    """Monitors Raydium migration contracts and tracks their activity"""
    
    def __init__(self, api_client: BlockchainAPIClient, history_file: str = "migration_history.json"):
        self.api_client = api_client
        self.history_file = Path(history_file)
        
        # Contract tracking
        self.known_contracts: Dict[str, MigrationContract] = {}
        self.completed_contracts: Set[str] = set()
        self.contract_stats: Dict[str, MigrationStats] = {}
        
        # Load historical data
        self._load_history()
        
    def _load_history(self):
        """Load historical migration data from file"""
        try:
            if self.history_file.exists():
                with open(self.history_file, 'r') as f:
                    data = json.load(f)
                    
                # Load known contracts
                for contract_data in data.get('contracts', []):
                    contract = MigrationContract(
                        address=contract_data['address'],
                        source_pool=contract_data['source_pool'],
                        target_pool=contract_data['target_pool'],
                        migration_deadline=contract_data['deadline'],
                        rewards_multiplier=float(contract_data['multiplier']),
                        is_active=contract_data['active']
                    )
                    self.known_contracts[contract.address] = contract
                    
                # Load completed contracts
                self.completed_contracts = set(data.get('completed_contracts', []))
                
                # Load statistics
                for stat_data in data.get('statistics', []):
                    stats = MigrationStats(
                        total_migrations=stat_data['total_migrations'],
                        total_volume=Decimal(str(stat_data['total_volume'])),
                        unique_users=stat_data['unique_users'],
                        avg_slippage=Decimal(str(stat_data['avg_slippage'])),
                        success_rate=float(stat_data['success_rate']),
                        avg_gas_cost=Decimal(str(stat_data['avg_gas_cost'])),
                        last_migration_time=stat_data['last_migration_time']
                    )
                    self.contract_stats[stat_data['contract']] = stats
                    
        except Exception as e:
            logger.error(f"Error loading migration history: {str(e)}")
            
    def _save_history(self):
        """Save current migration data to file"""
        try:
            data = {
                'contracts': [
                    {
                        'address': c.address,
                        'source_pool': c.source_pool,
                        'target_pool': c.target_pool,
                        'deadline': c.migration_deadline,
                        'multiplier': str(c.rewards_multiplier),
                        'active': c.is_active
                    }
                    for c in self.known_contracts.values()
                ],
                'completed_contracts': list(self.completed_contracts),
                'statistics': [
                    {
                        'contract': contract,
                        'total_migrations': stats.total_migrations,
                        'total_volume': str(stats.total_volume),
                        'unique_users': stats.unique_users,
                        'avg_slippage': str(stats.avg_slippage),
                        'success_rate': stats.success_rate,
                        'avg_gas_cost': str(stats.avg_gas_cost),
                        'last_migration_time': stats.last_migration_time
                    }
                    for contract, stats in self.contract_stats.items()
                ]
            }
            
            with open(self.history_file, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Error saving migration history: {str(e)}")
            
    async def start_monitoring(self, check_interval: int = 60):
        """Start monitoring for new migration contracts and updates"""
        logger.info("Starting migration contract monitoring...")
        
        while True:
            try:
                await self._check_for_new_contracts()
                await self._update_contract_states()
                await self._collect_statistics()
                self._save_history()
                
                await asyncio.sleep(check_interval)
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {str(e)}")
                await asyncio.sleep(check_interval)
                
    async def _check_for_new_contracts(self):
        """Check for new migration contract deployments"""
        try:
            # Get recent program logs
            signatures = await self.api_client.get_program_transactions(
                self.api_client.RAYDIUM_V4_PROGRAM_ID,
                limit=50
            )
            
            for sig in signatures:
                slot = sig.get('slot')
                signature = sig.get('signature')
                if not slot or not signature:
                    continue
                    
                tx = await self.api_client.get_transaction(signature)
                if not tx or not tx.get('meta', {}).get('logMessages'):
                    continue
                    
                # Look for migration initialization
                await self._process_transaction_logs(tx)
                
        except Exception as e:
            logger.error(f"Error checking for new contracts: {str(e)}")
            
    async def _process_transaction_logs(self, transaction):
        """Process transaction logs for migration contract events"""
        try:
            logs = transaction.get('meta', {}).get('logMessages')
            if not logs:
                return
                
            for log in logs:
                if "Initialize Migration" in log:
                    contract_address = self._parse_contract_address(log)
                    if (contract_address and 
                        contract_address not in self.known_contracts and
                        contract_address not in self.completed_contracts):
                        
                        contract = await self._analyze_contract(contract_address)
                        if contract:
                            self.known_contracts[contract_address] = contract
                            logger.info(f"Found new migration contract: {contract_address}")
                            
        except Exception as e:
            logger.error(f"Error processing transaction logs: {str(e)}")
            
    def _parse_contract_address(self, log: str) -> Optional[str]:
        """Parse contract address from program log"""
        try:
            # Example log: "Program XYZ: Initialize Migration ABC for pool DEF"
            parts = log.split()
            if len(parts) > 3:
                return parts[3]
            return None
        except Exception as e:
            logger.error(f"Error parsing contract address: {str(e)}")
            return None
            
    async def _analyze_contract(self, address: str) -> Optional[MigrationContract]:
        """Analyze a migration contract's parameters"""
        try:
            # Get contract account data
            account = await self.api_client.get_account_info(address)
            if not account or not account.get('data'):
                return None
                
            # Parse contract data
            import base64
            raw_data = base64.b64decode(account['data'][0])
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
            logger.error(f"Error analyzing contract: {str(e)}")
            return None
            
    async def _update_contract_states(self):
        """Update status of known contracts"""
        current_time = int(time.time())
        
        for address, contract in list(self.known_contracts.items()):
            try:
                # Check if contract has expired
                if current_time > contract.migration_deadline:
                    contract.is_active = False
                    self.completed_contracts.add(address)
                    del self.known_contracts[address]
                    continue
                    
                # Check if migration is complete
                if await self._is_migration_complete(contract):
                    contract.is_active = False
                    self.completed_contracts.add(address)
                    del self.known_contracts[address]
                    continue
                    
            except Exception as e:
                logger.error(f"Error updating contract {address}: {str(e)}")
                
    async def _is_migration_complete(self, contract: MigrationContract) -> bool:
        """Check if a migration has completed"""
        try:
            # Check V3 pool state
            v3_pool = await self.api_client.get_pool_info(contract.source_pool)
            if not v3_pool or v3_pool.total_liquidity < 100:  # Consider empty if < $100
                return True
                
            # Check if most liquidity has moved to V4
            v4_pool = await self.api_client.get_pool_info(contract.target_pool)
            if not v4_pool:
                return False
                
            # If V4 has significantly more liquidity, consider migration complete
            return v4_pool.total_liquidity > (v3_pool.total_liquidity * 10)
            
        except Exception as e:
            logger.error(f"Error checking migration completion: {str(e)}")
            return False
            
    async def _collect_statistics(self):
        """Collect and update statistics for active migrations"""
        for contract in self.known_contracts.values():
            try:
                # Get recent migrations for this contract
                migrations = await self._get_contract_migrations(contract, limit=100)
                
                if not migrations:
                    continue
                    
                # Calculate statistics
                total_volume = sum(m.amount_in for m in migrations)
                unique_users = len(set(m.user for m in migrations))
                success_count = len([m for m in migrations if m.success])
                success_rate = success_count / len(migrations)
                
                avg_slippage = (
                    sum(m.slippage for m in migrations if m.success) /
                    success_count if success_count > 0 else Decimal(0)
                )
                
                avg_gas = (
                    sum(m.gas_cost for m in migrations if m.success) /
                    success_count if success_count > 0 else Decimal(0)
                )
                
                last_time = max(m.timestamp for m in migrations)
                
                # Update statistics
                self.contract_stats[contract.address] = MigrationStats(
                    total_migrations=len(migrations),
                    total_volume=total_volume,
                    unique_users=unique_users,
                    avg_slippage=avg_slippage,
                    success_rate=success_rate,
                    avg_gas_cost=avg_gas,
                    last_migration_time=last_time
                )
                
            except Exception as e:
                logger.error(f"Error collecting statistics for {contract.address}: {str(e)}")
                
    async def _get_contract_migrations(self, contract: MigrationContract, limit: int = 100):
        """Get recent migrations for a contract"""
        migrations = []
        try:
            # Get recent transactions involving the contract
            signatures = await self.api_client.get_signatures_for_address(
                contract.address,
                limit=limit
            )
            
            for sig in signatures:
                tx = await self.api_client.get_transaction(sig.signature)
                if not tx or not tx.meta:
                    continue
                    
                # Parse migration details
                migration = self._parse_migration_from_tx(tx)
                if migration:
                    migrations.append(migration)
                    
        except Exception as e:
            logger.error(f"Error fetching contract migrations: {str(e)}")
            
        return migrations
        
    def _parse_migration_from_tx(self, transaction) -> Optional[dict]:
        """Parse migration details from a transaction"""
        try:
            if not transaction.meta or transaction.meta.err:
                return None
                
            # Extract relevant information
            # This would need proper implementation based on actual transaction format
            return {
                'timestamp': transaction.block_time,
                'user': str(transaction.message.recent_blockhash),  # placeholder
                'amount_in': Decimal(0),  # placeholder
                'success': not transaction.meta.err,
                'slippage': Decimal(0),  # placeholder
                'gas_cost': Decimal(str(transaction.meta.fee))
            }
            
        except Exception as e:
            logger.error(f"Error parsing migration transaction: {str(e)}")
            return None