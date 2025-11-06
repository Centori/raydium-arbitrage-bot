# KOL Sniper Bot - Production Ready

## Overview

Fully automated Solana token sniping engine that follows top KOL (Key Opinion Leader) wallets and executes trades based on liquidity momentum, pattern analysis, and safety checks.

## Features

### ✅ Multi-Token Async Monitoring
- Monitor multiple tokens simultaneously
- Non-blocking async architecture
- Real-time data updates every 2 seconds

### ✅ Pre-Entry Validation
- **Safety Checks**: LP burned/locked, honeypot detection, mintable check, freeze authority
- **Liquidity Momentum**: Track 50%+ liquidity acceleration 
- **Pattern Detection**: FOMO and pump pattern identification
- **KOL Confirmation**: Verify top KOL wallet holdings
- **Volume Ratio**: Require 3x+ volume-to-liquidity ratio

### ✅ Dynamic Position Sizing
- Max 10% of balance per trade
- Max 2% of token liquidity pool
- Automatic slippage buffer (2%)
- Respects configured MAX_BUY_SOL limit

### ✅ Jito Bundle Execution
- MEV-protected trade execution
- Front-running resistance
- Priority transaction processing

### ✅ Stop-Loss / Take-Profit
- Automatic 8% stop-loss
- Automatic 25% take-profit
- Real-time position monitoring
- Telegram notifications on close

### ✅ KOL Tracking
- Fetches top 50 performing wallets from GMGN.ai
- Tracks profit %, win rate, trade volume
- Requires min 60% win rate, 10+ trades
- Composite KOL scoring system

### ✅ Logging & Notifications
- Comprehensive file and console logging
- Telegram alerts for trades, positions, P&L
- Performance metrics tracking

## Files

```
kol_sniper_helpers.py   # Analysis classes (LiquidityMomentum, PatternAnalyzer, KOLTracker)
kol_sniper.py           # Main bot engine with GMGN/Jupiter integration
run_kol_sniper.py       # Runner script
```

## Configuration

Add to your `.env` file:

```bash
# Required
SOLANA_PRIVATE_KEY=your_private_key_here
RPC_ENDPOINT=https://api.mainnet-beta.solana.com

# Telegram (optional)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
TELEGRAM_NOTIFICATIONS_ENABLED=true

# Trading limits
MAX_BUY_SOL=0.08  # Maximum per trade
```

## Usage

### Quick Start

```bash
# Install dependencies (if needed)
pip3 install --break-system-packages aiohttp solana solders requests

# Run the bot
python3 run_kol_sniper.py
```

### Token Selection

Edit `run_kol_sniper.py` to customize which tokens to monitor:

```python
def get_trending_tokens() -> List[str]:
    return [
        "TokenAddress1...",
        "TokenAddress2...",
        # Add more addresses
    ]
```

### Advanced: Auto-Discovery

For production, integrate GMGN.ai trending token discovery:

```python
async def get_trending_tokens() -> List[str]:
    async with aiohttp.ClientSession() as session:
        url = "https://gmgn.ai/defi/quotation/v1/tokens/sol/new?limit=20"
        async with session.get(url) as resp:
            data = await resp.json()
            return [token['address'] for token in data['data']]
```

## Risk Management

### Position Sizing
- **Max per trade**: 10% of wallet balance OR 2% of pool liquidity (whichever is smaller)
- **Slippage buffer**: 2% automatically applied
- **Respects config limits**: Won't exceed `MAX_BUY_SOL`

### Stop-Loss / Take-Profit
- **Stop-loss**: -8% from entry price
- **Take-profit**: +25% from entry price
- Can be customized in `RiskManager` class

### Safety Checks (All must pass)
1. ✅ LP burned or locked
2. ✅ Not a honeypot
3. ✅ Not mintable
4. ✅ No freeze authority
5. ✅ Liquidity > $50k
6. ✅ Liquidity accelerating 50%+
7. ✅ FOMO or pump pattern detected
8. ✅ Top KOL in token
9. ✅ Volume ratio > 3.0x

## API Integrations

### GMGN.ai
- **Token Info**: `https://gmgn.ai/defi/quotation/v1/tokens/sol/{address}`
- **KOL Wallets**: `https://gmgn.ai/defi/quotation/v1/rank/sol/swaps/1h`
- **Rate Limits**: Respects API limits with delays

### Jupiter
- **Price Data**: `https://price.jup.ag/v4/price?ids={address}`
- **Used for**: Real-time price monitoring for P&L tracking

### Jito
- **Bundle Execution**: Via `JitoExecutor` class
- **Benefits**: MEV protection, priority execution

## Monitoring

### Logs
- **File**: `logs/kol_sniper.log`
- **Console**: Real-time output
- **Includes**: All decisions, API calls, trades, P&L

### Telegram Alerts
- Bot startup confirmation
- Trade execution notifications
- Position close alerts (with P&L)
- Session summary

## Example Session

```
🎯 KOL Sniper Bot Started
💰 Wallet: DLuX...
🔍 Monitoring Mode: Active

👀 Monitoring token: So111111...
✅ All pre-entry confirmations passed!
💎 Executing Jito bundle with 0.0392 SOL
✅ Jito bundle executed successfully

📊 Monitoring position for So111111...
🏆 Take-profit triggered: +28.5%
🔚 Position Closed - Take-Profit
   P&L: +28.5% (+0.0112 SOL)
```

## Performance Tuning

### Adjust Thresholds
In `kol_sniper_helpers.py`:
- Liquidity momentum threshold (default 50%)
- FOMO pattern sensitivity (price change, volume spike)
- KOL requirements (min trades, win rate)

### Optimize Monitoring
In `kol_sniper.py`:
- Check interval (default 2 seconds)
- Max monitoring duration (default 5 minutes)
- Position check frequency (default 3 seconds)

## Production Deployment

### VM Deployment
```bash
# Clone to VM
git clone your-repo
cd raydium-arbitrage-bot

# Install dependencies
pip3 install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your keys

# Run with nohup
nohup python3 run_kol_sniper.py > logs/sniper_output.log 2>&1 &
```

### Docker (Optional)
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python3", "run_kol_sniper.py"]
```

## Safety & Testing

### Test with Small Amounts
1. Set `MAX_BUY_SOL=0.001` for testing
2. Monitor 1-2 stable tokens first
3. Verify Telegram notifications work
4. Check P&L calculations

### Never Trade More Than You Can Lose
- Start with 0.1 SOL or less
- Test stop-loss triggers manually
- Verify all safety checks work

## Troubleshooting

### Bot Won't Start
- Check `.env` has `SOLANA_PRIVATE_KEY`
- Verify `logs/` directory exists
- Check Python 3.11+ installed

### No Trades Executing
- Criteria are strict by design (safety first)
- Lower thresholds for testing (not recommended for production)
- Check logs for which criteria failed

### Jito Bundle Fails
- Verify Jito endpoint configuration
- Check wallet has SOL for fees
- May need to retry or use fallback RPC

## Support

- Check logs first: `tail -f logs/kol_sniper.log`
- Test individual components separately
- Start with paper trading mode

---

**⚠️ Disclaimer**: Trading cryptocurrencies involves substantial risk. This bot is provided as-is with no guarantees. Always test thoroughly and never invest more than you can afford to lose.
