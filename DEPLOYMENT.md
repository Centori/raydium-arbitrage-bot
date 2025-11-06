# Raydium Bot - Secure Cloud Deployment Guide

## Prerequisites
- New Solana keypair (never committed to git)
- GCP project with Compute Engine API enabled
- `gcloud` CLI authenticated

## Step 1: Deploy Code to GCP VM

```bash
# Run the deployment script (deploys code WITHOUT secrets)
./deploy-to-gcp.sh
```

This will:
- Create a GCP Compute Engine VM
- Install Python and dependencies
- Clone your GitHub repo
- Set up the bot as a systemd service (but won't start yet)

## Step 2: Generate New Solana Keypair (Local)

**NEVER use old keys that were committed to git!**

```bash
# Generate new keypair
solana-keygen new --outfile new_wallet.json

# Get the address
solana address --keypair new_wallet.json

# Fund the new wallet
solana transfer NEW_ADDRESS AMOUNT --keypair old_wallet.json

# Get base58 private key for .env
cat new_wallet.json
# Copy the array of numbers, you'll encode this as base58
```

## Step 3: SSH into VM and Setup Secrets

```bash
# SSH into the VM
gcloud compute ssh raydium-bot-vm --zone=us-central1-a

# Upload and run the secret setup script
# (The script was deployed with your code)
sudo bash /opt/raydium-bot/setup-secrets-on-vm.sh
```

This creates a template `.env` file at `/opt/raydium-bot/.env`

## Step 4: Edit .env with Your Secrets

```bash
# Edit the .env file on the VM
sudo nano /opt/raydium-bot/.env
```

**Required fields to update:**
- `PRIVATE_KEY` - Your new Solana wallet private key (base58 encoded)
- `WALLET_ADDRESS` - Your new Solana wallet address
- `HELIUS_API_KEY` - Your Helius API key (if using)
- `EMAIL_USERNAME` - Your Gmail address
- `EMAIL_PASSWORD` - Gmail app-specific password
- `NOTIFICATION_EMAIL` - Where to send alerts

Save and exit (Ctrl+X, Y, Enter)

## Step 5: Secure Permissions

```bash
# Set secure permissions
sudo chmod 600 /opt/raydium-bot/.env
sudo chown raydium-bot:raydium-bot /opt/raydium-bot/.env
```

## Step 6: Start the Bot

```bash
# Start the service
sudo systemctl start raydium-bot

# Check status
sudo systemctl status raydium-bot

# View live logs
sudo journalctl -u raydium-bot -f
```

## Step 7: Verify Bot is Working

```bash
# Check balance
cd /opt/raydium-bot
source venv/bin/activate
python bot_cli.py balance

# Check stats
python bot_cli.py stats

# Monitor activity
python bot_cli.py monitor
```

## Managing the Bot

### View Logs
```bash
sudo journalctl -u raydium-bot -f
```

### Restart Bot
```bash
sudo systemctl restart raydium-bot
```

### Stop Bot
```bash
sudo systemctl stop raydium-bot
```

### Update Code (without secrets)
```bash
cd /opt/raydium-bot
sudo -u raydium-bot git pull origin main
sudo systemctl restart raydium-bot
```

## Security Checklist

- [ ] New Solana keypair generated (never committed)
- [ ] Old compromised keys deactivated and funds migrated
- [ ] `.env` file has 600 permissions
- [ ] `.env` file owned by raydium-bot user
- [ ] `.gitignore` properly configured
- [ ] No secrets in git history
- [ ] Gmail app-specific password used (not main password)
- [ ] VM firewall rules configured (if needed)
- [ ] Regular backups of VM or important data

## Troubleshooting

### Bot won't start
```bash
# Check logs for errors
sudo journalctl -u raydium-bot -n 100

# Verify .env file exists and has correct permissions
ls -la /opt/raydium-bot/.env

# Test Python environment
cd /opt/raydium-bot
source venv/bin/activate
python -c "from dotenv import load_dotenv; load_dotenv(); print('OK')"
```

### Can't connect to Solana RPC
```bash
# Test RPC connection
curl -X POST https://api.mainnet-beta.solana.com \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"getHealth"}'
```

### Email notifications not working
- Verify Gmail app-specific password (not your main password)
- Check SMTP settings in `.env`
- Enable "Less secure app access" if using Gmail (not recommended)
- Use a dedicated email service account

## Cost Estimation (GCP)

- **e2-micro VM**: ~$7/month
- **20GB disk**: ~$0.80/month
- **Network egress**: ~$1-2/month
- **Total**: ~$10/month

## Support

For issues, check:
1. Bot logs: `sudo journalctl -u raydium-bot -f`
2. System logs: `sudo journalctl -xe`
3. RPC endpoint status
4. Wallet balance and permissions
