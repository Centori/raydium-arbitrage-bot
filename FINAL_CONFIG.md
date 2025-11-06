# ✅ KOL Sniper Bot - Final Configuration

## 🎯 Updated Settings (As Requested)

### Trade Parameters:
- **Trade Size**: 0.025 SOL (~$5 USD)  
- **Stop-Loss**: 8% (hard limit)
- **Take-Profit**: UNCAPPED / DYNAMIC 🚀
  - Exits when velocity reverses (3 consecutive 2%+ drops)
  - Exits when 2+ whales start selling
  - Tracks peak profit and exits on momentum loss
- **Max Concurrent Trades**: 4 positions with 0.481 SOL balance

### Dynamic Exit Strategy:

**The bot will sell when ANY of these occur:**

1. **Stop-Loss** (-8%): Protects capital ✅
2. **Velocity Reversal**: Price drops 2%+ for 3 consecutive checks 📉
3. **KOL/Whale Sell**: 2+ smart money wallets selling (checked when up 10%+) 🐋
4. **Peak Tracking**: Monitors highest profit achieved, exits if momentum fades

**Example:**
```
Entry: $0.10
Peak: $0.50 (+400%) 🚀
Price drops to $0.48 (-4% from peak)
Price drops to $0.46 (-8% from peak) 
Price drops to $0.44 (-12% from peak)
→ EXIT at $0.44 for +340% profit! ✅
```

## 📊 Position Monitoring

Every 5 seconds, the bot checks:
- Current P&L
- Price velocity (rate of change)
- Whale buy/sell activity
- Logs progress: "🐎 Holding: +127.5% (Peak: 150.3%, Velocity: -2.1%)"

## 💰 With 0.481 SOL Balance:

- **0.1 SOL available** for trading (keeping 0.381 for fees/buffer)
- **0.025 SOL per trade** (25% of trading balance)
- **Max 4 concurrent positions**
- Each position independently monitored

## 🚀 Benefits of Dynamic Exit:

✅ **Rides winners** - No artificial 25% cap
✅ **Protects profits** - Exits when momentum turns
✅ **Follows smart money** - Exits when whales dump  
✅ **Tracks peak** - You'll know max profit achieved
✅ **Still has stop-loss** - 8% downside protection

## 📧 Email Updates Will Show:

```
Subject: 🎯 KOL Sniper Hourly - 2 trades, +0.085 SOL

Position Closed - Velocity Reversal
Token: pump...123
Entry: $0.000012
Exit: $0.000089
P&L: +641.7% (0.016 SOL)
Peak: +782.3%
Duration: 27.3min
```

## 🎯 VM Ready Commands:

```bash
# SSH to VM
gcloud compute ssh raydium-bot --zone=us-central1-a

# Go to bot directory
cd ~/raydium-bots

# Start bot
./start_kol_sniper.sh

# Check status
./status.sh

# View logs
tail -f logs/kol_sniper.log

# Stop bot
./stop_kol_sniper.sh
```

## ⚠️ Important Notes:

1. **Velocity checks happen every 5 seconds** - very responsive
2. **Whale activity checked when up 10%+** - avoids rate limits
3. **Peak profit is always tracked** - you'll see max opportunity
4. **Stop-loss still active** - 8% protection always there
5. **Trade size: 0.025 SOL** - safe for testing with limited capital

## 🏆 Expected Behavior:

**Losing Trade:**
- Hits 8% stop-loss quickly ❌
- Loss: 0.002 SOL ($0.40)

**Small Win:**
- Up 15%, velocity reverses
- Profit: 0.00375 SOL ($0.75) ✅

**Big Win:**
- Up 400%, whales start selling  
- Profit: 0.100 SOL ($20) 🚀✅

**Mega Win:**
- Up 1500%, velocity turns negative
- Profit: 0.375 SOL ($75) 🎯✅✅

---

**Ready to deploy!** Bot will maximize winners while protecting capital. 

SSH to VM and start: `./start_kol_sniper.sh`
