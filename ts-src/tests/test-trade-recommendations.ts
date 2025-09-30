import { EnhancedLiquidityMonitor } from '../blockchain/raydium/EnhancedLiquidityMonitor';
import { TradeRecommendation } from '../utils/TradeRecommender';
import { config } from '../utils/config';
import chalk from 'chalk';
import readline from 'readline';

// Set up command line interface for interacting with the test
const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout
});

/**
 * Test script for demonstrating trade recommendations based on liquidity flows
 */
async function testTradeRecommendations() {
  console.log(chalk.blue.bold('=== Testing Liquidity Flow Trade Recommendations ===\n'));
  
  // Get SOL amount from user
  const solAmount = await promptForSolAmount();
  console.log(chalk.cyan(`Using ${solAmount} SOL for trade recommendations\n`));
  
  // Initialize the enhanced monitor with trade recommendations enabled
  const monitor = new EnhancedLiquidityMonitor({
    enableTradeRecommendations: true,
    enableRiskAnalysis: true,
    tradeConfig: {
      solAmount,
      minScore: 70,
      maxRiskScore: 50,
      enableAutomatic: false
    },
    samplingInterval: 5000, // 5 seconds
    maxPoolAge: 1800, // 30 minutes
  });
  
  // Set up event listeners for recommendations
  monitor.on('recommendations', (recommendations: TradeRecommendation[]) => {
    // Only show recommendations with YES decision for cleaner output
    const yesRecommendations = recommendations.filter(rec => rec.decision === 'YES');
    
    if (yesRecommendations.length > 0) {
      displayRecommendations(yesRecommendations);
    }
  });
  
  // Set up event listeners for errors
  monitor.on('error', (error: Error) => {
    console.error('Error during monitoring:', error);
  });
  
  // Start monitoring
  await monitor.start();
  
  console.log(chalk.green('✓ Monitoring started'));
  console.log(chalk.yellow('Analyzing liquidity flows...'));
  console.log(chalk.yellow('This may take a few moments to gather enough data for analysis'));
  console.log(chalk.yellow('Press Ctrl+C to stop monitoring\n'));
  
  // Keep the process running
  await new Promise<void>((resolve) => {
    process.on('SIGINT', async () => {
      console.log('\nStopping monitoring...');
      monitor.stop();
      resolve();
    });
  });
}

/**
 * Prompt the user for SOL amount to use for trade recommendations
 */
function promptForSolAmount(): Promise<number> {
  return new Promise((resolve) => {
    rl.question('Enter SOL amount for trade recommendations (default: 0.5): ', (answer) => {
      let amount = 0.5;
      
      if (answer.trim() !== '') {
        const parsed = parseFloat(answer);
        if (!isNaN(parsed) && parsed > 0) {
          amount = parsed;
        } else {
          console.log('Invalid amount, using default of 0.5 SOL');
        }
      }
      
      resolve(amount);
    });
  });
}

/**
 * Display trade recommendations in a formatted table
 */
function displayRecommendations(recommendations: TradeRecommendation[]): void {
  // Clear previous output for cleaner display
  console.clear();
  
  console.log(chalk.blue.bold('=== Liquidity Flow Trade Recommendations ===\n'));
  
  // Print header
  console.log(chalk.bold('Token Symbol   | Token Name             | Liquidity Flow        | Decision | Confidence | Risk Level'));
  console.log('--------------|------------------------|-----------------------|----------|------------|------------');
  
  // Print each recommendation
  recommendations.forEach(rec => {
    const symbol = rec.tokenSymbol.padEnd(12, ' ').substring(0, 12);
    const name = (rec.tokenName || 'Unknown').padEnd(22, ' ').substring(0, 22);
    const flow = rec.liquidityFlow.toLowerCase().replace('_', ' ').padEnd(20, ' ').substring(0, 20);
    
    // Color formatting
    const decisionColor = rec.decision === 'YES' ? chalk.green.bold : chalk.red;
    const flowColor = rec.liquidityFlow.includes('ACCUMULATION') || rec.liquidityFlow === 'ACCELERATING' 
      ? chalk.green 
      : rec.liquidityFlow === 'DISTRIBUTION' 
        ? chalk.red 
        : chalk.yellow;
    
    const riskColor = rec.riskLevel === 'LOW' 
      ? chalk.green 
      : rec.riskLevel === 'MEDIUM' 
        ? chalk.yellow 
        : chalk.red;
    
    const confidenceColor = rec.confidence > 80 
      ? chalk.green 
      : rec.confidence > 60 
        ? chalk.yellow 
        : chalk.red;
    
    console.log(
      `${symbol} | ${name} | ${flowColor(flow)} | ${decisionColor(rec.decision.padEnd(8))} | ${confidenceColor(rec.confidence.toFixed(1).padEnd(10))}% | ${riskColor(rec.riskLevel.padEnd(10))}`
    );
  });
  
  if (recommendations.length === 0) {
    console.log(chalk.yellow('No positive recommendations found yet. Continuing to analyze...'));
  } else {
    console.log('\nTop recommendation details:');
    
    const top = recommendations[0];
    console.log(`\nToken: ${chalk.cyan(top.tokenSymbol)} (${top.tokenName || 'Unknown Token'})`);
    console.log(`Address: ${top.tokenAddress}`);
    console.log(`Trading amount: ${top.tradingAmount} SOL`);
    console.log(`Expected return: ${top.expectedReturn.toFixed(4)} SOL`);
    
    console.log('\nAnalysis:');
    top.reasoning.forEach(reason => console.log(` - ${reason}`));
  }
  
  console.log('\nMonitoring liquidity flows in real-time... Press Ctrl+C to stop');
  console.log('Last updated: ' + new Date().toLocaleTimeString());
}

// Run the test
testTradeRecommendations().catch(error => {
  console.error('Fatal error:', error);
  process.exit(1);
});