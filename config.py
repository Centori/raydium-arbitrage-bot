from dataclasses import dataclass
import os
from dotenv import load_dotenv
import base64
from pathlib import Path

import os
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    # Load environment variables
    load_dotenv()
    
    # TVL and holding settings
    MIN_LIQUIDITY_TVL: float = float(os.getenv('MIN_LIQUIDITY_TVL', '70000'))  # $70k minimum TVL by default
    MAX_INSIDER_HOLDING_PCT: float = float(os.getenv('MAX_INSIDER_HOLDING_PCT', '15.0'))  # 15% maximum insider holding
    
    # Risk score settings
    MAX_RISK_SCORE: int = int(os.getenv('MAX_RISK_SCORE', '40'))  # Maximum acceptable risk score
    
    # Token filtering settings
    ACCEPT_ALL_TOKEN_PAIRS: bool = os.getenv('ACCEPT_ALL_TOKEN_PAIRS', 'false').lower() == 'true'
    
    # Helius API settings
    HELIUS_API_KEY: str = os.getenv('HELIUS_API_KEY', '')
    HELIUS_RPC_URL: str = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}" if HELIUS_API_KEY else ""
    
    # Alchemy API settings
    ALCHEMY_API_KEY: str = os.getenv('ALCHEMY_API_KEY', '')
    ALCHEMY_RPC_URL: str = f"https://solana-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}" if ALCHEMY_API_KEY else ""
    
    # Jito settings
    JITO_ENDPOINT: str = os.getenv('JITO_ENDPOINT', "https://mainnet.block-engine.jito.wtf")
    JITO_AUTH_KEYPAIR_BASE64: str = os.getenv('JITO_AUTH_KEYPAIR_BASE64', '')
    
    # API settings - UPDATED to use external APIs only
    USE_LOCAL_API_SERVER: bool = os.getenv('USE_LOCAL_API_SERVER', 'false').lower() == 'true'
    API_PORT: int = int(os.getenv('API_PORT', '3000'))
    API_HOST: str = os.getenv('API_HOST', 'localhost')

    # External API endpoints (used when USE_LOCAL_API_SERVER=false)
    # NOTE: Jupiter API v6 is at quote-api.jup.ag which requires specific routing
    # Using price API instead which is more stable
    JUPITER_API_URL: str = os.getenv('JUPITER_API_URL', 'https://price.jup.ag/v6')
    DEXSCREENER_API_URL: str = os.getenv('DEXSCREENER_API_URL', 'https://api.dexscreener.com/latest')
    
    # Other endpoints
    # RPC priority: 1. Explicitly set RPC_ENDPOINT, 2. Helius, 3. Alchemy, 4. Public endpoint
    RPC_ENDPOINT: str = os.getenv('RPC_ENDPOINT', 
                                  HELIUS_RPC_URL or 
                                  ALCHEMY_RPC_URL or 
                                  "https://api.mainnet-beta.solana.com")
    SEARCHER_ENDPOINT: str = JITO_ENDPOINT  # Use Jito for bundle submission
    RAYDIUM_API_ENDPOINT: str = os.getenv('RAYDIUM_API_ENDPOINT', "http://127.0.0.1:8545")
    
    # Trading settings - OPTIMIZED for 0.5 SOL balance
    SLIPPAGE_BPS: int = int(os.getenv('SLIPPAGE_BPS', '100'))  # 1% slippage (optimized)
    MIN_BUY_SOL: float = float(os.getenv('MIN_BUY_SOL', '0.05'))  # Reduced minimum to allow smaller trades
    MAX_BUY_SOL: float = float(os.getenv('MAX_BUY_SOL', '0.5'))  # Capped at 0.5 SOL (current balance)
    TRADE_AMOUNT_SOL: float = float(os.getenv('TRADE_AMOUNT_SOL', os.getenv('TRADE_AMOUNT', '0.02')))  # Default 0.02 SOL
    
    # Pool refresh settings
    POOL_CACHE_EXPIRY: int = int(os.getenv('POOL_CACHE_EXPIRY', '60'))  # 60s cache expiry
    FULL_REFRESH_INTERVAL: int = int(os.getenv('FULL_REFRESH_INTERVAL', '300'))  # 5min full refresh
    
    # Cross-DEX arbitrage settings
    ENABLE_CROSS_DEX: bool = os.getenv('ENABLE_CROSS_DEX', 'true').lower() == 'true'
    MIN_CROSS_DEX_DIFF_PCT: float = float(os.getenv('MIN_CROSS_DEX_DIFF_PCT', '0.5'))  # Min 0.5% diff for cross-DEX
    
    # Execution settings
    MIN_PROFIT_USD: float = float(os.getenv('MIN_PROFIT_USD', '0.5'))  # Reduced min profit to 0.5 USD
    GAS_COST_MULTIPLIER: float = float(os.getenv('GAS_COST_MULTIPLIER', '2.0'))  # 2x gas cost
    
    # Telegram settings
    TELEGRAM_BOT_TOKEN: str = os.getenv('TELEGRAM_BOT_TOKEN', 'disabled')
    TELEGRAM_CHAT_ID: str = os.getenv('TELEGRAM_CHAT_ID', 'disabled')
    TELEGRAM_NOTIFICATIONS_ENABLED: bool = (
        TELEGRAM_BOT_TOKEN != 'disabled' and 
        TELEGRAM_CHAT_ID != 'disabled' and
        os.getenv('DISABLE_NOTIFICATIONS', 'false').lower() != 'true'
    )
    
    def __init__(self):
        # Load RPC endpoint
        self.RPC_ENDPOINT = os.getenv('RPC_ENDPOINT', 'https://api.mainnet-beta.solana.com')
        
        # API Keys
        self.BIRDEYE_API_KEY = os.getenv('BIRDEYE_API_KEY')
        self.JUPITER_API_KEY = os.getenv('JUPITER_API_KEY')
        self.HELIUS_API_KEY = os.getenv('HELIUS_API_KEY')
        
        # Trading Settings
        self.TRADE_AMOUNT_SOL = float(os.getenv('TRADE_AMOUNT_SOL', '0.1'))
        self.SLIPPAGE_BPS = int(os.getenv('SLIPPAGE_BPS', '50'))
        self.MAX_PRIORITY_FEE = int(os.getenv('MAX_PRIORITY_FEE', '1000000'))
        
        # Elite Trader Settings
        self.MIN_WIN_RATE = float(os.getenv('MIN_WIN_RATE', '0.85'))
        self.MIN_RETURN_PCT = float(os.getenv('MIN_RETURN_PCT', '1000.0'))
        self.MIN_TRADES = int(os.getenv('MIN_TRADES', '50'))
        
        # Liquidity Thresholds
        self.MIN_LIQUIDITY_USD = int(os.getenv('MIN_LIQUIDITY_USD', '50000'))
        self.SIGNIFICANT_LIQUIDITY_USD = int(os.getenv('SIGNIFICANT_LIQUIDITY_USD', '250000'))
        self.MASSIVE_LIQUIDITY_USD = int(os.getenv('MASSIVE_LIQUIDITY_USD', '1000000'))
        # Check for required API keys
        if not self.RPC_ENDPOINT or "api-key=your-" in self.RPC_ENDPOINT.lower():
            raise ValueError("RPC_ENDPOINT not properly configured in .env file")
            
        # Log which RPC we're using
        if "helius" in self.RPC_ENDPOINT.lower():
            print(f"Using Helius RPC endpoint with API key: {self.HELIUS_API_KEY[:8]}...")
        elif "alchemy" in self.RPC_ENDPOINT.lower():
            print(f"Using Alchemy RPC endpoint with API key: {self.ALCHEMY_API_KEY[:8]}...")
        else:
            print(f"Using RPC endpoint: {self.RPC_ENDPOINT}")
        
        if not self.JITO_AUTH_KEYPAIR_BASE64:
            print("Warning: JITO_AUTH_KEYPAIR_BASE64 not configured in .env file. Bundle submission won't be available.")
            
        # Log special modes
        if self.ACCEPT_ALL_TOKEN_PAIRS:
            print("WARNING: ACCEPT_ALL_TOKEN_PAIRS=true - Bot will consider all token pairs regardless of risk")
            
        if self.MAX_RISK_SCORE > 40:
            print(f"WARNING: MAX_RISK_SCORE={self.MAX_RISK_SCORE} - Using higher than recommended risk threshold")

"""
Configuration for arbitrage pattern detection and replication
"""
# DEX configurations and priorities
DEX_CONFIG = {
    "Jupiter": {
        "program_ids": ["JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"],
        "priority": 1,  # Highest priority due to best routing
        "min_profit_threshold": 0.01,  # In SOL
    },
    "Raydium": {
        "program_ids": [
            "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",
            "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK"
        ],
        "priority": 2,
        "min_profit_threshold": 0.015,
    },
    "Orca": {
        "program_ids": ["whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"],
        "priority": 3,
        "min_profit_threshold": 0.012,
    },
    "Meteora": {
        "program_ids": [
            "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo",  # Meteora DLMM
            "Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB"   # Meteora Pools
        ],
        "priority": 4,
        "min_profit_threshold": 0.01,
    },
    "Phoenix": {
        "program_ids": ["PhoeNiXZ8ByJGLkxNfZRnkUfjvmuYqLR89jjFHGqdXY"],
        "priority": 5,
        "min_profit_threshold": 0.008,  # Lower threshold for newer DEX
    },
    "Lifinity": {
        "program_ids": ["EewxydAPCCVuNEyrVN68PuSYdQ7wKn27V9Gjeoi8dy3S"],
        "priority": 6,
        "min_profit_threshold": 0.01,
    },
    "FluxBeam": {
        "program_ids": ["FLUXubRmkEi2q6K3Y9kBPg9248ggaZVsoSFhtJHSrm1X"],
        "priority": 7,
        "min_profit_threshold": 0.008,
    },
    "GooseFX": {
        "program_ids": ["GFXsSL5sSaDfNFQUYsHekbWBW1TsFdjDYzACh62tEHxn"],
        "priority": 8,
        "min_profit_threshold": 0.01,
    },
    "Invariant": {
        "program_ids": ["HyaB3W9q6XdA5xwpU4XnSZV94htfmbmqJXZcEbRaJutt"],
        "priority": 9,
        "min_profit_threshold": 0.009,
    }
}

# Pattern-specific configurations - OPTIMIZED for 0.5 SOL balance with max 0.52% price impact
PATTERN_CONFIG = {
    "TRIANGULAR": {
        "min_profit_threshold": 0.015,  # Reduced from 0.02 to allow for smaller profitable trades
        "max_hops": 3,
        "required_liquidity_ratio": 0.15,  # Increased to 15% to ensure enough liquidity
        "max_price_impact": 0.0052,  # Maximum 0.52% price impact
    },
    "CROSS_DEX": {
        "min_profit_threshold": 0.01,  # Reduced from 0.015
        "max_dexes": 2,
        "required_liquidity_ratio": 0.1,  # Doubled from 0.05 to reduce price impact
        "max_price_impact": 0.0052,  # Maximum 0.52% price impact
    },
    "FLASH_LOAN": {
        "min_profit_threshold": 0.02,  # Reduced from 0.025
        "max_flash_loan_amount": 0.5,  # Reduced to match SOL balance
        "required_liquidity_ratio": 0.2,  # Increased from 0.15 for less price impact
        "max_price_impact": 0.0052,  # Maximum 0.52% price impact
    }
}

# Token pairs to monitor (ordered by priority)
MONITORED_PAIRS = [
    # === STABLECOINS & MAJOR PAIRS ===
    {
        "name": "SOL/USDC",
        "base": "So11111111111111111111111111111111111111112",
        "quote": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "min_price_impact": 0.0005,  # 0.05%
        "max_price_impact": 0.0052,  # 0.52% max price impact
        "max_position_size": 0.5,  # In SOL - adjusted to match balance
    },
    {
        "name": "SOL/USDT",
        "base": "So11111111111111111111111111111111111111112",
        "quote": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
        "min_price_impact": 0.0005,  # 0.05%
        "max_price_impact": 0.0052,  # 0.52% max price impact
        "max_position_size": 0.5,  # In SOL - adjusted to match balance
    },
    {
        "name": "USDC/USDT",
        "base": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "quote": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
        "min_price_impact": 0.0001,  # 0.01% - tighter for stablecoin pairs
        "max_price_impact": 0.002,   # 0.2% max
        "max_position_size": 1000,    # In USDC
    },
    
    # === TOP MEMECOINS ===
    {
        "name": "WIF/SOL",  # dogwifhat
        "base": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
        "quote": "So11111111111111111111111111111111111111112",
        "min_price_impact": 0.001,
        "max_price_impact": 0.01,
        "max_position_size": 0.3,
    },
    {
        "name": "BONK/SOL",
        "base": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
        "quote": "So11111111111111111111111111111111111111112",
        "min_price_impact": 0.001,
        "max_price_impact": 0.01,
        "max_position_size": 0.3,
    },
    {
        "name": "POPCAT/SOL",
        "base": "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr",
        "quote": "So11111111111111111111111111111111111111112",
        "min_price_impact": 0.001,
        "max_price_impact": 0.01,
        "max_position_size": 0.3,
    },
    {
        "name": "MEW/SOL",  # cat in a dogs world
        "base": "MEW1gQWJ3nEXg2qgERiKu7FAFj79PHvQVREQUzScPP5",
        "quote": "So11111111111111111111111111111111111111112",
        "min_price_impact": 0.001,
        "max_price_impact": 0.01,
        "max_position_size": 0.3,
    },
    {
        "name": "PNUT/SOL",  # Peanut the Squirrel
        "base": "2qEHjDLDLbuBgRYvsxhc5D6uDWAivNFZGan56P1tpump",
        "quote": "So11111111111111111111111111111111111111112",
        "min_price_impact": 0.001,
        "max_price_impact": 0.01,
        "max_position_size": 0.3,
    },
    {
        "name": "GOAT/SOL",  # Goatseus Maximus
        "base": "CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump",
        "quote": "So11111111111111111111111111111111111111112",
        "min_price_impact": 0.001,
        "max_price_impact": 0.01,
        "max_position_size": 0.3,
    },
    {
        "name": "MOODENG/SOL",  # Moo Deng
        "base": "ED5nyyWEzpPPiWimP8vYm7sD7TD3LAt3Q3gRTWHzPJBY",
        "quote": "So11111111111111111111111111111111111111112",
        "min_price_impact": 0.001,
        "max_price_impact": 0.01,
        "max_position_size": 0.3,
    },
    
    # === HIGH LIQUIDITY DEFI TOKENS ===
    {
        "name": "JUP/SOL",  # Jupiter
        "base": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
        "quote": "So11111111111111111111111111111111111111112",
        "min_price_impact": 0.0005,
        "max_price_impact": 0.005,
        "max_position_size": 0.4,
    },
    {
        "name": "RAY/SOL",  # Raydium
        "base": "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
        "quote": "So11111111111111111111111111111111111111112",
        "min_price_impact": 0.0005,
        "max_price_impact": 0.005,
        "max_position_size": 0.4,
    },
    {
        "name": "JTO/SOL",  # Jito
        "base": "jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL",
        "quote": "So11111111111111111111111111111111111111112",
        "min_price_impact": 0.0005,
        "max_price_impact": 0.005,
        "max_position_size": 0.4,
    },
    {
        "name": "PYTH/SOL",  # Pyth Network
        "base": "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3",
        "quote": "So11111111111111111111111111111111111111112",
        "min_price_impact": 0.0005,
        "max_price_impact": 0.005,
        "max_position_size": 0.4,
    },
    {
        "name": "TNSR/SOL",  # Tensor
        "base": "TNSRxcUxoT9xBG3de7PiJyTDYu7kskLqcpddxnEJAS6",
        "quote": "So11111111111111111111111111111111111111112",
        "min_price_impact": 0.0005,
        "max_price_impact": 0.005,
        "max_position_size": 0.4,
    },
    
    # === LIQUID STAKING TOKENS ===
    {
        "name": "MSOL/SOL",  # Marinade staked SOL
        "base": "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So",
        "quote": "So11111111111111111111111111111111111111112",
        "min_price_impact": 0.0002,
        "max_price_impact": 0.003,
        "max_position_size": 0.5,
    },
    {
        "name": "JSOL/SOL",  # JPool staked SOL
        "base": "7Q2afV64in6N6SeZsAAB81TJzwDoD6zpqmHkzi9Dcavn",
        "quote": "So11111111111111111111111111111111111111112",
        "min_price_impact": 0.0002,
        "max_price_impact": 0.003,
        "max_position_size": 0.5,
    },
    {
        "name": "STSOL/SOL",  # Lido staked SOL
        "base": "7dHbWXmci3dT8UFYWYZweBLXgycu7Y3iL6trKn1Y7ARj",
        "quote": "So11111111111111111111111111111111111111112",
        "min_price_impact": 0.0002,
        "max_price_impact": 0.003,
        "max_position_size": 0.5,
    },
    
    # === WRAPPED ASSETS ===
    {
        "name": "WBTC/SOL",  # Wrapped Bitcoin
        "base": "3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh",
        "quote": "So11111111111111111111111111111111111111112",
        "min_price_impact": 0.0005,
        "max_price_impact": 0.005,
        "max_position_size": 0.3,
    },
    {
        "name": "WETH/SOL",  # Wrapped Ethereum
        "base": "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs",
        "quote": "So11111111111111111111111111111111111111112",
        "min_price_impact": 0.0005,
        "max_price_impact": 0.005,
        "max_position_size": 0.3,
    },
]

# Jito block engine configuration - OPTIMIZED for efficient execution
JITO_CONFIG = {
    "min_tip_threshold": 0.005,  # Reduced from 0.01 to allow smaller tips
    "max_bundle_size": 3,  # Maximum transactions per bundle
    "execution_timeout": 2,  # In seconds
    "retry_count": 3,
    # New optimized parameters
    "max_tip_percentage": 70,  # Reduced from 80% to retain more profit
    "dynamic_tip_scaling": True,  # Enable dynamic tip scaling based on profit potential
    "tip_multiplier_base": 2.0,  # Reduced from 2.5 to save on fees
    "backoff_strategy": "exponential",  # Use exponential backoff for retries
    "max_sockets": 25,  # Maximum number of socket connections (improves throughput)
    "socket_timeout": 19000,  # Socket timeout in ms (one second less than Solana RPC's keepalive)
    "keepalive_enabled": True,  # Enable TCP keepalive
    "bundle_transaction_limit": 6,  # Maximum number of transactions in a bundle (Jito limit)
    "simulate_before_send": True,  # Always simulate bundles before sending
    "minimum_priority_fee": 0.000005,  # Minimum priority fee in SOL
    "rpc_timeout_ms": 30000,  # RPC timeout in milliseconds
    "dynamic_compute_unit_limit": True,  # Enable dynamic compute unit limit for efficiency
    "prioritization_fee_mode": "auto",  # Auto-adjust prioritization fees based on network congestion
}

# Risk management settings - OPTIMIZED for smaller balance
RISK_CONFIG = {
    "max_exposure_per_trade": 0.5,  # In SOL - limited to current balance
    "max_daily_exposure": 2.0,  # In SOL - limited to 4x current balance
    "max_loss_threshold": 0.03,  # Reduced to 3% maximum loss tolerance
    "min_success_rate": 0.85,  # Increased to 85% for better safety
    "cooldown_period": 180,  # Reduced to 3 minutes between failed attempts
    "max_price_impact": 0.0052,  # 0.52% maximum price impact
}

# Auto-tuning parameters
TUNING_CONFIG = {
    "sample_size": 100,  # Number of transactions to analyze
    "success_threshold": 0.7,  # 70% success rate to keep pattern
    "profit_weight": 0.6,
    "success_rate_weight": 0.4,
    "update_frequency": 3600,  # Update patterns every hour
    "optimize_for_price_impact": True,  # New parameter to focus on minimizing price impact
    "max_price_impact": 0.0052,  # 0.52% maximum price impact
}

# Backrun strategy configuration
BACKRUN_STRATEGY = {
    "ENABLE_BACKRUN_STRATEGY": True,
    "DEXES_TO_MONITOR": [
        "Raydium", "RaydiumCLMM", "Orca", "Jupiter",
        "Meteora", "Phoenix", "Lifinity", "FluxBeam", 
        "GooseFX", "Invariant"
    ],
    "MIN_PRICE_IMPACT_PCT": 0.1,  # Minimum price impact to consider backrunning
    "SLOT_MEMO": True,
    "BASE_MINTS": [
        {
            "MINT": "So11111111111111111111111111111111111111112",  # SOL
            "MIN_SIMULATED_PROFIT": 100000,  # 0.0001 SOL minimum profit
            "MIN_TRADE_SIZE": 100_000_000,    # 0.1 SOL minimum trade
            "MAX_TRADE_SIZE": 500_000_000,    # 0.5 SOL maximum trade
            "TRADE_CONFIGS": [
                {"MIN_TRADE_BP": 1000, "MAX_TRADE_BP": 2000}  # 10-20% of detected trade
            ]
        }
    ]
}

def update_pattern_config(new_patterns):
    """Update pattern configurations based on analysis"""
    global PATTERN_CONFIG
    
    for pattern, data in new_patterns.items():
        if pattern in PATTERN_CONFIG:
            # Update min profit threshold based on average profits
            if data.get("avg_profit"):
                PATTERN_CONFIG[pattern]["min_profit_threshold"] = max(
                    data["avg_profit"] * 0.8,  # 80% of average profit
                    PATTERN_CONFIG[pattern]["min_profit_threshold"]
                )
            
            # Ensure max price impact is never exceeded
            PATTERN_CONFIG[pattern]["max_price_impact"] = min(
                data.get("max_price_impact", 0.0052),
                PATTERN_CONFIG[pattern].get("max_price_impact", 0.0052)
            )
