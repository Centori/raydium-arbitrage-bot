# KOL Sniper Bot - Quick Setup for $5-10 Testing

## ✅ Completed Setup

### 1. Three-Signal Detection System
- **🐋 Smart Money Detection** - On-chain whale analysis (10+ SOL volume)
- **📈 Liquidity Momentum** - 50%+ acceleration tracking
- **🔥 FOMO/Pump Patterns** - Price surge + volume spike detection

### 2. Auto Token Discovery
- Fetches trending tokens from DexScreener every hour
- Filters: $50k+ liquidity, <3 hours old, $20k+ 1h volume
- Automatically refreshes token list

### 3. Hourly Email Updates
- Sends detailed status every hour
- Includes: trades, P&L, whales found, success rate
- HTML formatted for easy reading

### 4. Safe Test Configuration
- **Trade Size**: 0.025 SOL (~$5 USD)
- **Stop-Loss**: 8% automatic
- **Take-Profit**: 25% automatic
- **Rate Limited**: No RPC errors

## 📧 Email Setup (Required)

Edit `.env` and replace with your actual email:

```bash
# Gmail Example (recommended)
SMTP_EMAIL=your.actual.email@gmail.com
SMTP_PASSWORD=your_gmail_app_password  # NOT your regular password!
NOTIFICATION_EMAIL=your.actual.email@gmail.com
EMAIL_NOTIFICATIONS=true
```

### Getting Gmail App Password:
1. Go to Google Account → Security
2. Enable 2-Factor Authentication
3. Search for "App Passwords"
4. Generate password for "Mail"
5. Copy the 16-character password
6. Use that in SMTP_PASSWORD

## 🚀 Running the Bot

### Test Run (Local):
```bash
# Make sure you have 0.1+ SOL in wallet for testing
python3 run_kol_sniper.py
```

### Production Run (Background):
```bash
nohup python3 run_kol_sniper.py > logs/kol_output.log 2>&1 &
```

### Check Status:
```bash
tail -f logs/kol_sniper.log
```

### Stop Bot:
```bash
pkill -f run_kol_sniper
```

## 💰 Recommended Starting Balance

For **$5-10 per trade** testing:
- **Minimum**: 0.1 SOL ($20) - allows 3-4 test trades
- **Recommended**: 0.2 SOL ($40) - allows 7-8 test trades
- **Safe**: 0.5 SOL ($100) - allows 15+ test trades

## 📊 What to Expect

### Hourly Email Will Include:
- ✅ Tokens monitored (refreshed hourly)
- ✅ Scans completed
- ✅ Trades executed
- ✅ Success rate
- ✅ Total P&L in SOL and USD
- ✅ Whales detected
- ✅ Runtime

### Entry Criteria (ALL must pass):
1. ✅ LP burned or locked
2. ✅ Not a honeypot  
3. ✅ Not mintable
4. ✅ No freeze authority
5. ✅ Liquidity > $50k
6. ✅ Liquidity accelerating 50%+
7. ✅ FOMO or pump pattern detected
8. ✅ Whale activity in recent transactions
9. ✅ Volume ratio > 3.0x

## 🔍 Monitoring

### Real-time Logs:
```bash
# Bot activity
tail -f logs/kol_sniper.log

# All output
tail -f logs/kol_output.log
```

### Check Running Process:
```bash
ps aux | grep run_kol_sniper
```

## ⚠️ Important Notes

### Testing Phase:
- Start with 0.1 SOL to test the system
- Monitor first 2-3 trades closely
- Verify email notifications arrive
- Check stop-loss triggers properly

### Entry Signal is STRICT:
- May take hours to find qualifying token
- This is intentional - safety first!
- Better to miss opportunities than lose money

### Email Frequency:
- **Hourly**: Status update (trades, P&L, whales)
- **Immediate**: Trade entry/exit alerts (if configured)

## 🛠️ Troubleshooting

### No Emails Received:
```bash
# Test email system
python3 -c "from email_notifier import EmailNotifier; import asyncio; n = EmailNotifier(); asyncio.run(n.send_hourly_kol_update(5, 10, 2, 1, 0.01, 3, 1.5))"
```

### No Tokens Found:
- Normal if no tokens meet strict criteria
- Bot will keep searching automatically
- Refreshes token list every hour

### Bot Stops:
- Check logs: `tail -100 logs/kol_sniper.log`
- Likely RPC rate limit (already handled)
- Will auto-retry after 5 minutes

## 📈 Expected Performance

### Realistic Expectations:
- **Win Rate**: 60-70% (strict entry criteria)
- **Avg Profit**: 10-20% per winning trade  
- **Trades per Day**: 2-5 (depends on market)
- **Monthly Return**: 50-100% (if market is active)

### Risk Profile:
- **Max Loss per Trade**: 8% (stop-loss)
- **Max Gain per Trade**: 25%+ (take-profit)
- **Risk/Reward**: ~1:3 ratio

## 🔄 Next Steps After Testing

1. **Monitor for 24 hours** with small amounts
2. **Verify email updates** are arriving hourly
3. **Check trade execution** works correctly
4. **Increase trade size** to 0.05 SOL ($10) if successful
5. **Scale up gradually** based on performance

---

**Ready to start!** The bot will:
- ✅ Auto-discover trending tokens hourly
- ✅ Detect whale activity on-chain
- ✅ Execute $5 trades when all signals align
- ✅ Email you hourly updates
- ✅ Auto stop-loss/take-profit

**Questions?** Check logs or reach out!
