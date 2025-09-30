import time
import json
import logging
import base64
import asyncio
from typing import Dict, List, Optional, Any, Union, Tuple
from dataclasses import dataclass

from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction
from solders.signature import Signature

from config import Config, BACKRUN_STRATEGY
from api_client import BlockchainAPIClient, ArbitrageOpportunity, TokenInfo
from jito_executor import JitoExecutor
from wallet import WalletManager
from risk_analyzer import RiskAnalyzer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/backrun.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("backrun_strategy")

@dataclass
class TransactionInfo:
    signature: str
    transaction_data: Dict[str, Any]
    dex: str
    price_impact_pct: float
    tokens_involved: List[str]
    slot: int

@dataclass
class BackrunOpportunity:
    target_signature: str
    input_mint: str
    output_mint: str
    amount_in: int
    expected_profit: float
    price_impact_pct: float
    transaction_data: Dict[str, Any]
    dex: str

@dataclass
class TradeConfig:
    min_trade_bp: int
    max_trade_bp: int

class BackrunStrategy:
    """Strategy for backrunning profitable DEX transactions"""
    
    def __init__(self, config: Config, api_client: BlockchainAPIClient, wallet_manager: WalletManager):
        self.config = config
        self.api_client = api_client
        self.wallet_manager = wallet_manager
        self.jito_executor = JitoExecutor(config, wallet_manager, api_client)
        self.risk_analyzer = RiskAnalyzer(config)
        
        # Load configuration from constants
        self.dexes_to_monitor = BACKRUN_STRATEGY.get("DEXES_TO_MONITOR", [])
        self.min_price_impact = BACKRUN_STRATEGY.get("MIN_PRICE_IMPACT_PCT", 0.1)
        self.base_mints_config = BACKRUN_STRATEGY.get("BASE_MINTS", [])
        self.enable_backrun = BACKRUN_STRATEGY.get("ENABLE_BACKRUN_STRATEGY", True)
        self.slot_memo = BACKRUN_STRATEGY.get("SLOT_MEMO", True)
        
        # Keep track of processed transactions
        self.processed_txs = set()
        self.running = False
        
        # SOL token address (wrapped SOL)
        self.SOL_MINT = "So11111111111111111111111111111111111111112"
        
        # DEX program IDs
        self.dex_program_ids = {
            "Raydium": "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",
            "RaydiumCLMM": "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK",
            "Whirlpool": "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc",
            "Meteora": "M2mx93ekt1fmXSVkTrUL9xVFHkmME8HTUi5Cyc5aF7K",
            "MeteoraDLMM": "dLMBYt7aBSyUbxHcy5crJKMrWDSPRKh1cAQHXg7KUT7"
        }
    
    async def start_monitoring(self, yellowstone_url: str, yellowstone_token: str):
        """Start monitoring transactions for backrunning opportunities"""
        if not self.enable_backrun:
            logger.info("Backrun strategy is disabled in config")
            return
            
        self.running = True
        logger.info(f"Starting backrun strategy monitoring for DEXes: {', '.join(self.dexes_to_monitor)}")
        
        try:
            # Try to initialize Jito connection for bundle submission
            jito_enabled = False
            if self.jito_executor:
                try:
                    init_success = await self.jito_executor.initialize()
                    if init_success:
                        jito_enabled = True
                        logger.info("Successfully initialized Jito connection for bundle submission")
                    else:
                        logger.warning("Failed to initialize Jito connection, running in simulation mode")
                except Exception as e:
                    logger.warning(f"Error initializing Jito: {e}, running in simulation mode")
            
            # Start monitoring recent blocks for opportunities
            latest_block = None
            while self.running:
                try:
                    # Get latest block height from RPC
                    slot_info = await self.wallet_manager.client.get_slot()
                    current_block = slot_info.value
                    
                    if latest_block is None:
                        latest_block = current_block - 1  # Start with previous block
                    
                    # Process any new blocks
                    while latest_block < current_block:
                        latest_block += 1
                        logger.info(f"Processing block {latest_block}")
                        
                        # Fetch and process block transactions
                        block_data = await self._fetch_block_transactions(latest_block)
                        if block_data:
                            for tx_data in block_data:
                                opportunity = await self._process_transaction(tx_data)
                                if opportunity:
                                    if jito_enabled:
                                        # Submit to Jito if connection available
                                        await self._execute_backrun(opportunity)
                                    else:
                                        # Otherwise just log the opportunity
                                        logger.info(f"[Simulation] Found opportunity in tx {tx_data.get('signature', 'unknown')}:")
                                        logger.info(f"  - Expected profit: ${opportunity.expected_profit:.4f}")
                                        logger.info(f"  - Price impact: {opportunity.price_impact_pct:.2f}%")
                                        logger.info(f"  - Token path: {' → '.join(opportunity.token_path)}")
                    
                    # Add a small delay to avoid excessive RPC calls
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    logger.error(f"Error processing blocks: {str(e)}")
                    await asyncio.sleep(1)  # Wait before retrying
                
        except Exception as e:
            logger.error(f"Error in backrun strategy monitoring: {str(e)}")
            self.running = False
    
    async def _fetch_block_transactions(self, block_height: int) -> List[Dict[str, Any]]:
        """Fetch and filter transactions from a specific block"""
        try:
            # Use RPC client to get block information
            block_info = await self.wallet_manager.client.get_block(
                block_height,
                max_supported_transaction_version=0,
                encoding="json"
            )
            
            if not block_info or not block_info.value:
                return []
                
            transactions = []
            for tx in block_info.value.transactions:
                # Check if transaction involves any of our monitored DEX programs
                if self._is_relevant_transaction(tx):
                    transactions.append(tx)
            
            return transactions
            
        except Exception as e:
            logger.error(f"Error fetching block transactions: {str(e)}")
            return []
    
    def _is_relevant_transaction(self, transaction) -> bool:
        """Check if a transaction is relevant for backrunning"""
        try:
            # Handle Solders EncodedTransactionWithStatusMeta
            if hasattr(transaction, 'transaction'):
                # Extract transaction message
                tx_message = transaction.transaction.message
                
                # Get account keys and instructions
                account_keys = [str(key) for key in tx_message.account_keys]
                instructions = tx_message.instructions
                
                # Check each instruction's program ID
                for ix in instructions:
                    program_idx = ix.program_id_index
                    if program_idx >= len(account_keys):
                        continue
                        
                    program_id = account_keys[program_idx]
                    if program_id in self.dex_program_ids.values():
                        return True
                        
            # Handle dictionary format (for simulation/testing)
            elif isinstance(transaction, dict):
                if "transaction" not in transaction or "message" not in transaction["transaction"]:
                    return False
                    
                message = transaction["transaction"]["message"]
                account_keys = message.get("accountKeys", [])
                instructions = message.get("instructions", [])
                
                # Check if any instructions involve our monitored DEX programs
                for instruction in instructions:
                    program_idx = instruction.get("programId")
                    if program_idx is None or program_idx >= len(account_keys):
                        continue
                        
                    program_id = account_keys[program_idx]
                    if program_id in self.dex_program_ids.values():
                        return True
            
            return False
            
        except Exception as e:
            logger.debug(f"Error checking transaction relevance: {str(e)}")
            return False
    
    def stop_monitoring(self):
        """Stop the transaction monitoring"""
        logger.info("Stopping backrun transaction monitoring")
        self.running = False
    
    async def _process_transaction(self, tx_data: Dict[str, Any]):
        """Process incoming transaction to find backrun opportunities"""
        try:
            # Extract transaction signature
            signature = tx_data.get("signature")
            if not signature or signature in self.processed_txs:
                return
                
            self.processed_txs.add(signature)
            # Keep processed transactions set manageable
            if len(self.processed_txs) > 10000:
                self.processed_txs = set(list(self.processed_txs)[-5000:])
            
            # Extract transaction details
            if "transaction" not in tx_data or "meta" not in tx_data:
                return
                
            # Identify if this is a DEX transaction on one of our monitored DEXes
            dex_info = self._identify_dex_transaction(tx_data)
            if not dex_info:
                return
                
            dex_name, tokens_involved = dex_info
            
            # Calculate price impact
            price_impact = self._calculate_price_impact(tx_data, tokens_involved)
            if price_impact < self.min_price_impact:
                logger.debug(f"Transaction {signature} has price impact {price_impact}% below threshold")
                return
                
            # Create transaction info object
            tx_info = TransactionInfo(
                signature=signature,
                transaction_data=tx_data,
                dex=dex_name,
                price_impact_pct=price_impact,
                tokens_involved=tokens_involved,
                slot=tx_data.get("slot", 0)
            )
            
            logger.info(f"Potential backrun opportunity: {signature} on {dex_name} with {price_impact:.2f}% impact")
            
            # Find and execute backrun opportunities
            await self._find_and_execute_backrun(tx_info)
            
        except Exception as e:
            logger.error(f"Error processing transaction for backrun: {str(e)}")
    
    def _identify_dex_transaction(self, tx_data: Dict[str, Any]) -> Optional[tuple]:
        """
        Identify if transaction is related to one of our monitored DEXes
        Returns tuple of (dex_name, tokens_involved) if it is, None otherwise
        """
        try:
            # Extract program IDs from transaction
            transaction = tx_data.get("transaction", {})
            message = transaction.get("message", {})
            account_keys = message.get("accountKeys", [])
            instructions = message.get("instructions", [])
            
            # Check if any instructions involve DEX programs
            for instruction in instructions:
                program_idx = instruction.get("programIdIndex")
                if program_idx is None or program_idx >= len(account_keys):
                    continue
                    
                program_id = account_keys[program_idx]
                
                # Match program with DEX
                for dex_name, dex_program_id in self.dex_program_ids.items():
                    if program_id == dex_program_id and dex_name in self.dexes_to_monitor:
                        # Parse token accounts from instruction accounts
                        tokens_involved = self._extract_token_accounts_from_instruction(instruction, account_keys)
                        return (dex_name, tokens_involved)
            
            return None
            
        except Exception as e:
            logger.error(f"Error identifying DEX transaction: {str(e)}")
            return None
    
    def _extract_token_accounts_from_instruction(self, instruction: Dict[str, Any], account_keys: List[str]) -> List[str]:
        """Extract token accounts from instruction accounts"""
        accounts_idx = instruction.get("accounts", [])
        token_accounts = [account_keys[i] for i in accounts_idx if i < len(account_keys)]
        
        # In a production implementation, you would identify which accounts are actually token mints
        # For now, we'll use a subset of accounts that might be token accounts
        return list(set(token_accounts))
    
    def _calculate_price_impact(self, tx_data: Dict[str, Any], token_accounts: List[str]) -> float:
        """
        Calculate the price impact of a transaction
        Returns price impact as percentage (e.g., 1.5 means 1.5%)
        """
        try:
            # Extract pre and post token balances
            pre_balances = tx_data.get("meta", {}).get("preTokenBalances", [])
            post_balances = tx_data.get("meta", {}).get("postTokenBalances", [])
            
            if not pre_balances or not post_balances:
                return 0.0
                
            # Group balances by mint
            pre_by_mint = {bal.get("mint"): bal.get("uiTokenAmount", {}).get("uiAmount", 0) 
                          for bal in pre_balances if "mint" in bal}
            post_by_mint = {bal.get("mint"): bal.get("uiTokenAmount", {}).get("uiAmount", 0) 
                           for bal in post_balances if "mint" in bal}
            
            # Calculate changes for each mint
            impacts = []
            for mint, pre_amount in pre_by_mint.items():
                post_amount = post_by_mint.get(mint, pre_amount)
                if pre_amount > 0:
                    # Calculate percentage change
                    impact = abs((post_amount - pre_amount) / pre_amount) * 100
                    impacts.append(impact)
            
            # Return maximum impact if found, otherwise 0
            return max(impacts) if impacts else 0.0
            
        except Exception as e:
            logger.error(f"Error calculating price impact: {str(e)}")
            return 0.0
    
    async def _find_and_execute_backrun(self, tx_info: TransactionInfo):
        """Find and execute profitable backrun opportunities"""
        try:
            opportunities = await self._analyze_backrun_opportunities(tx_info)
            
            if not opportunities:
                logger.debug(f"No profitable backrun opportunities found for {tx_info.signature}")
                return
                
            logger.info(f"Found {len(opportunities)} potential backrun opportunities")
            
            # Sort opportunities by expected profit
            opportunities.sort(key=lambda x: x.expected_profit, reverse=True)
            
            # Take the most profitable opportunity
            best_opportunity = opportunities[0]
            
            # Execute the backrun
            await self._execute_backrun(best_opportunity)
            
        except Exception as e:
            logger.error(f"Error finding backrun opportunities: {str(e)}")
    
    async def _analyze_backrun_opportunities(self, tx_info: TransactionInfo) -> List[BackrunOpportunity]:
        """Analyze potential backrun opportunities for a transaction"""
        opportunities = []
        
        try:
            # For each base mint configuration
            for base_config in self.base_mints_config:
                base_mint = base_config.get("MINT")
                min_profit = base_config.get("MIN_SIMULATED_PROFIT", 200000)
                min_trade = base_config.get("MIN_TRADE_SIZE", 500_000_000)
                max_trade = base_config.get("MAX_TRADE_SIZE", 150_000_000_000)
                
                # Get trade configs
                trade_configs = base_config.get("TRADE_CONFIGS", [])
                if not trade_configs:
                    trade_configs = [{"MIN_TRADE_BP": 2000, "MAX_TRADE_BP": 2000}]
                
                # For each token involved in the transaction
                for token_mint in tx_info.tokens_involved:
                    # Skip if it's the same as base mint
                    if token_mint == base_mint:
                        continue
                        
                    # For each trade config
                    for trade_config in trade_configs:
                        min_bp = trade_config.get("MIN_TRADE_BP", 2000)
                        max_bp = trade_config.get("MAX_TRADE_BP", 2000)
                        
                        # Calculate amounts to trade
                        for bp in range(min_bp, max_bp + 100, 100):
                            amount_in = int(min_trade + (bp / 10000) * (max_trade - min_trade))
                            
                            # Try both directions (A→B→A)
                            # First try base_mint → token_mint → base_mint
                            profit1 = await self._simulate_triangular_arbitrage(
                                base_mint, token_mint, amount_in
                            )
                            
                            if profit1 and profit1 > min_profit:
                                opportunities.append(BackrunOpportunity(
                                    target_signature=tx_info.signature,
                                    input_mint=base_mint,
                                    output_mint=token_mint,
                                    amount_in=amount_in,
                                    expected_profit=profit1,
                                    price_impact_pct=tx_info.price_impact_pct,
                                    transaction_data=tx_info.transaction_data,
                                    dex=tx_info.dex
                                ))
                            
                            # Then try token_mint → base_mint → token_mint
                            profit2 = await self._simulate_triangular_arbitrage(
                                token_mint, base_mint, amount_in
                            )
                            
                            if profit2 and profit2 > min_profit:
                                opportunities.append(BackrunOpportunity(
                                    target_signature=tx_info.signature,
                                    input_mint=token_mint,
                                    output_mint=base_mint,
                                    amount_in=amount_in,
                                    expected_profit=profit2,
                                    price_impact_pct=tx_info.price_impact_pct,
                                    transaction_data=tx_info.transaction_data,
                                    dex=tx_info.dex
                                ))
            
            return opportunities
            
        except Exception as e:
            logger.error(f"Error analyzing backrun opportunities: {str(e)}")
            return []
    
    async def _simulate_triangular_arbitrage(
        self, input_mint: str, output_mint: str, amount_in: int
    ) -> Optional[float]:
        """
        Simulate a triangular arbitrage:
        1. Swap input_mint → output_mint
        2. Swap output_mint → input_mint
        Return the profit in USD, or None if not profitable
        """
        try:
            # Get quote for first swap (input → output)
            first_quote = self.api_client.get_jupiter_quote(
                input_mint=input_mint, 
                output_mint=output_mint, 
                amount=str(amount_in)
            )
            
            if not first_quote:
                return None
            
            # Extract output amount from first swap
            out_amount = int(first_quote.get("outAmount", "0"))
            if out_amount <= 0:
                return None
            
            # Get quote for second swap (output → input)
            second_quote = self.api_client.get_jupiter_quote(
                input_mint=output_mint, 
                output_mint=input_mint, 
                amount=str(out_amount)
            )
            
            if not second_quote:
                return None
            
            # Extract final amount from second swap
            final_amount = int(second_quote.get("outAmount", "0"))
            
            # Calculate profit in input token
            profit_amount = final_amount - amount_in
            
            # If we're losing money, return None
            if profit_amount <= 0:
                return None
            
            # Convert profit to USD if input token is not SOL
            profit_usd = profit_amount
            if input_mint != self.SOL_MINT:
                # Get price in USD
                price = self.api_client.get_jupiter_price(input_mint, "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")  # USDC
                if price > 0:
                    profit_usd = profit_amount * price
            else:
                # SOL price in USD
                sol_price = self.api_client.get_jupiter_price(self.SOL_MINT, "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")  # USDC
                if sol_price > 0:
                    profit_usd = profit_amount * sol_price / 1_000_000_000  # Convert lamports to SOL
            
            return profit_usd
            
        except Exception as e:
            logger.error(f"Error simulating triangular arbitrage: {str(e)}")
            return None
    
    async def _execute_backrun(self, opportunity: BackrunOpportunity):
        """Execute a backrun opportunity using Jito MEV bundles"""
        try:
            logger.info(f"Executing backrun for {opportunity.target_signature} with expected profit ${opportunity.expected_profit:.6f}")
            
            # Create an ArbitrageOpportunity object based on the BackrunOpportunity
            # This allows us to use the existing arbitrage execution flow
            arb_opportunity = ArbitrageOpportunity(
                source_pool_id=opportunity.target_signature[:8],  # Use part of the signature as ID
                target_pool_id=opportunity.target_signature[:8] + "-target",
                token_path=[opportunity.input_mint, opportunity.output_mint, opportunity.input_mint],
                expected_profit=str(opportunity.expected_profit),
                profit_percentage=opportunity.price_impact_pct,
                estimated_gas_cost="0.00001",
                route_type="backrun",
                timestamp=int(time.time())
            )
            
            # Submit the opportunity to the blockchain API client for logging/tracking purposes
            self.api_client.submit_arbitrage_opportunities([arb_opportunity])
            
            # Convert target signature to Solders format
            target_sig = Signature.from_string(opportunity.target_signature)
            
            # 1. Get Jupiter swap instructions for first leg: input_mint -> output_mint
            first_quote = self.api_client.get_jupiter_quote(
                input_mint=opportunity.input_mint,
                output_mint=opportunity.output_mint,
                amount=str(opportunity.amount_in),
                slippage=50  # 0.5% slippage
            )
            
            if not first_quote or 'swapTransaction' not in first_quote:
                logger.error("Failed to get first swap transaction")
                return False
                
            # 2. Get first output amount
            first_output_amount = int(first_quote.get("outAmount", "0"))
            if first_output_amount <= 0:
                logger.error("First swap output amount is zero or negative")
                return False
                
            # 3. Get Jupiter swap instructions for second leg: output_mint -> input_mint
            second_quote = self.api_client.get_jupiter_quote(
                input_mint=opportunity.output_mint,
                output_mint=opportunity.input_mint,
                amount=str(first_output_amount),
                slippage=50  # 0.5% slippage
            )
            
            if not second_quote or 'swapTransaction' not in second_quote:
                logger.error("Failed to get second swap transaction")
                return False
            
            # 4. Build transaction bundle
            first_swap_tx_data = first_quote['swapTransaction']
            second_swap_tx_data = second_quote['swapTransaction']
            
            # Convert base64 transaction to VersionedTransaction
            first_swap_tx_bytes = base64.b64decode(first_swap_tx_data)
            second_swap_tx_bytes = base64.b64decode(second_swap_tx_data)
            
            first_swap_tx = VersionedTransaction.from_bytes(first_swap_tx_bytes)
            second_swap_tx = VersionedTransaction.from_bytes(second_swap_tx_bytes)
            
            # 5. Submit the transaction bundle using JitoExecutor
            # We'll first make sure the JitoExecutor is initialized
            if not self.jito_executor.initialized:
                await self.jito_executor.initialize()
            
            # Create bundle with both transactions
            transactions = [first_swap_tx, second_swap_tx]
            
            logger.info(f"Submitting backrun bundle with target signature {opportunity.target_signature}")
            logger.info(f"Bundle contains triangular arbitrage: {opportunity.input_mint} → {opportunity.output_mint} → {opportunity.input_mint}")
            
            # Submit bundle using JitoExecutor
            bundle_id = await self.jito_executor.submit_transactions(transactions)
            
            if bundle_id:
                logger.info(f"Successfully submitted backrun bundle with ID: {bundle_id}")
                return True
            else:
                logger.error("Failed to submit backrun bundle")
                return False
                
        except Exception as e:
            logger.error(f"Error executing backrun: {str(e)}")
            return False

# Helper function to create a new BackrunStrategy instance
def create_backrun_strategy(config: Config, api_client: BlockchainAPIClient, wallet_manager: WalletManager) -> BackrunStrategy:
    """Create a new BackrunStrategy instance"""
    return BackrunStrategy(config, api_client, wallet_manager)