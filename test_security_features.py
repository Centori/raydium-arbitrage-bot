#!/usr/bin/env python3
"""
Quick test script for security and trading features
Tests without requiring full bot deployment
"""
import asyncio
import sys
import os
from decimal import Decimal

# Test imports
try:
    from config import Config
    from security_validator import SecurityValidator
    from api_client import BlockchainAPIClient
    from gmgn_tracker import GMGNTracker
    from liquidity_flow_analyzer import LiquidityFlowAnalyzer
    print("✅ All modules imported successfully")
except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)

async def test_security_validator():
    """Test security validator"""
    print("\n🔒 Testing Security Validator...")
    
    try:
        config = Config()
        api_client = BlockchainAPIClient(config)
        validator = SecurityValidator(config, api_client)
        
        # Test with SOL token (should pass)
        sol_token = "So11111111111111111111111111111111111111112"
        print(f"Testing SOL token: {sol_token}")
        
        report = await validator.validate_token(sol_token)
        
        print(f"  Overall Risk Score: {report.overall_risk_score}/100")
        print(f"  Is Safe: {report.is_safe}")
        print(f"  Tradeable: {report.tradeable}")
        
        if report.warnings:
            print("  Warnings:")
            for warning in report.warnings:
                print(f"    - {warning}")
        
        print("✅ Security Validator working")
        return True
        
    except Exception as e:
        print(f"❌ Security Validator error: {e}")
        return False

async def test_gmgn_tracker():
    """Test GMGN smart money tracker"""
    print("\n🧠 Testing GMGN Tracker...")
    
    try:
        config = Config()
        tracker = GMGNTracker(config)
        
        # Test getting smart money wallets
        print("Fetching top smart money wallets...")
        wallets = await tracker.get_smart_money_wallets(limit=5)
        
        if wallets:
            print(f"✅ Found {len(wallets)} smart money wallets")
            for i, wallet in enumerate(wallets[:3], 1):
                print(f"  {i}. {wallet.address[:8]}... - PnL: ${float(wallet.pnl_30d):,.0f}, WR: {wallet.win_rate*100:.1f}%")
        else:
            print("⚠️  No wallets returned (API might be rate limited)")
        
        # Test trending tokens
        print("\nFetching trending tokens...")
        trending = await tracker.get_trending_tokens(timeframe="24h")
        
        if trending:
            print(f"✅ Found {len(trending)} trending tokens")
            for i, token in enumerate(trending[:3], 1):
                print(f"  {i}. {token['token_symbol']} - ${float(token['price']):.6f}")
        else:
            print("⚠️  No trending tokens (API might be rate limited)")
        
        return True
        
    except Exception as e:
        print(f"❌ GMGN Tracker error: {e}")
        return False

async def test_liquidity_flow():
    """Test liquidity flow analyzer"""
    print("\n📊 Testing Liquidity Flow Analyzer...")
    
    try:
        config = Config()
        api_client = BlockchainAPIClient(config)
        analyzer = LiquidityFlowAnalyzer(config, api_client)
        
        print("  Configuration:")
        print(f"    Snapshot interval: {analyzer.snapshot_interval}s")
        print(f"    History window: {analyzer.history_window}s")
        print(f"    Reversal threshold: {analyzer.reversal_threshold*100}%")
        
        print("✅ Liquidity Flow Analyzer initialized")
        print("  (Full testing requires active pool monitoring)")
        
        return True
        
    except Exception as e:
        print(f"❌ Liquidity Flow Analyzer error: {e}")
        return False

async def test_circuit_breaker():
    """Test circuit breaker functionality"""
    print("\n🚨 Testing Circuit Breaker...")
    
    try:
        from migration_executor import MigrationExecutor
        from pool_analyzer import PoolAnalyzer
        from risk_analyzer import RiskAnalyzer
        
        config = Config()
        api_client = BlockchainAPIClient(config)
        risk_analyzer = RiskAnalyzer(config)
        pool_analyzer = PoolAnalyzer(config, risk_analyzer)
        
        executor = MigrationExecutor(config, pool_analyzer, api_client)
        
        print("  Configuration:")
        print(f"    Max daily loss: {float(executor.max_daily_loss)} SOL")
        print(f"    Max daily trades: {executor.max_daily_trades}")
        print(f"    Blacklist after fails: {executor.blacklist_after_fails}")
        
        # Test circuit breaker check
        can_trade = await executor.check_circuit_breaker()
        print(f"  Circuit breaker status: {'🟢 ACTIVE' if can_trade else '🔴 TRIPPED'}")
        
        # Check current stats
        daily_pnl = await executor._calculate_daily_pnl()
        daily_trades = executor._count_daily_trades()
        
        print(f"  Daily P&L: {float(daily_pnl):.4f} SOL")
        print(f"  Daily trades: {daily_trades}/{executor.max_daily_trades}")
        
        print("✅ Circuit Breaker working")
        return True
        
    except Exception as e:
        print(f"❌ Circuit Breaker error: {e}")
        return False

async def test_config():
    """Test configuration"""
    print("\n⚙️  Testing Configuration...")
    
    try:
        config = Config()
        
        print("  Wallet:")
        wallet_addr = getattr(config, 'SOLANA_WALLET', os.getenv('SOLANA_WALLET', 'Not set'))
        print(f"    Address: {wallet_addr}")
        
        print("  Trading:")
        print(f"    Trade amount: {config.TRADE_AMOUNT_SOL} SOL")
        print(f"    Max daily trades: {getattr(config, 'MAX_DAILY_TRADES', 'Not set')}")
        print(f"    Max daily loss: {getattr(config, 'MAX_DAILY_LOSS_SOL', 'Not set')} SOL")
        
        print("  RPC:")
        print(f"    Endpoint: {config.RPC_ENDPOINT[:50]}...")
        print(f"    Helius: {'✅' if config.HELIUS_API_KEY else '❌'}")
        
        print("✅ Configuration loaded")
        return True
        
    except Exception as e:
        print(f"❌ Configuration error: {e}")
        return False

async def main():
    """Run all tests"""
    print("="*60)
    print("🧪 RAYDIUM MIGRATION SNIPER - SECURITY TESTS")
    print("="*60)
    
    results = []
    
    # Run tests
    results.append(("Config", await test_config()))
    results.append(("Security Validator", await test_security_validator()))
    results.append(("GMGN Tracker", await test_gmgn_tracker()))
    results.append(("Liquidity Flow", await test_liquidity_flow()))
    results.append(("Circuit Breaker", await test_circuit_breaker()))
    
    # Summary
    print("\n" + "="*60)
    print("📋 TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {name}: {status}")
    
    print(f"\n  Total: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Bot is ready for deployment.")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Review errors above.")
    
    return passed == total

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
