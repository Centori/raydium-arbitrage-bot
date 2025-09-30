#!/bin/bash

# Setup Telegram Commands for SolAssassin_bot
# This script registers commands with the Telegram bot API

echo "===== Setting up SolAssassin_bot Telegram Commands ====="

# Load configuration from .env file
if [ -f ./.env ]; then
  set -a  # automatically export all variables
  source ./.env
  set +a
else
  echo "Error: .env file not found!"
  exit 1
fi

# Debug token (hiding sensitive parts)
TOKEN_LENGTH=${#TELEGRAM_BOT_TOKEN}
TOKEN_START=$(echo $TELEGRAM_BOT_TOKEN | cut -c1-5)
TOKEN_END=$(echo $TELEGRAM_BOT_TOKEN | cut -c$((TOKEN_LENGTH-4))-)
echo "Bot token length: $TOKEN_LENGTH"
echo "Bot token format check (first 5 and last 4 chars): ${TOKEN_START}...${TOKEN_END}"

# Remove any potential hidden characters
TELEGRAM_BOT_TOKEN=$(echo "$TELEGRAM_BOT_TOKEN" | tr -d '[:space:]' | tr -cd '[:print:]')
TELEGRAM_CHAT_ID=$(echo "$TELEGRAM_CHAT_ID" | tr -d '[:space:]' | tr -cd '[:print:]')

# Test bot token first
echo "Testing bot token..."
TEST_RESPONSE=$(curl -v -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe" 2>&1)
echo "API Response:"
echo "$TEST_RESPONSE"

if ! echo "$TEST_RESPONSE" | grep -q '"ok":true'; then
  echo "❌ Error: Invalid bot token or API not accessible"
  exit 1
fi
echo "✅ Bot token validated successfully"

# Define commands to register with SolAssassin_bot
echo "Registering commands with SolAssassin_bot..."

# Use the Telegram Bot API to set commands with verbose output
REGISTER_RESPONSE=$(curl -v -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setMyCommands" \
-H "Content-Type: application/json" \
-d '{
  "commands": [
    {"command": "buy", "description": "Buy a token - /buy SOL 0.5"},
    {"command": "sell", "description": "Sell a token - /sell SOL 0.5"},
    {"command": "setamount", "description": "Set default trading amount - /setamount 0.5"},
    {"command": "setslippage", "description": "Set max slippage in basis points - /setslippage 100"},
    {"command": "setpriorityfee", "description": "Set priority fee in lamports - /setpriorityfee 10000"},
    {"command": "setflashfee", "description": "Set flash loan fee in basis points - /setflashfee 30"},
    {"command": "togglebribes", "description": "Enable/disable validator bribes"},
    {"command": "setbribe", "description": "Set bribe amount in lamports - /setbribe 10000"},
    {"command": "toggleauto", "description": "Enable/disable auto-execution"},
    {"command": "status", "description": "Check bot status and metrics"},
    {"command": "balance", "description": "Check wallet balance and P/L"},
    {"command": "config", "description": "Show current configuration"},
    {"command": "help", "description": "Show available commands"}
  ]
}' 2>&1)

echo "Command registration response:"
echo "$REGISTER_RESPONSE"

if ! echo "$REGISTER_RESPONSE" | grep -q '"ok":true'; then
  echo "❌ Failed to register commands"
  exit 1
fi

echo "✅ Successfully registered commands"

# Send a test message
echo "Sending test message..."
MESSAGE_RESPONSE=$(curl -v -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
-H "Content-Type: application/json" \
-d '{
  "chat_id": "'"$TELEGRAM_CHAT_ID"'",
  "text": "✅ SolAssassin_bot is now configured with enhanced features:\n\n• Trade configuration\n• MEV features (bribes, priority fees)\n• Flash loan settings\n• Auto-execution mode\n\nType /help to see all available commands.",
  "parse_mode": "HTML"
}' 2>&1)

echo "Message response:"
echo "$MESSAGE_RESPONSE"

if ! echo "$MESSAGE_RESPONSE" | grep -q '"ok":true'; then
  echo "❌ Failed to send test message. Please verify your TELEGRAM_CHAT_ID"
  exit 1
fi

echo "✅ Setup completed successfully!"
echo "Try sending /help to your bot to see the available commands."