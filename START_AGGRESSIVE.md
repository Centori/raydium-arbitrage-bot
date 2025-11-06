# 🚀 Aggressive Cross-DEX Arbitrage - Quick Start

**Goal**: Grow 0.48 SOL → 2.5 SOL (420% ROI)  
**Strategy**: Cross-DEX arbitrage only (no expensive Jito bundles)  
**Risk Level**: Moderate-High (No ROI caps for maximum growth)

---

## Configuration Applied

✅ **Trading Settings:**
- Trade size: 0.02 - 0.48 SOL (dynamic based on opportunity)
- Min profit threshold: $0.25 USD per trade
- Max daily trades: 100 (no cap on volume)
- Slippage tolerance: 1.5% (150 bps)

✅ **Risk Settings:**
- Max risk score: 65 (accepts more opportunities)
- Min liquidity: $25,000 TVL (lower threshold for more pairs)
- Accept all token pairs: TRUE
- Max daily loss: 0.15 SOL (safety circuit breaker)

✅ **Disabled Expensive Features:**
- ❌ Backrun strategy (requires Jito tips)
- ❌ Migration sniping (rare events)
- ❌ Jito bundles (saves on tips)

---

## How to Start

### 1. Start the Bot

```bash
cd /Users/lm/Desktop/raydium-arbitrage-bot

# Option A: Using Python directly
python3 run_aggressive_crossdex.py

# Option B: Make executable and run
./run_aggressive_crossdex.py
```

### 2. Monitor in Real-Time

**Live logs:**
```bash
tail -f logs/aggressive_crossdex.log
```

**Check balance:**
```bash
# In Python console
from wallet import WalletManager
from config import Config
import asyncio

async def check_balance():
    config = Config()
    wallet = WalletManager(config)
    balance = await wallet.client.get_balance(wallet.payer.pubkey())
    print(f"Balance: {balance.value / 1e9:.4f} SOL")

asyncio.run(check_balance())
```

### 3. Track Progress

The bot will send Telegram updates every 5 minutes with:
- Current balance
- Progress toward 2.5 SOL goal
- Win rate and trade count
- Total profit/loss

---

## Expected Performance

**Conservative Estimate:**
- Average profit per trade: $0.50 - $2.00
- Trade frequency: 10-30 trades/day
- Daily profit target: $5-15 USD (~0.025-0.08 SOL)
- Time to reach 2.5 SOL: **2-4 weeks**

**Aggressive Estimate (with high market volatility):**
- Average profit per trade: $1.00 - $5.00
- Trade frequency: 30-80 trades/day
- Daily profit target: $20-50 USD (~0.1-0.25 SOL)
- Time to reach 2.5 SOL: **1-2 weeks**

---

## Safety Features

✅ **Circuit Breakers:**
- Auto-stop if daily loss exceeds 0.15 SOL
- Blacklist tokens after 3 consecutive failed trades
- Real-time balance monitoring

✅ **Risk Management:**
- Only trades with >$25K liquidity
- Max 1.5% slippage protection
- Priority on stablecoin pairs (SOL/USDC, SOL/USDT)

---

## Monitoring Commands

### Check if bot is running:
```bash
ps aux | grep aggressive_crossdex
```

### View recent trades:
```bash
tail -n 50 logs/aggressive_crossdex.log | grep "Trade executed"
```

### Check for errors:
```bash
tail -n 50 logs/aggressive_crossdex.log | grep "ERROR"
```

### Stop the bot gracefully:
```bash
# Press Ctrl+C in the terminal running the bot
# Or find and kill the process:
pkill -f run_aggressive_crossdex
```

---

## Optimization Tips

**If not finding enough opportunities:**
1. Lower MIN_CROSS_DEX_DIFF_PCT to 0.2% in .env
2. Lower MIN_LIQUIDITY_TVL to 15000 in .env
3. Increase scan frequency (reduce sleep time in script)

**If too many failed trades:**
1. Increase MIN_PROFIT_USD to 0.50 in .env
2. Increase SLIPPAGE_BPS to 200 (2%) in .env
3. Lower MAX_RISK_SCORE to 55 in .env

**If you want even more aggressive:**
1. Set TRADE_AMOUNT_SOL=0.15 in .env (use more capital per trade)
2. Set MIN_CROSS_DEX_DIFF_PCT=0.15 in .env (catch smaller spreads)
3. Remove MAX_DAILY_TRADES limit entirely

---

## Important Notes

⚠️ **This is aggressive trading:**
- Higher risk tolerance to reach goal faster
- No ROI caps means you'll take more opportunities
- Monitor regularly, especially in the first 24 hours

💰 **Capital growth path:**
- 0.48 SOL → 1.0 SOL (fastest, many opportunities)
- 1.0 SOL → 2.0 SOL (good opportunities still available)
- 2.0 SOL → 2.5 SOL (final push, fewer optimal trades)

🎯 **Once you reach 2.5 SOL:**
- Switch to backrun strategy for better ROI
- Target new token launches with 2-5 SOL positions
- Consider running multiple strategies simultaneously

---

## Support

**If something goes wrong:**
1. Check logs: `logs/aggressive_crossdex.log`
2. Verify wallet balance hasn't hit circuit breaker
3. Restart bot with: `python3 run_aggressive_crossdex.py`
4. Check Telegram for error notifications

**Bot will auto-stop when:**
- Target of 2.5 SOL is reached ✅
- Daily loss limit hit (0.15 SOL) 🛑
- Ctrl+C pressed (graceful shutdown) 🛑

---

Good luck! 🚀 Let's grow that 0.48 SOL!
