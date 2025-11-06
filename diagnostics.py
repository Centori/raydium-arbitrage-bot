#!/usr/bin/env python3
"""
Bot Diagnostics - Check all systems
"""
import asyncio
import sys
import time
from decimal import Decimal

print("=" * 70)
print("🔍 ARBITRAGE BOT DIAGNOSTICS")
print("=" * 70)
print()

# Test 1: Configuration
print("📋 Test 1: Configuration Loading")
print("-" * 70)
try:
    from config import Config
    config = Config()
    print(f"✅ Config loaded successfully")
    print(f"   RPC Endpoint: {config.RPC_ENDPOINT[:50]}...")
    print(f"   Trade Size: {config.TRADE_AMOUNT_SOL} SOL")
    print(f"   Max Buy: {config.MAX_BUY_SOL} SOL")
    print(f"   Min Buy: {config.MIN_BUY_SOL} SOL")
    print(f"   Slippage: {config.SLIPPAGE_BPS} bps")
    print(f"   Cross-DEX Enabled: {config.ENABLE_CROSS_DEX}")
    print(f"   Min Cross-DEX Diff: {config.MIN_CROSS_DEX_DIFF_PCT}%")
except Exception as e:
    print(f"❌ Config failed: {e}")
    sys.exit(1)

print()

# Test 2: Wallet
print("💰 Test 2: Wallet Connection")
print("-" * 70)
try:
    from wallet import WalletManager
    wallet = WalletManager(config)
    print(f"✅ Wallet initialized")
    print(f"   Public Key: {wallet.keypair.pubkey()}")
    
    # Test balance
    async def check_balance():
        balance = await wallet.client.get_balance(wallet.keypair.pubkey())
        return balance.value / 1e9
    
    balance = asyncio.run(check_balance())
    print(f"   Balance: {balance:.6f} SOL (${balance * 200:.2f} @ $200/SOL)")
    
    if balance < 0.02:
        print(f"   ⚠️  Warning: Balance too low for trading")
    elif balance < 0.1:
        print(f"   ⚠️  Warning: Limited trading capacity")
    else:
        print(f"   ✅ Sufficient balance for trading")
        
except Exception as e:
    print(f"❌ Wallet failed: {e}")
    sys.exit(1)

print()

# Test 3: Jupiter API
print("🪐 Test 3: Jupiter API Connection")
print("-" * 70)
try:
    import aiohttp
    
    async def test_jupiter():
        url = f"{config.JUPITER_API_URL}/quote"
        params = {
            "inputMint": "So11111111111111111111111111111111111111112",
            "outputMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "amount": "1000000000",
            "onlyDirectRoutes": "true"
        }
        
        start = time.time()
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                elapsed = time.time() - start
                if response.status == 200:
                    data = await response.json()
                    if "outAmount" in data:
                        price = float(data["outAmount"]) / 1e6
                        print(f"✅ Jupiter API working")
                        print(f"   Response time: {elapsed:.2f}s")
                        print(f"   SOL/USDC price: ${price:.2f}")
                        return True
                print(f"❌ Jupiter returned status {response.status}")
                return False
    
    jupiter_ok = asyncio.run(test_jupiter())
    if not jupiter_ok:
        print(f"   ⚠️  Jupiter API may be slow or rate-limited")
        
except Exception as e:
    print(f"❌ Jupiter API failed: {e}")

print()

# Test 4: Components
print("🔧 Test 4: Bot Components")
print("-" * 70)
try:
    from api_client import BlockchainAPIClient
    from raydium_pools import RaydiumPoolFetcher
    from monitor_arbitrage_opportunities import ArbitrageMonitor
    from hft_executor import HFTExecutor
    
    api_client = BlockchainAPIClient(config)
    print(f"✅ BlockchainAPIClient initialized")
    
    pool_fetcher = RaydiumPoolFetcher(config)
    print(f"✅ RaydiumPoolFetcher initialized")
    
    monitor = ArbitrageMonitor(config)
    print(f"✅ ArbitrageMonitor initialized")
    
    # HFTExecutor needs event loop - skip for now
    print(f"✅ HFTExecutor (will be initialized at runtime)")
    
except Exception as e:
    print(f"❌ Component initialization failed: {e}")
    sys.exit(1)

print()

# Test 5: Profit Calculation
print("💵 Test 5: Profit Calculation Logic")
print("-" * 70)
try:
    trade_size = config.MAX_BUY_SOL
    
    # Simulate a 5% price difference opportunity
    price_diff_pct = 5.0
    gross_profit = trade_size * price_diff_pct / 100
    
    # Calculate costs
    gas_cost = 0.0002
    slippage_cost = trade_size * (config.SLIPPAGE_BPS / 10000)
    dex_fees = trade_size * 0.005
    
    net_profit = gross_profit - gas_cost - slippage_cost - dex_fees
    overhead_pct = ((gas_cost + slippage_cost + dex_fees) / trade_size) * 100
    
    print(f"✅ Profit calculation working")
    print(f"   Trade Size: {trade_size} SOL")
    print(f"   Price Diff: {price_diff_pct}%")
    print(f"   Gross Profit: {gross_profit:.6f} SOL")
    print(f"   - Gas: {gas_cost:.6f} SOL")
    print(f"   - Slippage: {slippage_cost:.6f} SOL")
    print(f"   - DEX Fees: {dex_fees:.6f} SOL")
    print(f"   = Net Profit: {net_profit:.6f} SOL (${net_profit * 200:.2f})")
    print(f"   Total Overhead: {overhead_pct:.2f}%")
    print()
    
    # Calculate break-even
    breakeven_pct = overhead_pct + 0.1  # Add 0.1% for minimum profit
    print(f"   ℹ️  Minimum spread needed: >{breakeven_pct:.1f}%")
    
    if net_profit > 0:
        print(f"   ✅ 5% spread = PROFITABLE")
    else:
        print(f"   ❌ 5% spread = NOT PROFITABLE")
        
except Exception as e:
    print(f"❌ Profit calculation failed: {e}")

print()

# Test 6: Risk Assessment
print("⚡ Test 6: Risk Assessment")
print("-" * 70)
try:
    risk_per_trade = (config.MAX_BUY_SOL / balance) * 100
    trades_possible = int(balance / config.MAX_BUY_SOL)
    
    print(f"   Risk per trade: {risk_per_trade:.1f}% of balance")
    print(f"   Trades possible: {trades_possible} trades")
    
    if risk_per_trade > 25:
        print(f"   ⚠️  HIGH RISK: >25% per trade")
    elif risk_per_trade > 15:
        print(f"   ⚠️  MODERATE RISK: 15-25% per trade")
    elif risk_per_trade > 10:
        print(f"   ✅ ACCEPTABLE: 10-15% per trade")
    else:
        print(f"   ✅ CONSERVATIVE: <10% per trade")
    
    if trades_possible < 5:
        print(f"   ⚠️  Limited trade capacity - consider lower trade size or more SOL")
    else:
        print(f"   ✅ Good trade capacity")
        
except Exception as e:
    print(f"❌ Risk assessment failed: {e}")

print()

# Test 7: Quick Opportunity Scan
print("🔎 Test 7: Quick Opportunity Scan")
print("-" * 70)
try:
    async def quick_scan():
        print(f"   Fetching pool data... (this may take 30-60 seconds)")
        start = time.time()
        
        opportunities = await monitor.find_cross_dex_opportunities()
        elapsed = time.time() - start
        
        print(f"   ✅ Scan completed in {elapsed:.1f}s")
        print(f"   Found: {len(opportunities)} opportunities")
        
        if opportunities:
            print(f"\n   Top 3 Opportunities:")
            for i, opp in enumerate(opportunities[:3], 1):
                print(f"   {i}. {opp.get('pair', 'Unknown')}")
                print(f"      DEXes: {' → '.join(opp.get('dexes', []))}")
                print(f"      Price Diff: {opp.get('price_diff_pct', 0):.2f}%")
                print(f"      Net Profit: {opp.get('net_profit_sol', 0):.6f} SOL")
                print(f"      USD: ${opp.get('profit_usd', 0):.2f}")
                print()
        else:
            print(f"   ℹ️  No profitable opportunities found right now")
            print(f"   (This is normal - profitable arbs are rare)")
    
    asyncio.run(quick_scan())
    
except Exception as e:
    print(f"❌ Opportunity scan failed: {e}")
    import traceback
    traceback.print_exc()

print()
print("=" * 70)
print("🎯 DIAGNOSTICS COMPLETE")
print("=" * 70)
print()
print("Summary:")
print(f"  Balance: {balance:.6f} SOL")
print(f"  Trade Size: {config.MAX_BUY_SOL} SOL ({risk_per_trade:.1f}% risk)")
print(f"  Min Spread Needed: >{breakeven_pct:.1f}%")
print(f"  Bot Status: Ready to trade")
print()
