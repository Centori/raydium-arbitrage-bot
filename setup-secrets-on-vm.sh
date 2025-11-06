#!/bin/bash
# Setup script to run ON the GCP VM after deployment
# This script should be run manually via SSH to set up secrets

set -e

echo "=== Raydium Bot Secret Setup ==="
echo ""
echo "This script will help you set up your private keys and configuration on the VM."
echo "NEVER commit these files to git or include them in your deployment."
echo ""

BOT_DIR="/opt/raydium-bot"
ENV_FILE="$BOT_DIR/.env"

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root: sudo bash setup-secrets-on-vm.sh"
    exit 1
fi

# Create .env file
echo "Creating .env file..."
cat > "$ENV_FILE" << 'ENVEOF'
# Solana RPC Configuration
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
HELIUS_API_KEY=your_helius_api_key_here

# Wallet Configuration (PASTE YOUR NEW PRIVATE KEY HERE)
PRIVATE_KEY=your_base58_private_key_here
WALLET_ADDRESS=your_wallet_address_here

# Trading Configuration
MAX_POSITION_SIZE=0.5
MIN_PROFIT_THRESHOLD=0.02
SLIPPAGE_TOLERANCE=0.01
MAX_SLIPPAGE=0.05

# Email Notifications
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
EMAIL_USERNAME=your_email@gmail.com
EMAIL_PASSWORD=your_app_specific_password_here
NOTIFICATION_EMAIL=your_notification_email@gmail.com

# Bot Configuration
ENABLE_MIGRATION_STRATEGY=true
ENABLE_KOL_TRACKING=true
ENABLE_ELITE_TRACKING=true
LOG_LEVEL=INFO
ENVEOF

echo ""
echo ".env file created at: $ENV_FILE"
echo ""
echo "⚠️  IMPORTANT: Edit this file with your actual secrets:"
echo "   sudo nano $ENV_FILE"
echo ""
echo "Then set secure permissions:"
echo "   sudo chmod 600 $ENV_FILE"
echo "   sudo chown raydium-bot:raydium-bot $ENV_FILE"
echo ""
echo "After editing, restart the bot:"
echo "   sudo systemctl restart raydium-bot"
echo "   sudo systemctl status raydium-bot"
echo ""
echo "View logs:"
echo "   sudo journalctl -u raydium-bot -f"
