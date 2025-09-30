import { config } from '../utils/config';
import { RaydiumClient } from '../blockchain/raydium/RaydiumClient';
import { LiquidityFlowAnalyzer } from '../blockchain/raydium/LiquidityFlowAnalyzer';
import { AlertService } from '../utils/AlertService';
import { LiquidityDataStore, LiquidityRecord } from '../utils/DataPersistence';
import chalk from 'chalk';
import { Connection } from '@solana/web3.js';

// Default Raydium API endpoint if not in config
const RAYDIUM_API_ENDPOINT = "https://api.raydium.io/v2";

export async function monitorLiquidityFlow(duration: number = 300) { // 5 minutes default
    console.log(chalk.blue.bold('\n=== Liquidity Flow Monitoring ===\n'));
    
    // Initialize services - use default API endpoint if not in config
    const raydiumApiEndpoint = (config as any).raydiumApiEndpoint || RAYDIUM_API_ENDPOINT;
    const raydiumClient = new RaydiumClient(raydiumApiEndpoint);
    const analyzer = new LiquidityFlowAnalyzer();
    const alertService = new AlertService({
        minLiquidityRate: 50,         // Lower threshold for testing
        enableConsoleAlerts: true,
        enableFileLogging: true
    });
    const dataStore = new LiquidityDataStore();
    
    console.log(`Starting liquidity monitoring for ${duration} seconds...`);
    console.log('Looking for new pools with strong accumulation patterns...\n');
    console.log(chalk.gray('Alerts will be logged to liquidity-alerts.log\n'));

    const startTime = Date.now();
    const interval = 3000; // 3 second sampling interval
    let iterationCount = 0;

    while ((Date.now() - startTime) < duration * 1000) {
        try {
            iterationCount++;
            
            // Fetch latest pool data
            const pools = await raydiumClient.fetchAllPools();
            
            // Add samples to analyzer
            pools.forEach(pool => analyzer.addPoolSample(pool));
            
            // Get prioritized opportunities
            const opportunities = analyzer.getPrioritizedPools();
            
            // Filter and process new pools (45 mins or newer)
            const newPools = opportunities.filter(p => p.age <= 2700);
            
            // Process each opportunity
            for (const pool of newPools) {
                // Store the data
                const poolData = pools.find(p => p.id === pool.poolId);
                if (poolData) {
                    const totalLiquidity = Number(poolData.baseAmount) + Number(poolData.quoteAmount);
                    
                    // Create record for persistence
                    const record: LiquidityRecord = {
                        poolId: pool.poolId,
                        baseToken: pool.baseToken,
                        quoteToken: pool.quoteToken,
                        timestamp: Date.now(),
                        liquidity: totalLiquidity,
                        liquidityRate: pool.rate,
                        pattern: pool.pattern,
                        age: pool.age
                    };
                    
                    // Store data
                    dataStore.addRecord(record);
                    
                    // Send alert if this is a significant opportunity
                    if (['STRONG_ACCUMULATION', 'ACCELERATING'].includes(pool.pattern)) {
                        alertService.alert({
                            poolId: pool.poolId,
                            baseToken: pool.baseToken,
                            quoteToken: pool.quoteToken,
                            pattern: pool.pattern,
                            rate: pool.rate,
                            age: pool.age,
                            timestamp: Date.now(),
                            totalLiquidity
                        });
                    }
                }
            }

            // Every 10th iteration (30 seconds), print a summary
            if (iterationCount % 10 === 0) {
                printSummary(newPools.length, pools.length);
            }
            
            // Wait for next interval
            await new Promise(resolve => setTimeout(resolve, interval));
            
        } catch (error) {
            console.error('Error during monitoring:', error);
            await new Promise(resolve => setTimeout(resolve, interval));
        }
    }
    
    // Ensure all data is written to storage
    dataStore.cleanup();
    console.log(chalk.blue('\nMonitoring complete. Data persisted to disk.'));
}

// Add the enhanced version of the monitor function
export async function monitorLiquidityFlowEnhanced(
    connection: Connection, 
    duration: number = 300,
    notifier?: any,
    options?: {
        enableRiskAnalysis?: boolean;
        enableMetrics?: boolean;
        transactionAlerts?: boolean;
        riskManagementAlerts?: boolean;
    }
) {
    console.log(chalk.blue.bold('\n=== Enhanced Liquidity Flow Monitoring ===\n'));
    
    // Initialize services with enhanced settings - use default API endpoint if not in config
    const raydiumApiEndpoint = (config as any).raydiumApiEndpoint || RAYDIUM_API_ENDPOINT;
    const raydiumClient = new RaydiumClient(raydiumApiEndpoint);
    const analyzer = new LiquidityFlowAnalyzer();
    const alertService = new AlertService({
        minLiquidityRate: 40,  // More sensitive for enhanced monitoring
        enableConsoleAlerts: true,
        enableFileLogging: true,
        enableTelegramAlerts: !!notifier
    });
    const dataStore = new LiquidityDataStore();
    
    // Print startup info
    console.log(`Starting enhanced liquidity monitoring for ${duration} seconds...`);
    if (options?.enableRiskAnalysis) console.log('Risk analysis enabled');
    if (options?.enableMetrics) console.log('Metrics collection enabled');
    console.log('Looking for new pools with accumulation patterns...\n');
    console.log(chalk.gray('Detailed alerts will be logged to liquidity-alerts.log\n'));

    // Monitoring loop variables
    const startTime = Date.now();
    const interval = 2500; // Faster 2.5 second sampling interval for enhanced monitoring
    let iterationCount = 0;
    let significantPoolsFound = 0;

    // Send initial notification if we have a notifier
    if (notifier) {
        await notifier.sendMessage('🔍 <b>Enhanced Monitoring Started</b>\nNow scanning for significant liquidity movements...');
    }
    
    // Main monitoring loop
    while ((Date.now() - startTime) < duration * 1000) {
        try {
            iterationCount++;
            
            // Fetch latest pool data
            const pools = await raydiumClient.fetchAllPools();
            
            // Enhanced analysis
            pools.forEach(pool => analyzer.addPoolSample(pool));
            
            // Get prioritized opportunities with enhanced criteria
            const opportunities = analyzer.getPrioritizedPools();
            
            // Filter for newer pools (up to 3 hours old for enhanced monitoring)
            const newPools = opportunities.filter(p => p.age <= 10800);
            
            // Process each opportunity
            for (const pool of newPools) {
                const poolData = pools.find(p => p.id === pool.poolId);
                if (!poolData) continue;

                const totalLiquidity = Number(poolData.baseAmount) + Number(poolData.quoteAmount);
                
                // Create record for persistence
                const record: LiquidityRecord = {
                    poolId: pool.poolId,
                    baseToken: pool.baseToken,
                    quoteToken: pool.quoteToken,
                    timestamp: Date.now(),
                    liquidity: totalLiquidity,
                    liquidityRate: pool.rate,
                    pattern: pool.pattern,
                    age: pool.age
                };
                
                // Store data
                dataStore.addRecord(record);
                
                // Enhanced alerting with Telegram integration
                if (pool.rate >= 50 || ['STRONG_ACCUMULATION', 'ACCELERATING'].includes(pool.pattern)) {
                    significantPoolsFound++;
                    
                    // Log alert
                    alertService.alert({
                        poolId: pool.poolId,
                        baseToken: pool.baseToken,
                        quoteToken: pool.quoteToken,
                        pattern: pool.pattern,
                        rate: pool.rate,
                        age: pool.age,
                        timestamp: Date.now(),
                        totalLiquidity
                    });
                    
                    // Send Telegram notification for significant pools
                    if (notifier && (pool.rate >= 75 || pool.pattern === 'STRONG_ACCUMULATION')) {
                        const minutesAgo = Math.round(pool.age / 60);
                        const message = `🔔 <b>Significant Liquidity Pattern</b>\n\n` +
                                        `Pool: ${pool.poolId.substring(0, 8)}...\n` +
                                        `Pattern: ${pool.pattern}\n` +
                                        `Rate: ${pool.rate.toFixed(2)}\n` +
                                        `Age: ${minutesAgo} minutes\n` +
                                        `Liquidity: $${(totalLiquidity / 1000).toFixed(2)}K`;
                        
                        await notifier.sendMessage(message);
                    }
                }
            }
            
            // More frequent status updates
            if (iterationCount % 8 === 0) {
                printEnhancedSummary(newPools.length, pools.length, significantPoolsFound);
            }
            
            // Wait for next interval
            await new Promise(resolve => setTimeout(resolve, interval));
            
        } catch (error) {
            // Fix: Type the error properly
            const errorMessage = error instanceof Error ? error.message : String(error);
            console.error('Error during enhanced monitoring:', errorMessage);
            if (notifier) {
                await notifier.sendMessage(`⚠️ <b>Monitoring Warning</b>\n\nEncountered an error: ${errorMessage}\nContinuing operation...`);
            }
            await new Promise(resolve => setTimeout(resolve, interval));
        }
    }
    
    // Ensure all data is written to storage
    dataStore.cleanup();
    
    // Send completion notification
    if (notifier) {
        await notifier.sendMessage(`✅ <b>Monitoring Complete</b>\n\nScanned ${iterationCount} intervals\nIdentified ${significantPoolsFound} significant patterns\n\nData persisted to disk.`);
    }
    
    console.log(chalk.blue('\nEnhanced monitoring complete. Data persisted to disk.'));
}

function printSummary(newPoolCount: number, totalPoolCount: number): void {
    console.log(chalk.gray(`[${new Date().toLocaleTimeString()}] Monitoring ${totalPoolCount} pools, found ${newPoolCount} new pools with activity`));
}

function printEnhancedSummary(newPoolCount: number, totalPoolCount: number, significantCount: number): void {
    console.log(chalk.cyan(`[${new Date().toLocaleTimeString()}] Monitoring ${totalPoolCount} pools, tracking ${newPoolCount} new pools, found ${significantCount} significant patterns`));
}

async function main() {
    try {
        // Monitor for 5 minutes by default
        await monitorLiquidityFlow(300);
    } catch (error) {
        console.error('Fatal error:', error);
        process.exit(1);
    }
}

if (require.main === module) {
    main().catch(console.error);
}