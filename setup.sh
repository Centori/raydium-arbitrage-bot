#!/bin/bash
set -e

# Colors for better output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}Setting up Raydium Arbitrage Bot...${NC}"

# Check for .env file
if [ ! -f .env ]; then
  echo -e "${YELLOW}Creating .env file from template...${NC}"
  cat > .env << EOL
# RPC Endpoints
ALCHEMY_API_KEY=your-alchemy-api-key-here
RPC_ENDPOINT=https://api.mainnet-beta.solana.com
JITO_ENDPOINT=https://mainnet.block-engine.jito.wtf

# Jito Authentication
JITO_AUTH_KEYPAIR_BASE64=

# API Configuration
API_PORT=3000
API_HOST=localhost

# Trading Settings
SLIPPAGE_BPS=100
MIN_BUY_SOL=0.1
MAX_BUY_SOL=1.0
EOL
  echo -e "${YELLOW}Please edit .env file with your API keys and settings${NC}"
else
  echo -e "${GREEN}.env file already exists${NC}"
fi

# Check for Node.js
if ! command -v node &> /dev/null; then
  echo -e "${RED}Node.js is not installed. Please install Node.js 18+ to continue.${NC}"
  exit 1
fi

# Check for npm
if ! command -v npm &> /dev/null; then
  echo -e "${RED}npm is not installed. Please install npm to continue.${NC}"
  exit 1
fi

# Check for Python
if ! command -v python3 &> /dev/null; then
  echo -e "${RED}Python is not installed. Please install Python 3.9+ to continue.${NC}"
  exit 1
fi

# Check for Docker and Docker Compose
if ! command -v docker &> /dev/null; then
  echo -e "${YELLOW}Docker not found. Docker is recommended for running the hybrid architecture.${NC}"
else
  if ! command -v docker-compose &> /dev/null; then
    echo -e "${YELLOW}Docker Compose not found. Docker Compose is recommended for running the hybrid architecture.${NC}"
  else
    echo -e "${GREEN}Docker and Docker Compose found.${NC}"
  fi
fi

# Install TypeScript dependencies
echo -e "${GREEN}Installing TypeScript dependencies...${NC}"
npm install

# Install Python dependencies
echo -e "${GREEN}Installing Python dependencies...${NC}"
pip3 install -r requirements.txt

echo -e "${GREEN}Setup completed!${NC}"
echo -e "${YELLOW}Usage:${NC}"
echo -e "  - Development mode:"
echo -e "    - TS Service: ${GREEN}npm run dev${NC}"
echo -e "    - Python Bot: ${GREEN}python3 main.py${NC}"
echo -e "  - Production mode (Docker):"
echo -e "    - ${GREEN}docker-compose up -d${NC}"
echo -e ""
echo -e "${YELLOW}Make sure to edit .env file with your API keys before starting!${NC}"
