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
    enableDashboard: false, // Performance dashboard
    enableTradeRecommendations: true,
    
    // Trade configuration
    tradeConfig: {
      solAmount: 0.01,    // SOL amount for trades
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
      console.log(chalk.green.bold(`Found ${yesRecs.length} buy opportunities!`));
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
