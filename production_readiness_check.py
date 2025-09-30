#!/usr/bin/env python3
"""
Production Readiness Check for Raydium Arbitrage Bot
Validates wallet access, API connections, and Telegram monitoring
"""
import os
import json
import asyncio
import logging
import base58
from dotenv import load_dotenv
from solders.keypair import Keypair
from solana.rpc.async_api import AsyncClient
from solana.rpc.api import Client
import aiohttp
import requests

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ProductionReadinessChecker:
    def __init__(self):
        load_dotenv()
        self.issues = []
        self.warnings = []
        self.success = []
        
    def log_issue(self, message):
        self.issues.append(message)
        logger.error(f"❌ {message}")
        
    def log_warning(self, message):
        self.warnings.append(message)
        logger.warning(f"⚠️ {message}")
        
    def log_success(self, message):
        self.success.append(message)
        logger.info(f"✅ {message}")

    def check_wallet_access(self):
        """Test wallet loading and access"""
        logger.info("🔐 Checking wallet access...")
        
        # Check for private key in .env
        private_key = os.getenv('SOLANA_PRIVATE_KEY')
        if not private_key:
            self.log_issue("SOLANA_PRIVATE_KEY not found in .env file")
            return False
            
        # Check for wallet keypair file
        wallet_path = os.getenv('WALLET_KEYPAIR_PATH', './keys/wallet-keypair.json')
        if not os.path.exists(wallet_path):
            self.log_warning(f"Wallet keypair file not found at {wallet_path}")
        else:
            self.log_success(f"Wallet keypair file found at {wallet_path}")
            
            # Try to load from JSON file
            try:
                with open(wallet_path, 'r') as f:
                    keypair_data = json.load(f)
                    if isinstance(keypair_data, list) and len(keypair_data) == 64:
                        keypair = Keypair.from_bytes(bytes(keypair_data))
                        self.log_success(f"Wallet loaded from file: {keypair.pubkey()}")
                        return True
                    else:
                        self.log_issue("Invalid wallet keypair format in JSON file")
            except Exception as e:
                self.log_issue(f"Error loading wallet from file: {str(e)}")
                
        # Try loading from environment variable
        try:
            # Try base58 format first
            try:
                private_key_bytes = base58.b58decode(private_key)
                if len(private_key_bytes) == 32:
                    # This is a seed, need to derive the full keypair
                    self.log_warning("Private key appears to be a seed (32 bytes), not full keypair")
                    return False
                elif len(private_key_bytes) == 64:
                    keypair = Keypair.from_bytes(private_key_bytes)
                    self.log_success(f"Wallet loaded from env (base58): {keypair.pubkey()}")
                    return True
            except Exception as e:
                self.log_warning(f"Base58 decode failed: {str(e)}")
                
            self.log_issue("Unable to load wallet keypair from any source")
            return False
            
        except Exception as e:
            self.log_issue(f"Error checking wallet: {str(e)}")
            return False

    async def check_rpc_connection(self):
        """Test RPC endpoint connectivity"""
        logger.info("🌐 Checking RPC connections...")
        
        rpc_endpoint = os.getenv('RPC_ENDPOINT')
        if not rpc_endpoint:
            self.log_issue("RPC_ENDPOINT not configured")
            return False
            
        try:
            client = AsyncClient(rpc_endpoint)
            
            # Test getting recent blockhash (this is a good connectivity test)
            try:
                recent_blockhash = await client.get_latest_blockhash()
                if recent_blockhash.value:
                    self.log_success(f"RPC endpoint working: {rpc_endpoint}")
                    self.log_success("RPC can fetch recent blockhash")
                else:
                    self.log_warning("RPC failed to fetch recent blockhash")
            except Exception as e:
                self.log_issue(f"RPC blockhash test failed: {str(e)}")
                await client.close()
                return False
                
            # Test getting slot (another connectivity test)
            try:
                slot = await client.get_slot()
                if slot.value and slot.value > 0:
                    self.log_success(f"RPC slot check passed: {slot.value}")
                else:
                    self.log_warning("RPC slot check returned invalid value")
            except Exception as e:
                self.log_warning(f"RPC slot test failed: {str(e)}")
                
            await client.close()
            return True
            
        except Exception as e:
            self.log_issue(f"RPC connection failed: {str(e)}")
            return False

    async def check_wallet_balance(self):
        """Check wallet balance on mainnet"""
        logger.info("💰 Checking wallet balance...")
        
        # Load wallet first
        wallet_path = os.getenv('WALLET_KEYPAIR_PATH', './keys/wallet-keypair.json')
        if not os.path.exists(wallet_path):
            self.log_issue("Cannot check balance - wallet file not found")
            return False
            
        try:
            with open(wallet_path, 'r') as f:
                keypair_data = json.load(f)
                keypair = Keypair.from_bytes(bytes(keypair_data))
                
            rpc_endpoint = os.getenv('RPC_ENDPOINT')
            client = AsyncClient(rpc_endpoint)
            
            balance_response = await client.get_balance(keypair.pubkey())
            balance_lamports = balance_response.value
            balance_sol = balance_lamports / 1e9
            
            if balance_sol > 0:
                self.log_success(f"Wallet balance: {balance_sol:.6f} SOL")
                if balance_sol < 0.01:
                    self.log_warning(f"Low balance: {balance_sol:.6f} SOL - consider adding more funds")
                elif balance_sol < 0.1:
                    self.log_warning(f"Moderate balance: {balance_sol:.6f} SOL - good for testing")
                else:
                    self.log_success(f"Good balance: {balance_sol:.6f} SOL - ready for production")
            else:
                self.log_issue("Wallet has zero balance - add SOL before running bot")
                
            await client.close()
            return True
            
        except Exception as e:
            self.log_issue(f"Error checking wallet balance: {str(e)}")
            return False

    def check_telegram_config(self):
        """Test Telegram bot configuration"""
        logger.info("📱 Checking Telegram configuration...")
        
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        chat_id = os.getenv('TELEGRAM_CHAT_ID')
        
        if not bot_token or bot_token == 'disabled':
            self.log_warning("Telegram bot token not configured - notifications will be disabled")
            return False
            
        if not chat_id or chat_id == 'disabled':
            self.log_warning("Telegram chat ID not configured - notifications will be disabled")
            return False
            
        # Test sending a message
        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            data = {
                "chat_id": chat_id,
                "text": "🤖 Production readiness check - Telegram notifications working!",
                "parse_mode": "Markdown"
            }
            
            response = requests.post(url, data=data, timeout=10)
            
            if response.status_code == 200:
                self.log_success("Telegram notifications working correctly")
                return True
            else:
                self.log_issue(f"Telegram test failed: {response.text}")
                return False
                
        except Exception as e:
            self.log_issue(f"Telegram test error: {str(e)}")
            return False

    async def check_api_endpoints(self):
        """Test external API endpoints"""
        logger.info("🔗 Checking API endpoints...")
        
        # Test Jupiter API
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://quote-api.jup.ag/v6/tokens") as response:
                    if response.status == 200:
                        self.log_success("Jupiter API accessible")
                    else:
                        self.log_warning(f"Jupiter API returned status {response.status}")
        except Exception as e:
            self.log_warning(f"Jupiter API test failed: {str(e)}")
            
        # Test Raydium API
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://api.raydium.io/v2/main/pairs") as response:
                    if response.status == 200:
                        self.log_success("Raydium API accessible")
                    else:
                        self.log_warning(f"Raydium API returned status {response.status}")
        except Exception as e:
            self.log_warning(f"Raydium API test failed: {str(e)}")

    def check_jito_config(self):
        """Check Jito configuration"""
        logger.info("⚡ Checking Jito configuration...")
        
        jito_auth = os.getenv('JITO_AUTH_KEYPAIR_BASE64')
        if not jito_auth:
            self.log_warning("JITO_AUTH_KEYPAIR_BASE64 not configured - bundle execution will be disabled")
            return False
            
        jito_endpoint = os.getenv('JITO_ENDPOINT')
        if not jito_endpoint:
            self.log_warning("JITO_ENDPOINT not configured")
            return False
            
        self.log_success(f"Jito configured with endpoint: {jito_endpoint}")
        return True

    def check_configuration_values(self):
        """Check key configuration values"""
        logger.info("⚙️ Checking configuration values...")
        
        # Check critical settings
        min_profit = os.getenv('MIN_PROFIT_USD', '0.5')
        max_buy_sol = os.getenv('MAX_BUY_SOL', '0.5')
        min_liquidity = os.getenv('MIN_LIQUIDITY_TVL', '70000')
        
        try:
            min_profit_val = float(min_profit)
            max_buy_sol_val = float(max_buy_sol)
            min_liquidity_val = float(min_liquidity)
            
            self.log_success(f"Configuration loaded - Min profit: ${min_profit_val}, Max trade: {max_buy_sol_val} SOL, Min liquidity: ${min_liquidity_val:,.0f}")
            
            if min_profit_val < 0.1:
                self.log_warning(f"Very low minimum profit threshold: ${min_profit_val}")
            if max_buy_sol_val > 1.0:
                self.log_warning(f"High maximum trade size: {max_buy_sol_val} SOL")
                
        except Exception as e:
            self.log_issue(f"Invalid configuration values: {str(e)}")

    async def run_full_check(self):
        """Run all production readiness checks"""
        logger.info("🚀 Starting Production Readiness Check...")
        logger.info("=" * 60)
        
        # Run all checks
        self.check_wallet_access()
        await self.check_rpc_connection()
        await self.check_wallet_balance()
        self.check_telegram_config()
        await self.check_api_endpoints()
        self.check_jito_config()
        self.check_configuration_values()
        
        # Summary
        logger.info("=" * 60)
        logger.info("📊 PRODUCTION READINESS SUMMARY")
        logger.info("=" * 60)
        
        logger.info(f"✅ {len(self.success)} checks passed")
        logger.info(f"⚠️ {len(self.warnings)} warnings")
        logger.info(f"❌ {len(self.issues)} critical issues")
        
        if self.issues:
            logger.error("\n🔥 CRITICAL ISSUES TO FIX:")
            for issue in self.issues:
                logger.error(f"  • {issue}")
                
        if self.warnings:
            logger.warning("\n⚠️ WARNINGS TO CONSIDER:")
            for warning in self.warnings:
                logger.warning(f"  • {warning}")
                
        # Production readiness verdict
        if not self.issues:
            if not self.warnings:
                logger.info("\n🎉 PRODUCTION READY - All systems go!")
                return "READY"
            else:
                logger.info("\n🟡 PRODUCTION READY WITH WARNINGS - Consider addressing warnings")
                return "READY_WITH_WARNINGS"
        else:
            logger.error("\n🛑 NOT PRODUCTION READY - Fix critical issues first")
            return "NOT_READY"

async def main():
    checker = ProductionReadinessChecker()
    result = await checker.run_full_check()
    
    # Provide next steps
    print("\n" + "=" * 60)
    print("📋 NEXT STEPS FOR PRODUCTION:")
    print("=" * 60)
    
    if result == "READY":
        print("1. ✅ Start the bot: python main.py")
        print("2. ✅ Monitor Telegram for notifications")
        print("3. ✅ Check logs regularly for performance")
        print("4. ✅ Monitor wallet balance")
        
    elif result == "READY_WITH_WARNINGS":
        print("1. 🟡 Consider addressing warnings above")
        print("2. ✅ Start the bot: python main.py")
        print("3. ✅ Monitor Telegram for notifications")
        print("4. ✅ Check logs regularly for performance")
        
    else:
        print("1. ❌ Fix critical issues listed above")
        print("2. ❌ Re-run this check: python production_readiness_check.py")
        print("3. ❌ Do not start the bot until all issues are resolved")

if __name__ == "__main__":
    asyncio.run(main())
