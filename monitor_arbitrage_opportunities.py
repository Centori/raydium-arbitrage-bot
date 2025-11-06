#!/usr/bin/env python3
"""
Real-time Arbitrage Opportunity Monitor
Monitors all configured DEXes for emerging arbitrage opportunities
"""

import asyncio
import time
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import aiohttp
from rich.console import Console
from rich.table import Table
from rich.layout import Layout
from rich.panel import Panel
from rich.live import Live
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.columns import Columns
import requests

from config import Config, DEX_CONFIG, PATTERN_CONFIG, MONITORED_PAIRS
from api_client import BlockchainAPIClient
from raydium_pools import RaydiumPoolFetcher
from risk_analyzer import RiskAnalyzer

# Initialize Rich console
console = Console()

@dataclass
class ArbitrageOpportunity:
    """Represents a potential arbitrage opportunity"""
    opportunity_id: str
    pattern_type: str  # CROSS_DEX, TRIANGULAR, FLASH_LOAN
    dexes: List[str]
    token_path: List[str]
    expected_profit_sol: float
    expected_profit_usd: float
    price_impact: float
    confidence_score: float
    timestamp: float
    execution_path: List[Dict[str, Any]]
    gas_estimate: float = 0.001
    risk_score: int = 0
    
    @property
    def net_profit_sol(self) -> float:
        return self.expected_profit_sol - self.gas_estimate
    
    @property
    def is_profitable(self) -> bool:
        return self.net_profit_sol > 0

@dataclass
class DEXPoolData:
    """Stores pool data for a specific DEX"""
    dex_name: str
    pool_address: str
    token_a: str
    token_b: str
    reserve_a: float
    reserve_b: float
    price_a_to_b: float
    price_b_to_a: float
    liquidity_usd: float
    volume_24h: float = 0
    last_update: float = field(default_factory=time.time)

class ArbitrageMonitor:
    def __init__(self, config: Config):
        self.config = config
        self.api_client = BlockchainAPIClient(config)
        self.pool_fetcher = RaydiumPoolFetcher(config)
        self.risk_analyzer = RiskAnalyzer(config)
        
        # Store pool data by DEX
        self.dex_pools: Dict[str, List[DEXPoolData]] = defaultdict(list)
        
        # Track opportunities
        self.active_opportunities: List[ArbitrageOpportunity] = []
        self.opportunity_history: List[ArbitrageOpportunity] = []
        self.executed_opportunities = 0
        self.total_profit = 0.0
        
        # Performance metrics
        self.start_time = time.time()
        self.last_update_time = time.time()
        self.update_count = 0
        self.sol_price = 0.0
        
        # Monitoring state
        self.is_running = False
        self.update_interval = 2  # seconds
        
    async def start_monitoring(self):
        """Start the monitoring process"""
        self.is_running = True
        console.print("[bold green]Starting Arbitrage Opportunity Monitor...[/bold green]")
        
        # Initial setup
        await self._update_sol_price()
        
        # Create monitoring tasks
        tasks = [
            asyncio.create_task(self._monitor_loop()),
            asyncio.create_task(self._display_loop()),
            asyncio.create_task(self._cleanup_loop())
        ]
        
        try:
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            console.print("\n[bold red]Stopping monitor...[/bold red]")
            self.is_running = False
    
    async def _monitor_loop(self):
        """Main monitoring loop"""
        while self.is_running:
            try:
                await self._update_pool_data()
                await self._find_opportunities()
                self.update_count += 1
                self.last_update_time = time.time()
                await asyncio.sleep(self.update_interval)
            except Exception as e:
                console.print(f"[red]Error in monitor loop: {str(e)}[/red]")
                await asyncio.sleep(5)
    
    async def _update_sol_price(self):
        """Update SOL price in USD"""
        try:
            # Get SOL price from Jupiter
            response = await self._fetch_jupiter_price(
                "So11111111111111111111111111111111111111112",
                "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"  # USDC
            )
            if response:
                self.sol_price = float(response.get("price", 0))
        except Exception as e:
            console.print(f"[yellow]Warning: Could not update SOL price: {str(e)}[/yellow]")
            self.sol_price = 100  # Default fallback
    
    async def _fetch_jupiter_price(self, input_mint: str, output_mint: str) -> Optional[Dict]:
        """Fetch price from Jupiter API"""
        try:
            url = f"{self.config.JUPITER_API_URL}/quote"
            params = {
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": "1000000000"  # 1 SOL in lamports
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data and "outAmount" in data:
                            price = int(data["outAmount"]) / 1000000  # Convert to USDC
                            return {"price": price}
        except Exception as e:
            console.print(f"[yellow]Error fetching Jupiter price: {str(e)}[/yellow]")
        return None
    
    async def _fetch_jupiter_real_price(self, input_mint: str, output_mint: str, dex_filter: str = None) -> float:
        """Fetch real-time price from Jupiter API with optional DEX filter"""
        try:
            url = f"{self.config.JUPITER_API_URL}/quote"
            params = {
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": "1000000000",  # 1 token in smallest units
                "onlyDirectRoutes": "true"  # Must be string for Jupiter API
            }
            
            # Add DEX filter if specified
            if dex_filter:
                dex_mapping = {
                    "Raydium": "raydium",
                    "Orca": "orca",
                    "Phoenix": "phoenix",
                    "Meteora": "meteora"
                }
                if dex_filter in dex_mapping:
                    params["dexes"] = dex_mapping[dex_filter]
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data and "outAmount" in data:
                            # Calculate price based on amounts
                            out_amount = float(data["outAmount"])
                            in_amount = 1000000000.0
                            
                            # Determine decimals (simplified - SOL=9, USDC=6, USDT=6)
                            out_decimals = 6 if output_mint == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v" or output_mint == "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB" else 9
                            in_decimals = 9 if input_mint == "So11111111111111111111111111111111111111112" else 6
                            
                            price = (out_amount / 10**out_decimals) / (in_amount / 10**in_decimals)
                            return price
            return 0.0
        except Exception as e:
            console.print(f"[dim yellow]Warning: Could not fetch real price: {str(e)}[/dim yellow]")
            return 0.0
    
    async def _update_pool_data(self):
        """Update pool data from all DEXes"""
        # Clear old data
        self.dex_pools.clear()
        
        # Fetch data for each DEX
        for dex_name, dex_config in DEX_CONFIG.items():
            try:
                pools = await self._fetch_dex_pools(dex_name, dex_config)
                self.dex_pools[dex_name] = pools
            except Exception as e:
                console.print(f"[yellow]Error fetching {dex_name} pools: {str(e)}[/yellow]")
    
    async def _fetch_dex_pools(self, dex_name: str, dex_config: Dict) -> List[DEXPoolData]:
        """Fetch pool data for a specific DEX using real API data"""
        pools = []
        
        # Get token pairs from configuration
        token_pairs = []
        for pair in MONITORED_PAIRS:
            token_pairs.append((pair["base"], pair["quote"]))
        
        # If no configured pairs, use defaults
        if not token_pairs:
            token_pairs = [
                ("So11111111111111111111111111111111111111112", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"),  # SOL/USDC
                ("So11111111111111111111111111111111111111112", "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"),  # SOL/USDT
                ("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"),  # USDC/USDT
            ]
        
        for token_a, token_b in token_pairs:
            try:
                # Add delay to respect Jupiter API rate limits (max 5 req/sec = 200ms between calls)
                await asyncio.sleep(0.25)  # 250ms delay = 4 requests per second
                
                # Fetch real price from Jupiter API
                price = await self._fetch_jupiter_real_price(token_a, token_b, dex_name)
                
                if price > 0:
                    pool = DEXPoolData(
                        dex_name=dex_name,
                        pool_address=f"{dex_name}_{token_a[:8]}_{token_b[:8]}",
                        token_a=token_a,
                        token_b=token_b,
                        reserve_a=1000000,
                        reserve_b=1000000 * price,
                        price_a_to_b=price,
                        price_b_to_a=1/price if price > 0 else 0,
                        liquidity_usd=2000000,  # Would need separate API call for real liquidity
                        volume_24h=500000
                    )
                    pools.append(pool)
            except Exception as e:
                console.print(f"[yellow]Error fetching price for {token_a[:8]}/{token_b[:8]} on {dex_name}: {e}[/yellow]")
        
        return pools
    
    async def _find_opportunities(self):
        """Find arbitrage opportunities across all DEXes"""
        new_opportunities = []
        
        # Find cross-DEX opportunities
        cross_dex_opps = await self._find_cross_dex_opportunities()
        new_opportunities.extend(cross_dex_opps)
        
        # Find triangular opportunities
        triangular_opps = await self._find_triangular_opportunities()
        new_opportunities.extend(triangular_opps)
        
        # Update active opportunities
        self.active_opportunities = [
            opp for opp in new_opportunities 
            if opp.is_profitable and opp.confidence_score > 0.7
        ]
        
        # Sort by profit
        self.active_opportunities.sort(key=lambda x: x.net_profit_sol, reverse=True)
        
        # Keep only top 20 opportunities
        self.active_opportunities = self.active_opportunities[:20]
    
    async def find_cross_dex_opportunities(self):
        """Public method to find cross-DEX arbitrage opportunities"""
        await self._update_pool_data()
        opportunities = await self._find_cross_dex_opportunities()
        
        # Convert to dict format for compatibility
        result = []
        for opp in opportunities:
            if opp.is_profitable:
                # Calculate price difference percentage from the opportunity
                # Price diff = gross profit / trade size * 100
                trade_size = 0.01  # Our configured trade size
                gross_profit = opp.expected_profit_sol + opp.gas_estimate + (trade_size * 0.005) + (trade_size * 0.015)
                price_diff_pct = (gross_profit / trade_size) * 100 if trade_size > 0 else 0
                
                result.append({
                    'pair': ' → '.join([t[:8] for t in opp.token_path[:2]]),
                    'profit_usd': opp.expected_profit_usd,
                    'price_diff_pct': price_diff_pct,
                    'dexes': opp.dexes,
                    'confidence': opp.confidence_score,
                    'net_profit_sol': opp.net_profit_sol,
                    'gas_cost': opp.gas_estimate,
                    'price_impact': opp.price_impact
                })
        return result
    
    async def _find_cross_dex_opportunities(self) -> List[ArbitrageOpportunity]:
        """Find arbitrage opportunities between different DEXes"""
        opportunities = []
        
        # Group pools by token pair
        pools_by_pair = defaultdict(list)
        for dex_name, pools in self.dex_pools.items():
            for pool in pools:
                pair_key = tuple(sorted([pool.token_a, pool.token_b]))
                pools_by_pair[pair_key].append((dex_name, pool))
        
        # Find price differences between DEXes
        for pair_key, dex_pools in pools_by_pair.items():
            if len(dex_pools) < 2:
                continue
                
            # Compare prices between each pair of DEXes
            for i in range(len(dex_pools)):
                for j in range(i + 1, len(dex_pools)):
                    dex1_name, pool1 = dex_pools[i]
                    dex2_name, pool2 = dex_pools[j]
                    
                    # Calculate price difference
                    price_diff_pct = abs(pool1.price_a_to_b - pool2.price_a_to_b) / pool1.price_a_to_b * 100
                    
                    if price_diff_pct > self.config.MIN_CROSS_DEX_DIFF_PCT:
                        # Determine buy/sell direction
                        if pool1.price_a_to_b < pool2.price_a_to_b:
                            buy_dex, sell_dex = dex1_name, dex2_name
                            buy_pool, sell_pool = pool1, pool2
                        else:
                            buy_dex, sell_dex = dex2_name, dex1_name
                            buy_pool, sell_pool = pool2, pool1
                        
                        # Calculate potential profit with realistic trade size
                        trade_amount_sol = min(self.config.MAX_BUY_SOL, 0.01)  # Use actual max trade size
                        
                        # Calculate gross profit from price difference
                        gross_profit_sol = trade_amount_sol * price_diff_pct / 100
                        
                        # Account for slippage (from config, default 1.5%)
                        slippage_bps = self.config.SLIPPAGE_BPS if hasattr(self.config, 'SLIPPAGE_BPS') else 150
                        slippage_cost = trade_amount_sol * (slippage_bps / 10000)
                        
                        # Account for DEX fees (typical 0.25% per swap, 2 swaps = 0.5%)
                        dex_fees = trade_amount_sol * 0.005  # 0.5% total for buy + sell
                        
                        # Account for gas fees (realistic Solana costs)
                        # Base transaction: ~0.000005 SOL per signature
                        # Priority fee: ~0.0001 SOL for faster execution
                        # Total for 2 transactions (buy + sell)
                        gas_cost = 0.0002  # Conservative estimate in SOL
                        
                        # Calculate net profit
                        expected_profit_sol = gross_profit_sol - slippage_cost - dex_fees - gas_cost
                        expected_profit_usd = expected_profit_sol * self.sol_price
                        
                        # Calculate price impact (should be minimal for small trades)
                        min_liquidity = min(buy_pool.liquidity_usd, sell_pool.liquidity_usd)
                        price_impact_pct = (trade_amount_sol * self.sol_price / min_liquidity) * 100
                        
                        # Calculate confidence based on liquidity and price impact
                        liquidity_confidence = min(1.0, min_liquidity / 100000)  # Full confidence at $100k+ liquidity
                        impact_confidence = max(0.0, 1.0 - (price_impact_pct / 2))  # Lower confidence for high impact
                        confidence = (liquidity_confidence + impact_confidence) / 2
                        
                        opportunity = ArbitrageOpportunity(
                            opportunity_id=f"CROSS_{buy_dex}_{sell_dex}_{int(time.time())}",
                            pattern_type="CROSS_DEX",
                            dexes=[buy_dex, sell_dex],
                            token_path=[pool1.token_a, pool1.token_b],
                            expected_profit_sol=expected_profit_sol,
                            expected_profit_usd=expected_profit_usd,
                            price_impact=price_impact_pct,
                            confidence_score=confidence,
                            timestamp=time.time(),
                            execution_path=[
                                {"dex": buy_dex, "action": "BUY", "pool": buy_pool.pool_address},
                                {"dex": sell_dex, "action": "SELL", "pool": sell_pool.pool_address}
                            ],
                            gas_estimate=gas_cost
                        )
                        
                        if opportunity.net_profit_sol > 0:
                            opportunities.append(opportunity)
        
        return opportunities
    
    async def _find_triangular_opportunities(self) -> List[ArbitrageOpportunity]:
        """Find triangular arbitrage opportunities within each DEX"""
        opportunities = []
        
        for dex_name, pools in self.dex_pools.items():
            if len(pools) < 3:
                continue
                
            # Build adjacency list for token graph
            token_graph = defaultdict(list)
            pool_map = {}
            
            for pool in pools:
                token_graph[pool.token_a].append((pool.token_b, pool))
                token_graph[pool.token_b].append((pool.token_a, pool))
                pool_map[(pool.token_a, pool.token_b)] = pool
                pool_map[(pool.token_b, pool.token_a)] = pool
            
            # Find triangular paths
            for start_token in token_graph:
                for second_token, pool1 in token_graph[start_token]:
                    for third_token, pool2 in token_graph[second_token]:
                        if third_token == start_token:
                            continue
                            
                        # Check if we can complete the triangle
                        if start_token in [t for t, _ in token_graph[third_token]]:
                            pool3_key = (third_token, start_token)
                            if pool3_key in pool_map:
                                pool3 = pool_map[pool3_key]
                                
                                # Calculate arbitrage potential
                                # Start -> Second -> Third -> Start
                                rate1 = pool1.price_a_to_b if pool1.token_a == start_token else pool1.price_b_to_a
                                rate2 = pool2.price_a_to_b if pool2.token_a == second_token else pool2.price_b_to_a
                                rate3 = pool3.price_a_to_b if pool3.token_a == third_token else pool3.price_b_to_a
                                
                                combined_rate = rate1 * rate2 * rate3
                                
                                if combined_rate > 1.003:  # 0.3% profit threshold
                                    profit_pct = (combined_rate - 1) * 100
                                    trade_amount_sol = 0.3  # Smaller amount for triangular
                                    expected_profit_sol = trade_amount_sol * profit_pct / 100
                                    expected_profit_usd = expected_profit_sol * self.sol_price
                                    
                                    opportunity = ArbitrageOpportunity(
                                        opportunity_id=f"TRI_{dex_name}_{int(time.time())}",
                                        pattern_type="TRIANGULAR",
                                        dexes=[dex_name],
                                        token_path=[start_token, second_token, third_token, start_token],
                                        expected_profit_sol=expected_profit_sol,
                                        expected_profit_usd=expected_profit_usd,
                                        price_impact=0.1,  # Simplified
                                        confidence_score=0.8,
                                        timestamp=time.time(),
                                        execution_path=[
                                            {"dex": dex_name, "pool": pool1.pool_address, "swap": f"{start_token}->{second_token}"},
                                            {"dex": dex_name, "pool": pool2.pool_address, "swap": f"{second_token}->{third_token}"},
                                            {"dex": dex_name, "pool": pool3.pool_address, "swap": f"{third_token}->{start_token}"}
                                        ],
                                        gas_estimate=0.003  # Higher gas for 3 swaps
                                    )
                                    
                                    if opportunity.net_profit_sol > 0:
                                        opportunities.append(opportunity)
        
        return opportunities
    
    async def _display_loop(self):
        """Display monitoring results in real-time"""
        with Live(self._generate_display(), refresh_per_second=1) as live:
            while self.is_running:
                live.update(self._generate_display())
                await asyncio.sleep(1)
    
    def _generate_display(self) -> Layout:
        """Generate the display layout"""
        layout = Layout()
        
        # Header
        header = Panel(
            Text("🔍 Arbitrage Opportunity Monitor", justify="center", style="bold blue"),
            title="[bold]Real-Time DEX Monitor[/bold]",
            subtitle=f"Last Update: {datetime.now().strftime('%H:%M:%S')}"
        )
        
        # Statistics panel
        stats = self._generate_stats_panel()
        
        # Opportunities table
        opportunities_table = self._generate_opportunities_table()
        
        # DEX status
        dex_status = self._generate_dex_status()
        
        # Layout structure
        layout.split_column(
            Layout(header, size=3),
            Layout(stats, size=8),
            Layout(opportunities_table, size=20),
            Layout(dex_status, size=6)
        )
        
        return layout
    
    def _generate_stats_panel(self) -> Panel:
        """Generate statistics panel"""
        runtime = time.time() - self.start_time
        runtime_str = str(timedelta(seconds=int(runtime)))
        
        stats_text = f"""
[bold cyan]Performance Metrics[/bold cyan]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[yellow]Runtime:[/yellow] {runtime_str}
[yellow]Updates:[/yellow] {self.update_count:,}
[yellow]Update Rate:[/yellow] {self.update_count / max(runtime, 1):.1f}/sec
[yellow]SOL Price:[/yellow] ${self.sol_price:.2f}

[bold green]Active Opportunities:[/bold green] {len(self.active_opportunities)}
[bold blue]Total Opportunities Found:[/bold blue] {len(self.opportunity_history)}
[bold magenta]Executed:[/bold magenta] {self.executed_opportunities}
[bold yellow]Total Profit:[/bold yellow] {self.total_profit:.4f} SOL (${self.total_profit * self.sol_price:.2f})
        """
        
        return Panel(stats_text.strip(), title="[bold]Statistics[/bold]", border_style="green")
    
    def _generate_opportunities_table(self) -> Panel:
        """Generate opportunities table"""
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Type", style="cyan", width=12)
        table.add_column("DEXes", style="yellow")
        table.add_column("Path", style="blue")
        table.add_column("Profit (SOL)", justify="right", style="green")
        table.add_column("Profit (USD)", justify="right", style="green")
        table.add_column("Impact %", justify="right", style="red")
        table.add_column("Confidence", justify="right", style="magenta")
        table.add_column("Age", justify="right", style="dim")
        
        for opp in self.active_opportunities[:10]:  # Show top 10
            age = int(time.time() - opp.timestamp)
            age_str = f"{age}s" if age < 60 else f"{age//60}m"
            
            # Format token path with expanded token symbols
            token_symbols = {
                # Major tokens
                "So11111111111111111111111111111111111111112": "SOL",
                "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC",
                "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": "USDT",
                
                # Memecoins
                "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263": "BONK",
                "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm": "WIF",
                "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr": "POPCAT",
                "MEW1gQWJ3nEXg2qgERiKu7FAFj79PHvQVREQUzScPP5": "MEW",
                "2qEHjDLDLbuBgRYvsxhc5D6uDWAivNFZGan56P1tpump": "PNUT",
                "CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump": "GOAT",
                "ED5nyyWEzpPPiWimP8vYm7sD7TD3LAt3Q3gRTWHzPJBY": "MOODENG",
                
                # DeFi tokens
                "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN": "JUP",
                "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R": "RAY",
                "jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL": "JTO",
                "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3": "PYTH",
                "TNSRxcUxoT9xBG3de7PiJyTDYu7kskLqcpddxnEJAS6": "TNSR",
                
                # Liquid staking
                "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So": "mSOL",
                "7Q2afV64in6N6SeZsAAB81TJzwDoD6zpqmHkzi9Dcavn": "jSOL",
                "7dHbWXmci3dT8UFYWYZweBLXgycu7Y3iL6trKn1Y7ARj": "stSOL",
                
                # Wrapped assets
                "3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh": "WBTC",
                "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs": "WETH"
            }
            
            path_tokens = []
            for token in opp.token_path[:3]:  # Show first 3 tokens
                symbol = token_symbols.get(token, token[:4] + "..")
                path_tokens.append(symbol)
            path_str = " → ".join(path_tokens)
            if len(opp.token_path) > 3:
                path_str += " → ..."
            
            table.add_row(
                opp.pattern_type,
                ", ".join(opp.dexes[:2]),  # Show first 2 DEXes
                path_str,
                f"{opp.net_profit_sol:.5f}",
                f"${opp.net_profit_sol * self.sol_price:.2f}",
                f"{opp.price_impact:.2f}",
                f"{opp.confidence_score:.0%}",
                age_str
            )
        
        return Panel(table, title="[bold]Top Arbitrage Opportunities[/bold]", border_style="blue")
    
    def _generate_dex_status(self) -> Panel:
        """Generate DEX status panel"""
        dex_lines = []
        
        for dex_name in DEX_CONFIG.keys():
            pools = self.dex_pools.get(dex_name, [])
            pool_count = len(pools)
            total_liquidity = sum(p.liquidity_usd for p in pools)
            
            status = "🟢" if pool_count > 0 else "🔴"
            dex_lines.append(
                f"{status} [bold]{dex_name:12}[/bold] | Pools: {pool_count:3} | "
                f"Liquidity: ${total_liquidity:,.0f}"
            )
        
        return Panel(
            "\n".join(dex_lines),
            title="[bold]DEX Status[/bold]",
            border_style="yellow"
        )
    
    async def _cleanup_loop(self):
        """Clean up old opportunities periodically"""
        while self.is_running:
            # Remove opportunities older than 5 minutes
            cutoff_time = time.time() - 300
            self.opportunity_history = [
                opp for opp in self.opportunity_history 
                if opp.timestamp > cutoff_time
            ]
            await asyncio.sleep(60)  # Run every minute

async def main():
    """Main entry point"""
    config = Config()
    monitor = ArbitrageMonitor(config)
    
    try:
        await monitor.start_monitoring()
    except KeyboardInterrupt:
        console.print("\n[bold red]Monitor stopped by user[/bold red]")
    except Exception as e:
        console.print(f"\n[bold red]Error: {str(e)}[/bold red]")

if __name__ == "__main__":
    # Install rich if not available
    try:
        import rich
    except ImportError:
        console.print("[yellow]Installing required package: rich[/yellow]")
        os.system(f"{sys.executable} -m pip install rich")
        console.print("[green]Package installed, please run the script again[/green]")
        sys.exit(1)
    
    asyncio.run(main())
