import json
import os
import aiohttp
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from config import Config

@dataclass
class TokenInfo:
    address: str
    symbol: str
    name: str
    decimals: int

@dataclass
class PoolData:
    id: str
    version: int
    base_token: TokenInfo
    quote_token: TokenInfo
    lp_mint: str
    base_vault: str
    quote_vault: str
    base_amount: str  # String to preserve precision
    quote_amount: str  # String to preserve precision
    fee_rate: int  # In basis points (e.g., 30 = 0.3%)
    
    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> 'PoolData':
        """Convert JSON data to PoolData object"""
        return cls(
            id=data['id'],
            version=data['version'],
            base_token=TokenInfo(
                address=data['baseToken']['address'],
                symbol=data['baseToken'].get('symbol', 'Unknown'),
                name=data['baseToken'].get('name', 'Unknown Token'),
                decimals=data['baseToken']['decimals']
            ),
            quote_token=TokenInfo(
                address=data['quoteToken']['address'],
                symbol=data['quoteToken'].get('symbol', 'Unknown'),
                name=data['quoteToken'].get('name', 'Unknown Token'),
                decimals=data['quoteToken']['decimals']
            ),
            lp_mint=data['lpMint'],
            base_vault=data['baseVault'],
            quote_vault=data['quoteVault'],
            base_amount=data['baseAmount'],
            quote_amount=data['quoteAmount'],
            fee_rate=data['feeRate']
        )

@dataclass
class ArbitrageOpportunity:
    source_pool_id: str
    target_pool_id: str
    token_path: List[str]  # Path of token addresses
    expected_profit: str  # In USD, as string to preserve precision
    profit_percentage: float
    estimated_gas_cost: str
    route_type: str
    timestamp: int
    
    def to_json(self) -> Dict[str, Any]:
        """Convert object to JSON serializable dict"""
        return {
            "sourcePoolId": self.source_pool_id,
            "targetPoolId": self.target_pool_id,
            "tokenPath": self.token_path,
            "expectedProfit": self.expected_profit,
            "profitPercentage": self.profit_percentage,
            "estimatedGasCost": self.estimated_gas_cost,
            "routeType": self.route_type,
            "timestamp": self.timestamp
        }

@dataclass
class TipAccount:
    pubkey: str
    balance: float
    last_update: int

class BlockchainAPIClient:
    """Client for interacting with external blockchain APIs (Helius, Jito, Jupiter)"""
    
    # Raydium Program IDs
    RAYDIUM_V3_PROGRAM_ID = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
    RAYDIUM_V4_PROGRAM_ID = "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK"
    
    def __init__(self, config: Config):
        self.config = config
        self.use_local_server = False  # Always use external APIs for now
        
        # API endpoints
        self.base_url = "https://api.raydium.io"
        
        # Session will be created when needed
        self.session = None
        self.headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        # Store common API endpoints
        self.jupiter_api = config.JUPITER_API_URL
        self.raydium_api = config.RAYDIUM_API_ENDPOINT
    
    async def init_jito_connection(self, max_sockets=25, socket_timeout=19000, keepalive=True) -> bool:
        """Initialize connection to Jito service"""
        try:
            response = self.session.post(f"{self.base_url}/api/jito/init", json={
                'maxSockets': max_sockets,
                'socketTimeout': socket_timeout,
                'keepalive': keepalive
            })
            
            if response.status_code != 200:
                print(f"Failed to initialize Jito connection: HTTP {response.status_code}")
                return False
                
            data = response.json()
            return data.get('success', False)
            
        except Exception as e:
            print(f"Error initializing Jito connection: {e}")
            return False
    
    async def _handle_response(self, response: aiohttp.ClientResponse) -> Dict[str, Any]:
        """Handle API response and errors"""
        try:
            if not response.ok:
                try:
                    error_data = await response.json()
                    error_message = error_data.get('error', f"HTTP {response.status}")
                except:
                    error_message = f"HTTP {response.status}"
                raise Exception(f"API Error: {error_message}")
            return await response.json()
        except aiohttp.ClientError as e:
            raise Exception(f"Request failed: {str(e)}")
        except json.JSONDecodeError:
            raise Exception("Failed to parse API response")
    
    async def get_transaction(self, signature: str) -> Optional[Dict]:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTransaction",
            "params": [signature, {"maxSupportedTransactionVersion": 0}]
        }
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.post(self.config.RPC_ENDPOINT, json=payload, timeout=15) as resp:
                    data = await resp.json()
                    return data.get("result")
        except Exception as e:
            print(f"Error fetching transaction: {e}")
            return None
    
    async def get_account_info(self, address: str) -> Optional[Dict]:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getAccountInfo",
            "params": [address, {"encoding": "base64"}]
        }
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.post(self.config.RPC_ENDPOINT, json=payload, timeout=15) as resp:
                    data = await resp.json()
                    return data.get("result")
        except Exception as e:
            print(f"Error fetching account info: {e}")
            return None
    
    async def get_program_transactions(self, program_id: str, limit: int = 100) -> List[Dict]:
        """Get recent transactions/signatures for a program via JSON-RPC"""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getSignaturesForAddress",
            "params": [program_id, {"limit": limit}]
        }
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.post(self.config.RPC_ENDPOINT, json=payload, timeout=15) as resp:
                    data = await resp.json()
                    result = data.get("result", []) or []
                    return result
        except Exception as e:
            print(f"Error fetching program transactions: {e}")
            return []
    
    async def check_api_health(self) -> bool:
        """Check if external APIs are available or local server if enabled"""
        async with aiohttp.ClientSession(headers=self.headers) as session:
            if self.use_local_server:
                try:
                    async with session.get(f"{self.base_url}/api/health", timeout=5) as response:
                        return response.status == 200
                except Exception as e:
                    print(f"Local API health check failed: {e}")
                    return False
            else:
                # Check external APIs directly
                try:
                    # Test Helius/RPC endpoint
                    async with session.post(
                        self.config.RPC_ENDPOINT,
                        json={"jsonrpc": "2.0", "id": 1, "method": "getHealth"},
                        timeout=10
                    ) as response:
                        if response.status != 200:
                            return False
                    
                    # Test Jupiter API
                    async with session.get(
                        f"{self.config.JUPITER_API_URL}/quote",
                        params={
                            "inputMint": "So11111111111111111111111111111111111111112",
                            "outputMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                            "amount": "1000000"
                        },
                        timeout=10
                    ) as response:
                        return response.status == 200
                    
                except Exception as e:
                    print(f"External API health check failed: {e}")
                    return False
    
    async def get_raydium_pools(self) -> List[PoolData]:
        """Get all Raydium pools"""
        async with aiohttp.ClientSession(headers=self.headers) as session:
            async with session.get(f"{self.base_url}/api/pools/raydium") as response:
                if response.status != 200:
                    raise Exception(f"Failed to get Raydium pools: HTTP {response.status}")
                
                data = await response.json()
                if not data.get('success'):
                    raise Exception(f"Failed to get Raydium pools: {data.get('error')}")
                
                pools = []
                for pool_data in data.get('data', []):
                    try:
                        pool = PoolData.from_json(pool_data)
                        pools.append(pool)
                    except Exception as e:
                        print(f"Error parsing pool data: {str(e)}")
                
                return pools
    
    async def get_raydium_pool(self, pool_id: str) -> Optional[PoolData]:
        """Get specific Raydium pool data"""
        async with aiohttp.ClientSession(headers=self.headers) as session:
            async with session.get(f"{self.base_url}/api/pools/raydium/{pool_id}") as response:
                # Handle 404 specially
                if response.status == 404:
                    return None
                    
                data = await response.json()
                if not data.get('success'):
                    raise Exception(f"Failed to get pool data: {data.get('error')}")
                    
                try:
                    return PoolData.from_json(data['data'])
                except Exception as e:
                    print(f"Error parsing pool data: {str(e)}")
                    return None
        if response.status_code == 404:
            return None
            
        data = self._handle_response(response)
        
        if not data.get('success'):
            raise Exception(f"Failed to get Raydium pool: {data.get('error')}")
        
        try:
            return PoolData.from_json(data['data'])
        except Exception as e:
            print(f"Error parsing pool data: {str(e)}")
            return None
    
    def get_jupiter_price(self, input_mint: str, output_mint: str, amount: str = "1000000000") -> float:
        """
        Get token price from Jupiter with enhanced error handling and rate limiting
        
        Args:
            input_mint: Input token mint address
            output_mint: Output token mint address (usually USDC)
            amount: Amount to quote (default 1 SOL equivalent)
            
        Returns:
            Price of input token in terms of output token
        """
        try:
            if self.use_local_server:
                # Try the TypeScript service first
                try:
                    response = self.session.get(f"{self.base_url}/api/jupiter/price", params={
                        "inputMint": input_mint,
                        "outputMint": output_mint,
                        "amount": amount
                    }, timeout=10)
                    data = self._handle_response(response)
                    return float(data.get("price", 0))
                except Exception as e:
                    print(f"TypeScript service unavailable: {e}, falling back to direct Jupiter API")
            
            # Use direct Jupiter quote API with rate limiting
            import time
            time.sleep(0.2)  # Rate limiting - 5 requests per second max
            
            jupiter_url = f"{self.config.JUPITER_API_URL}/quote"
            response = requests.get(jupiter_url, params={
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": amount,
                "slippageBps": 50
            }, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if "outAmount" in data:
                    out_amount = float(data["outAmount"])
                    in_amount = float(amount)
                    return out_amount / in_amount if in_amount > 0 else 0
            elif response.status_code == 429:
                print("Jupiter API rate limit hit, backing off")
                time.sleep(2)
            return 0
                
        except Exception as e:
            print(f"Error getting Jupiter price for {input_mint[:8]}.../{output_mint[:8]}...: {e}")
            return 0

    def get_cross_dex_prices(self, token_address: str, base_token: str = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v") -> Dict[str, float]:
        """
        Get token prices across multiple DEXes for arbitrage detection
        
        Args:
            token_address: Token to get prices for
            base_token: Base token for pricing (default USDC)
            
        Returns:
            Dictionary with DEX names as keys and prices as values
        """
        prices = {}
        
        try:
            # Get Jupiter aggregated price (includes multiple DEXes)
            jupiter_price = self.get_jupiter_price(token_address, base_token)
            if jupiter_price > 0:
                prices["Jupiter"] = jupiter_price
            
            # Get Raydium-specific price
            raydium_price = self.get_raydium_price_direct(token_address, base_token)
            if raydium_price > 0:
                prices["Raydium"] = raydium_price
            
            # Get Meteora price via DexScreener
            meteora_price = self.get_meteora_price(token_address)
            if meteora_price > 0:
                prices["Meteora"] = meteora_price
                
        except Exception as e:
            print(f"Error getting cross-DEX prices: {e}")
        
        return prices

    def get_raydium_price_direct(self, token_address: str, base_token: str) -> float:
        """Get price directly from Raydium pools"""
        try:
            pools = self.get_raydium_pools()
            
            for pool in pools:
                # Check if this pool contains our token pair
                if ((pool.base_token.address == token_address and pool.quote_token.address == base_token) or
                    (pool.base_token.address == base_token and pool.quote_token.address == token_address)):
                    
                    base_amount = float(pool.base_amount) / (10 ** pool.base_token.decimals)
                    quote_amount = float(pool.quote_amount) / (10 ** pool.quote_token.decimals)
                    
                    if pool.base_token.address == token_address and base_amount > 0:
                        return quote_amount / base_amount
                    elif pool.quote_token.address == token_address and quote_amount > 0:
                        return base_amount / quote_amount
            
            return 0
        except Exception as e:
            print(f"Error getting Raydium price: {e}")
            return 0

    def get_meteora_price(self, token_address: str) -> float:
        """Get Meteora price via DexScreener API with rate limiting"""
        try:
            import time
            time.sleep(0.3)  # Rate limiting for DexScreener
            
            url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
            response = requests.get(url, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'
            })
            
            if response.status_code == 200:
                data = response.json()
                pairs = data.get('pairs', [])
                
                # Look for Meteora pairs specifically
                meteora_pairs = [p for p in pairs if p.get('dexId') == 'meteora']
                if meteora_pairs:
                    # Get the most liquid Meteora pair
                    best_pair = max(meteora_pairs, key=lambda p: float(p.get('liquidity', {}).get('usd', 0)))
                    return float(best_pair.get('priceUsd', 0))
            elif response.status_code == 429:
                print("DexScreener rate limit hit")
                time.sleep(5)
            
            return 0
        except Exception as e:
            print(f"Error getting Meteora price: {e}")
            return 0

    def get_jupiter_quote(
        self, 
        input_mint: str, 
        output_mint: str, 
        amount: str,
        slippage: int = 100  # Default 1%
    ) -> Optional[Dict[str, Any]]:
        """
        Get a Jupiter swap quote
        
        Args:
            input_mint: Input token mint address
            output_mint: Output token mint address
            amount: Amount of input token in raw units (not decimalized)
            slippage: Slippage tolerance in basis points (e.g., 100 = 1%)
            
        Returns:
            Quote data if successful, None otherwise
        """
        payload = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": amount,
            "slippageBps": slippage
        }
        
        try:
            response = self.session.post(f"{self.base_url}/api/jupiter/quote", json=payload)
            return self._handle_response(response)
        except Exception as e:
            print(f"Error getting Jupiter quote: {e}")
            return None
    
    def check_arbitrage_opportunity(
        self,
        token_a: str,
        token_b: str,
        amount: str,
        min_profit_threshold_usd: float = 1.0
    ) -> Dict[str, Any]:
        """Check for arbitrage opportunity between token pair"""
        payload = {
            'tokenA': token_a,
            'tokenB': token_b,
            'amount': amount,
            'minProfitThresholdUsd': min_profit_threshold_usd
        }
        
        response = self.session.post(f"{self.base_url}/api/arbitrage/check", json=payload)
        data = self._handle_response(response)
        
        if not data.get('success'):
            raise Exception(f"Failed to check arbitrage opportunity: {data.get('error')}")
        
        return data['data']
    
    def submit_arbitrage_opportunities(
        self,
        opportunities: List[ArbitrageOpportunity]
    ) -> bool:
        """Submit arbitrage opportunities to the TypeScript service for execution"""
        payload = {
            'opportunities': [opp.to_json() for opp in opportunities]
        }
        
        response = self.session.post(f"{self.base_url}/api/arbitrage/opportunities", json=payload)
        data = self._handle_response(response)
        
        return data.get('success', False)
    
    def get_jito_tip_accounts(self) -> List[TipAccount]:
        """Get Jito tip accounts from TypeScript service"""
        try:
            response = self.session.get(f"{self.base_url}/api/jito/tip-accounts")
            if response.status_code != 200:
                raise Exception(f"API returned status {response.status_code}")

            data = response.json()
            if not data.get('success'):
                raise Exception(data.get('error', 'Unknown error'))

            return [
                TipAccount(
                    pubkey=account['pubkey'],
                    balance=account['balance'],
                    last_update=account['lastUpdate']
                )
                for account in data['data']
            ]
        except Exception as e:
            print(f"Error getting tip accounts: {e}")
            return []

    def submit_jito_bundle(self, transactions: List[str]) -> Optional[str]:
        """Submit transaction bundle to Jito through TypeScript service"""
        try:
            response = self.session.post(
                f"{self.base_url}/api/jito/submit-bundle",
                json={'transactions': transactions}
            )
            
            if response.status_code != 200:
                raise Exception(f"API returned status {response.status_code}")

            data = response.json()
            if not data.get('success'):
                raise Exception(data.get('error', 'Unknown error'))

            return data['data']['bundleId']
        except Exception as e:
            print(f"Error submitting bundle: {e}")
            return None

    def get_next_block(self) -> Optional[int]:
        """Get next block height from Jito"""
        try:
            response = self.session.get(f"{self.base_url}/api/jito/next-block")
            return self._handle_response(response)['data']['nextBlock']
        except Exception as e:
            print(f"Error getting next block: {e}")
            return None

    async def submit_bundle(self, transactions, tip_lamports=0) -> Optional[str]:
        """Submit bundle of transactions to Jito"""
        try:
            # Convert transactions to base64 strings
            tx_base64_list = []
            for tx in transactions:
                tx_base64_list.append(base64.b64encode(tx.serialize()).decode('ascii'))
            
            # Prepare payload with tip
            payload = {
                'transactions': tx_base64_list,
                'tipLamports': tip_lamports
            }
            
            # Submit to API
            response = self.session.post(
                f"{self.base_url}/api/jito/submit-bundle",
                json=payload
            )
            
            if response.status_code != 200:
                print(f"Failed to submit bundle: HTTP {response.status_code}")
                return None
                
            data = response.json()
            if not data.get('success'):
                print(f"Bundle submission failed: {data.get('error', 'Unknown error')}")
                return None
                
            return data.get('data', {}).get('bundleId')
            
        except Exception as e:
            print(f"Error submitting bundle: {e}")
            return None
    
    async def get_bundle_status(self, bundle_id: str) -> Dict[str, Any]:
        """Get status of a submitted bundle"""
        try:
            response = self.session.get(f"{self.base_url}/api/jito/bundle-status/{bundle_id}")
            
            if response.status_code != 200:
                return {"status": "error", "error": f"HTTP {response.status_code}"}
                
            data = response.json()
            if not data.get('success'):
                return {"status": "error", "error": data.get('error', 'Unknown error')}
                
            return data.get('data', {"status": "unknown"})
            
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    async def simulate_transactions(self, tx_base64_list: List[str]) -> Dict[str, Any]:
        """Simulate a bundle of transactions"""
        try:
            response = self.session.post(
                f"{self.base_url}/api/transactions/simulate",
                json={'transactions': tx_base64_list}
            )
            
            if response.status_code != 200:
                return {"success": False, "error": f"HTTP {response.status_code}"}
                
            data = response.json()
            return data
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def build_triangle_arbitrage_tx(
        self,
        tokens: List[str],
        pools: List[str],
        amount: float,
        slippage_bps: int = 100,
        priority_fee: Optional[str] = None,
        dynamic_compute_limit: bool = True
    ) -> Dict[str, Any]:
        """Build a transaction for triangle arbitrage"""
        try:
            payload = {
                "tokens": tokens,
                "pools": pools,
                "amount": str(amount),
                "slippageBps": slippage_bps,
                "priorityFee": priority_fee,
                "dynamicComputeLimit": dynamic_compute_limit
            }
            
            response = self.session.post(
                f"{self.base_url}/api/arbitrage/build-triangle-tx",
                json=payload
            )
            
            return self._handle_response(response)
            
        except Exception as e:
            print(f"Error building triangle arbitrage transaction: {e}")
            return {}
    
    async def build_cross_dex_arbitrage_tx(
        self,
        source_dex: str,
        target_dex: str,
        token_pair: List[str],
        amount: float,
        slippage_bps: int = 100,
        priority_fee: Optional[str] = None,
        dynamic_compute_limit: bool = True
    ) -> Dict[str, Any]:
        """Build a transaction for cross-DEX arbitrage"""
        try:
            payload = {
                "sourceDex": source_dex,
                "targetDex": target_dex,
                "tokenPair": token_pair,
                "amount": str(amount),
                "slippageBps": slippage_bps,
                "priorityFee": priority_fee,
                "dynamicComputeLimit": dynamic_compute_limit
            }
            
            response = self.session.post(
                f"{self.base_url}/api/arbitrage/build-cross-dex-tx",
                json=payload
            )
            
            return self._handle_response(response)
            
        except Exception as e:
            print(f"Error building cross-DEX arbitrage transaction: {e}")
            return {}
    
    async def build_flash_loan_arbitrage_tx(
        self,
        tokens: List[str],
        pools: List[str],
        amount: float,
        flash_loan_market: str,
        slippage_bps: int = 100,
        priority_fee: Optional[str] = None,
        dynamic_compute_limit: bool = True
    ) -> Dict[str, Any]:
        """Build a transaction for flash loan arbitrage"""
        try:
            payload = {
                "tokens": tokens,
                "pools": pools,
                "amount": str(amount),
                "flashLoanMarket": flash_loan_market,
                "slippageBps": slippage_bps,
                "priorityFee": priority_fee,
                "dynamicComputeLimit": dynamic_compute_limit
            }
            
            response = self.session.post(
                f"{self.base_url}/api/arbitrage/build-flash-loan-tx",
                json=payload
            )
            
            return self._handle_response(response)
            
        except Exception as e:
            print(f"Error building flash loan arbitrage transaction: {e}")
            return {}
    
    async def calculate_arbitrage_profit(
        self,
        opportunity_type: str,
        tokens: List[str],
        pools: List[str],
        amount: float
    ) -> float:
        """Calculate expected profit for an arbitrage opportunity"""
        try:
            payload = {
                "type": opportunity_type,
                "tokens": tokens,
                "pools": pools,
                "amount": str(amount)
            }
            
            response = self.session.post(
                f"{self.base_url}/api/arbitrage/calculate-profit",
                json=payload
            )
            
            data = self._handle_response(response)
            return float(data.get("profit", 0))
            
        except Exception as e:
            print(f"Error calculating arbitrage profit: {e}")
            return 0.0