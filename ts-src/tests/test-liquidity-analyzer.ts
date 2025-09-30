import { config } from '../utils/config';
import { RaydiumClient } from '../blockchain/raydium/RaydiumClient';
import { LiquidityFlowAnalyzer } from '../blockchain/raydium/LiquidityFlowAnalyzer';
import chalk from 'chalk';

/**
 * This test script validates the LiquidityFlowAnalyzer by:
 * 1. Simulating pool liquidity changes with various patterns
 * 2. Testing the analyzer's pattern detection
 * 3. Validating the rate calculation
 */

// Mock pool data for testing
const createMockPool = (id: string, baseSymbol: string, quoteSymbol: string, baseAmount: string, quoteAmount: string) => {
  return {
    id,
    version: 4,
    baseToken: {
      address: `base-${id}`,
      symbol: baseSymbol,
      decimals: 9
    },
    quoteToken: {
      address: `quote-${id}`,
      symbol: quoteSymbol,
      decimals: 9
    },
    baseAmount,
    quoteAmount,
    lpMint: `lp-${id}`,
    baseVault: `bv-${id}`,
    quoteVault: `qv-${id}`,
    feeRate: 30,
    status: 'active' as const,
    creationTime: Date.now() / 1000 - 1800 // 30 minutes old
  };
};

async function testPatternDetection() {
  console.log(chalk.blue.bold('\n=== Testing Liquidity Flow Pattern Detection ===\n'));
  
  const analyzer = new LiquidityFlowAnalyzer();
  
  // Create mock pools with different patterns
  const strongAccumPool = createMockPool('pool1', 'TEST1', 'USDC', '1000000', '1000000');
  const acceleratingPool = createMockPool('pool2', 'TEST2', 'USDC', '1000000', '1000000');
  const steadyPool = createMockPool('pool3', 'TEST3', 'USDC', '1000000', '1000000');
  const deceleratingPool = createMockPool('pool4', 'TEST4', 'USDC', '1000000', '1000000');
  const distributionPool = createMockPool('pool5', 'TEST5', 'USDC', '1000000', '1000000');
  
  console.log('Simulating liquidity patterns over time...\n');
  
  // Simulate time passing and liquidity changes
  for (let i = 0; i < 30; i++) {
    // Simulate Strong Accumulation (accelerating growth)
    strongAccumPool.baseAmount = (Number(strongAccumPool.baseAmount) + (1000 * Math.pow(i, 2))).toString();
    strongAccumPool.quoteAmount = (Number(strongAccumPool.quoteAmount) + (1000 * Math.pow(i, 2))).toString();
    
    // Simulate Accelerating (consistently growing)
    acceleratingPool.baseAmount = (Number(acceleratingPool.baseAmount) + (2000 * i)).toString();
    acceleratingPool.quoteAmount = (Number(acceleratingPool.quoteAmount) + (2000 * i)).toString();
    
    // Simulate Steady (linear growth)
    steadyPool.baseAmount = (Number(steadyPool.baseAmount) + 1000).toString();
    steadyPool.quoteAmount = (Number(steadyPool.quoteAmount) + 1000).toString();
    
    // Simulate Decelerating (slowing growth)
    deceleratingPool.baseAmount = (Number(deceleratingPool.baseAmount) + (3000 / (i + 1))).toString();
    deceleratingPool.quoteAmount = (Number(deceleratingPool.quoteAmount) + (3000 / (i + 1))).toString();
    
    // Simulate Distribution (decreasing)
    if (i > 15) {
      distributionPool.baseAmount = (Number(distributionPool.baseAmount) - 1000).toString();
      distributionPool.quoteAmount = (Number(distributionPool.quoteAmount) - 1000).toString();
    } else {
      distributionPool.baseAmount = (Number(distributionPool.baseAmount) + 1000).toString();
      distributionPool.quoteAmount = (Number(distributionPool.quoteAmount) + 1000).toString();
    }
    
    // Add pool data to analyzer
    analyzer.addPoolSample(strongAccumPool);
    analyzer.addPoolSample(acceleratingPool);
    analyzer.addPoolSample(steadyPool);
    analyzer.addPoolSample(deceleratingPool);
    analyzer.addPoolSample(distributionPool);
    
    // Small delay to simulate time passing
    await new Promise(resolve => setTimeout(resolve, 200));
  }
  
  // Get analysis results
  const results = [
    { poolId: 'pool1', analysis: analyzer.detectAccumulation('pool1') },
    { poolId: 'pool2', analysis: analyzer.detectAccumulation('pool2') },
    { poolId: 'pool3', analysis: analyzer.detectAccumulation('pool3') },
    { poolId: 'pool4', analysis: analyzer.detectAccumulation('pool4') },
    { poolId: 'pool5', analysis: analyzer.detectAccumulation('pool5') }
  ];
  
  // Display results
  console.log(chalk.green('Pattern Detection Results:'));
  results.forEach(result => {
    let patternColor;
    switch (result.analysis.pattern) {
      case 'STRONG_ACCUMULATION':
        patternColor = chalk.green.bold;
        break;
      case 'ACCELERATING':
        patternColor = chalk.yellow.bold;
        break;
      case 'STEADY':
        patternColor = chalk.blue.bold;
        break;
      case 'DECELERATING':
        patternColor = chalk.cyan.bold;
        break;
      case 'DISTRIBUTION':
        patternColor = chalk.red.bold;
        break;
      default:
        patternColor = chalk.gray.bold;
    }
    
    console.log(`\nPool ID: ${result.poolId}`);
    console.log(`Pattern: ${patternColor(result.analysis.pattern)}`);
    console.log(`Rate: ${result.analysis.rate.toFixed(2)} units/sec`);
  });
  
  // Check if the prioritized pools order is correct
  const prioritizedPools = analyzer.getPrioritizedPools();
  console.log(chalk.green('\nPrioritized Pools:'));
  prioritizedPools.forEach((pool, i) => {
    console.log(`${i + 1}. ${pool.poolId} - ${chalk.bold(pool.pattern)} (Rate: ${pool.rate.toFixed(2)})`);
  });
}

async function testRealTimeAnalysis() {
  console.log(chalk.blue.bold('\n=== Testing Real-time Liquidity Analysis ===\n'));
  
  try {
    // Connect to Raydium
    const client = new RaydiumClient(config.rpcEndpoint);
    const analyzer = new LiquidityFlowAnalyzer();
    
    console.log('Fetching pools from Raydium...');
    const pools = await client.fetchAllPools();
    console.log(`Found ${pools.length} pools`);
    
    // Add initial samples
    pools.forEach(pool => analyzer.addPoolSample(pool));
    console.log('Added initial pool samples to analyzer');
    
    // Wait and fetch again to see changes
    console.log('Waiting 5 seconds to detect changes...');
    await new Promise(resolve => setTimeout(resolve, 5000));
    
    const updatedPools = await client.fetchAllPools();
    updatedPools.forEach(pool => analyzer.addPoolSample(pool));
    console.log('Added updated pool samples to analyzer');
    
    // Display top opportunities based on liquidity changes
    const opportunities = analyzer.getPrioritizedPools();
    console.log(chalk.green(`\nFound ${opportunities.length} pools with detectable patterns`));
    
    if (opportunities.length > 0) {
      console.log(chalk.green('\nTop 5 Opportunities:'));
      opportunities.slice(0, 5).forEach((pool, i) => {
        console.log(`${i + 1}. ${pool.baseToken}/${pool.quoteToken} - ${chalk.bold(pool.pattern)} (Rate: ${pool.rate.toFixed(2)})`);
      });
    }
    
    return true;
  } catch (error) {
    console.error('Error in real-time analysis:', error);
    return false;
  }
}

async function main() {
  console.log(chalk.blue.bold('='.repeat(60)));
  console.log(chalk.blue.bold('         Liquidity Flow Analyzer Tests'));
  console.log(chalk.blue.bold('='.repeat(60)));
  
  // Run pattern detection test first (simulation with mock data)
  await testPatternDetection();
  
  // Then test with real data
  await testRealTimeAnalysis();
  
  console.log(chalk.green.bold('\nTests completed!'));
}

if (require.main === module) {
  main().catch(console.error);
}