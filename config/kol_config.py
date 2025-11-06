"""
Configuration for KOL tracking functionality
"""

# Known KOL wallets to track
KOL_WALLETS = {
    "SOL_Mate": "7eDiHXpGzwHJsN9EhwqXu6jxSEkM4Sw1c6oWi4rZXvEQ",
    "DeGod": "9CipFGrq3n8qh2GcqRA6hdxhFezQXg6c5sLnKxfhJXry",
    "Frank": "FrankV5s3cPwVF9LwYg2L1KCQgKuxThHYEhB8btGE9WtL",
    "Mango": "mangoSrm6T1RPefoYCfCAVZKKyW5YHwb4pdnuVK4G",
    # Add more KOL wallets here
}

# Minimum trade size to track (in USD)
MIN_TRADE_SIZE_USD = 1000

# Time window for correlation analysis (in seconds)
CORRELATION_WINDOW = 3600  # 1 hour

# Minimum correlation score for strong signal
MIN_CORRELATION_SCORE = 0.7

# Confidence score weights
WEIGHTS = {
    'trade_size': 0.4,
    'wallet_history': 0.2,
    'correlation': 0.4
}

# API Configuration
HELIUS_API_KEY = ""  # Add your Helius API key here
BIRDEYE_API_KEY = ""  # Add your Birdeye API key here

# Trading parameters
KOL_SENTIMENT_THRESHOLD = 0.7  # Minimum KOL sentiment score to influence trades
MAX_SENTIMENT_IMPACT = 0.3  # Maximum impact on trade size (30%)