import { config } from '../utils/config';
import { RaydiumClient } from '../blockchain/raydium/RaydiumClient';
import { Connection } from '@solana/web3.js';
import { performance } from 'perf_hooks';
import chalk from 'chalk';

interface PerformanceMetrics {
    operation: string;
    startTime: number;
    endTime: number;
    duration: number;
}

class PoolAnalyzer {
    private raydiumClient: RaydiumClient;
    private metrics: PerformanceMetrics[] = [];

    constructor() {
        this.raydiumClient = new RaydiumClient(config.rpcEndpoint);
    }

    private measurePerformance(operation: string, startTime: number): number {
        const endTime = performance.now();
        const duration = endTime - startTime;
        this.metrics.push({ operation, startTime, endTime, duration });
        return duration;
    }

    async analyzePoolMetrics(minLiquidity: number = 10000): Promise<void> {
        console.log(chalk.blue.bold('\n=== Pool Analysis Metrics ===\n'));

        // Test pool fetching performance
        const fetchStart = performance.now();
        const poolAnalysis = await this.raydiumClient.analyzePools(minLiquidity);
        const fetchTime = this.measurePerformance('Pool Fetching & Analysis', fetchStart);

        // Print results
        console.log(chalk.green('Pool Statistics:'));
        console.log(`Total Pools Found: ${poolAnalysis.totalPools}`);
        console.log(`Active Pools: ${poolAnalysis.activePools}`);
        console.log(`Average Fee Rate: ${(poolAnalysis.averageFeeRate / 100).toFixed(2)}%`);
        console.log(`Analysis Time: ${fetchTime.toFixed(2)}ms`);

        // Print top pools
        console.log(chalk.green('\nTop Pools by Liquidity:'));
        poolAnalysis.topPoolsByLiquidity.forEach((pool, i) => {
            const totalLiquidity = Number(pool.baseAmount) + Number(pool.quoteAmount);
            console.log(chalk.yellow(`\n${i + 1}. Pool ID: ${pool.id}`));
            console.log(`   Pair: ${pool.baseToken.symbol}/${pool.quoteToken.symbol}`);
            console.log(`   Total Liquidity: $${totalLiquidity.toLocaleString()}`);
            console.log(`   Fee Rate: ${(pool.feeRate / 100).toFixed(2)}%`);
            console.log(`   Status: ${pool.status}`);
        });
    }

    async testLatencyDistribution(samples: number = 10): Promise<void> {
        console.log(chalk.blue.bold('\n=== Latency Analysis ===\n'));
        
        const latencies: number[] = [];
        console.log(`Running ${samples} sample operations...`);

        for (let i = 0; i < samples; i++) {
            const start = performance.now();
            await this.raydiumClient.fetchAllPools();
            const end = performance.now();
            latencies.push(end - start);
            process.stdout.write('.');
        }

        // Calculate statistics
        const avgLatency = latencies.reduce((a, b) => a + b, 0) / latencies.length;
        const minLatency = Math.min(...latencies);
        const maxLatency = Math.max(...latencies);
        const sortedLatencies = [...latencies].sort((a, b) => a - b);
        const p95Latency = sortedLatencies[Math.floor(sortedLatencies.length * 0.95)];
        const p99Latency = sortedLatencies[Math.floor(sortedLatencies.length * 0.99)];

        console.log(chalk.green('\n\nLatency Statistics:'));
        console.log(`Average: ${avgLatency.toFixed(2)}ms`);
        console.log(`Min: ${minLatency.toFixed(2)}ms`);
        console.log(`Max: ${maxLatency.toFixed(2)}ms`);
        console.log(`P95: ${p95Latency.toFixed(2)}ms`);
        console.log(`P99: ${p99Latency.toFixed(2)}ms`);
    }

    async monitorPoolChanges(duration: number = 60): Promise<void> {
        console.log(chalk.blue.bold('\n=== Pool Change Monitoring ===\n'));
        console.log(`Monitoring pools for ${duration} seconds...`);

        const snapshots: Map<string, any>[] = [];
        const interval = 10; // Seconds between checks
        const iterations = Math.floor(duration / interval);

        for (let i = 0; i < iterations; i++) {
            const startTime = performance.now();
            const pools = await this.raydiumClient.fetchAllPools();
            
            // Create snapshot
            const snapshot = new Map(pools.map(pool => [
                pool.id,
                {
                    baseAmount: pool.baseAmount,
                    quoteAmount: pool.quoteAmount,
                    timestamp: Date.now()
                }
            ]));

            snapshots.push(snapshot);

            // Compare with previous snapshot if available
            if (i > 0) {
                const prevSnapshot = snapshots[i - 1];
                let changes = 0;

                for (const [poolId, currentData] of snapshot) {
                    const prevData = prevSnapshot.get(poolId);
                    if (prevData && (
                        currentData.baseAmount !== prevData.baseAmount ||
                        currentData.quoteAmount !== prevData.quoteAmount
                    )) {
                        changes++;
                    }
                }

                console.log(`Snapshot ${i + 1}: ${changes} pools changed`);
            }

            // Wait for next interval
            const elapsed = (performance.now() - startTime) / 1000;
            if (elapsed < interval) {
                await new Promise(resolve => setTimeout(resolve, (interval - elapsed) * 1000));
            }
        }
    }
}

async function main() {
    const analyzer = new PoolAnalyzer();

    try {
        // Run full analysis
        await analyzer.analyzePoolMetrics();
        
        // Test latency
        await analyzer.testLatencyDistribution(5);
        
        // Monitor changes
        await analyzer.monitorPoolChanges(30);

    } catch (error) {
        console.error('Error running analysis:', error);
        process.exit(1);
    }
}

if (require.main === module) {
    main().catch(console.error);
}