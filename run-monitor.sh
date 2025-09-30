#!/bin/bash

# Run the Raydium Arbitrage Bot with Liquidity Analysis in Docker
# with Telegram notifications enabled

echo "Starting Raydium Arbitrage Bot with Telegram notifications..."

# Check if .env file exists, if not create from example
if [ ! -f ./.env ]; then
  echo "Creating .env file from .env.example"
  cp ./.env.example ./.env
  echo "Please edit .env file with your Telegram bot token and chat ID"
  exit 1
fi

# Check if Telegram credentials are set
telegram_token=$(grep "TELEGRAM_BOT_TOKEN" ./.env | cut -d '=' -f 2)
telegram_chat=$(grep "TELEGRAM_CHAT_ID" ./.env | cut -d '=' -f 2)

if [ "$telegram_token" != "your_bot_token_here" ] && [ -n "$telegram_token" ] && \
   [ "$telegram_chat" != "your_chat_id_here" ] && [ -n "$telegram_chat" ]; then
  # Start just the liquidity monitor service
  docker-compose up -d liquidity-monitor
  echo "Liquidity monitor started with Telegram notifications enabled"
  echo "Check docker logs with: docker-compose logs -f liquidity-monitor"
else
  echo "ERROR: Telegram bot token or chat ID not set"
  echo "Please edit .env file and set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID"
  exit 1
fi