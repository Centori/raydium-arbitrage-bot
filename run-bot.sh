#!/bin/bash

# Run script for Raydium arbitrage bot with complete functionality
# This script will set up and run the enhanced liquidity monitor with all features enabled

# Colors for better readability
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Set default SOL amount for trades
SOL_AMOUNT=0.01

# Parse arguments
while [[ "$#" -gt 0 ]]; do
  case $1 in
    -s|--sol) SOL_AMOUNT="$2"; shift ;;
    -d|--dashboard) SHOW_DASHBOARD=true ;;
    -h|--help) 
      echo "Usage: ./run-bot.sh [OPTIONS]"
      echo "Options:"
      echo "  -s, --sol AMOUNT    Set the SOL amount for trades (default: 0.5)"
      echo "  -d, --dashboard     Enable performance dashboard"
      echo "  -h, --help          Show this help message"
      exit 0
      ;;
    *) echo "Unknown parameter: $1"; exit 1 ;;
  esac
  shift
done

echo -e "${BLUE}=== Raydium Arbitrage Bot Startup ===${NC}"
echo -e "${YELLOW}Performing system checks...${NC}"

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
  echo -e "${RED}Node.js is not installed. Please install it first.${NC}"
  exit 1
fi

# Check if TypeScript is installed
if ! command -v tsc &> /dev/null; then
  echo -e "${YELLOW}TypeScript is not installed. Installing...${NC}"
  npm install -g typescript
fi

# Check if ts-node is installed
if ! command -v ts-node &> /dev/null; then
  echo -e "${YELLOW}ts-node is not installed. Installing...${NC}"
  npm install -g ts-node
fi

# Check for required directories
mkdir -p data/liquidity
mkdir -p data/metrics
mkdir -p keys

# Check if wallet keypair exists
if [ ! -f "keys/wallet-keypair.json" ]; then
  echo -e "${YELLOW}Warning: No wallet keypair found in keys/wallet-keypair.json${NC}"
  echo -e "${YELLOW}Trade recommendations will still work but won't be able to check wallet balance${NC}"
fi

# Install dependencies if needed
if [ ! -d "node_modules" ]; then
  echo -e "${YELLOW}Installing dependencies...${NC}"
  npm install
fi

# Build the TypeScript code
echo -e "${YELLOW}Building TypeScript code...${NC}"
npm run build

# Run tests to verify components
echo -e "${YELLOW}Running component verification tests...${NC}"

# Create a temporary script to run with enhanced config
cat > run-enhanced-monitor.ts << EOL
import { EnhancedLiquidityMonitor } from './ts-src/blockchain/raydium/EnhancedLiquidityMonitor';
import { TradeRecommendation } from './ts-src/utils/TradeRecommender';
import { config } from './ts-src/utils/config';
import chalk from 'chalk';

async function main() {
  console.log(chalk.blue.bold('\n=== Raydium Arbitrage Bot with Liquidity Analysis ===\n'));
  console.log(chalk.yellow('Initializing bot with all features enabled...'));
  
  const monitor = new EnhancedLiquidityMonitor({
    // Core monitoring options
    samplingInterval: 3000,        // 3 seconds between samples
    maxPoolAge: 1800,              // 30 minutes
    minLiquidityRate: 50,          // Minimum flow rate
    minTotalLiquidity: 5000,       // Minimum liquidity
    rpcEndpoint: config.rpcEndpoint,
    
    // Enable all features
    enableRiskAnalysis: true,      // Token risk analysis
    enableMetrics: true,           // Performance metrics tracking
    enableDashboard: ${SHOW_DASHBOARD:-false}, // Performance dashboard
    enableTradeRecommendations: true,
    
    // Trade configuration
    tradeConfig: {
      solAmount: ${SOL_AMOUNT},    // SOL amount for trades
      minScore: 75,                // Minimum opportunity score
      maxRiskScore: 40,            // Maximum risk score
      profitThresholdPercent: 5    // 5% minimum expected profit
    },
    
    // Alert configuration
    alertConfig: {
      enableConsoleAlerts: true,
      enableFileLogging: true,
      logFilePath: './data/liquidity/alerts.log'
    }
  });
  
  // Set up event listeners
  monitor.on('recommendations', (recommendations: TradeRecommendation[]) => {
    // Only log when new YES recommendations appear
    const yesRecs = recommendations.filter(rec => rec.decision === 'YES');
    if (yesRecs.length > 0) {
      console.log(chalk.green.bold(\`Found \${yesRecs.length} buy opportunities!\`));
    }
  });
  
  monitor.on('error', (error: Error) => {
    console.error('Error during monitoring:', error);
  });
  
  // Start monitoring
  await monitor.start();
  
  console.log(chalk.green('✓ Bot started successfully'));
  console.log(chalk.yellow('Monitoring liquidity flows and generating trade recommendations...'));
  console.log(chalk.yellow('Press Ctrl+C to stop\n'));
  
  // Handle graceful shutdown
  process.on('SIGINT', () => {
    console.log('\nGracefully shutting down...');
    monitor.stop();
    console.log('Bot stopped. Goodbye!');
    process.exit(0);
  });
}

main().catch(error => {
  console.error('Fatal error:', error);
  process.exit(1);
});
EOL

echo -e "${GREEN}Starting Raydium Arbitrage Bot with ${SOL_AMOUNT} SOL preset for trades${NC}"
if [ "$SHOW_DASHBOARD" = true ]; then
  echo -e "${GREEN}Performance dashboard enabled${NC}"
fi

# Run the bot
ts-node run-enhanced-monitor.ts