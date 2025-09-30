import { PoolData } from '../../models/PoolData';

interface LiquiditySample {
    timestamp: number;
    liquidity: number;
}

interface PoolSnapshot {
    poolId: string;
    baseToken: string;
    quoteToken: string;
    creationTime: number;
    samples: LiquiditySample[];
}

// Define a type for the pool analysis result
interface PoolAnalysisResult {
    poolId: string;
    pattern: string;
    rate: number;
    age: number;
    baseToken: string;
    quoteToken: string;
}

export class LiquidityFlowAnalyzer {
    private poolSnapshots: Map<string, PoolSnapshot> = new Map();
    private readonly WINDOW_SIZE = 300; // 5 minutes
    private readonly MAX_TOKEN_AGE = 45 * 60; // 45 minutes in seconds
    private readonly SAMPLE_INTERVAL = 3; // 3 seconds between samples

    constructor() {}

    public addPoolSample(pool: PoolData): void {
        const currentTime = Date.now() / 1000; // Convert to seconds
        const poolId = pool.id;
        const totalLiquidity = Number(pool.baseAmount) + Number(pool.quoteAmount);

        if (!this.poolSnapshots.has(poolId)) {
            // Initialize new pool tracking
            this.poolSnapshots.set(poolId, {
                poolId,
                baseToken: pool.baseToken.symbol,
                quoteToken: pool.quoteToken.symbol,
                creationTime: currentTime,
                samples: []
            });
        }

        const snapshot = this.poolSnapshots.get(poolId)!;
        
        // Add new sample
        snapshot.samples.push({
            timestamp: currentTime,
            liquidity: totalLiquidity
        });

        // Maintain rolling window
        while (snapshot.samples.length > 0 && 
               currentTime - snapshot.samples[0].timestamp > this.WINDOW_SIZE) {
            snapshot.samples.shift();
        }
    }

    public calculateRate(poolId: string, windowSeconds: number): number {
        const snapshot = this.poolSnapshots.get(poolId);
        if (!snapshot || snapshot.samples.length < 2) return 0;

        const currentTime = Date.now() / 1000;
        const windowStart = currentTime - windowSeconds;
        
        // Get samples within window
        const windowSamples = snapshot.samples.filter(s => s.timestamp >= windowStart);
        if (windowSamples.length < 2) return 0;

        // Calculate rate using linear regression
        const xValues = windowSamples.map(s => s.timestamp - windowSamples[0].timestamp);
        const yValues = windowSamples.map(s => s.liquidity);
        
        return this.calculateLinearRegression(xValues, yValues);
    }

    public detectAccumulation(poolId: string): {
        pattern: string;
        rate: number;
        age: number;
    } {
        const snapshot = this.poolSnapshots.get(poolId);
        if (!snapshot) return { pattern: "UNKNOWN", rate: 0, age: 0 };

        const currentTime = Date.now() / 1000;
        const poolAge = currentTime - snapshot.creationTime;

        // Only analyze pools younger than MAX_TOKEN_AGE
        if (poolAge > this.MAX_TOKEN_AGE) {
            return { pattern: "TOO_OLD", rate: 0, age: poolAge };
        }

        const shortRate = this.calculateRate(poolId, 15);    // 15-second window
        const mediumRate = this.calculateRate(poolId, 60);   // 1-minute window
        const longRate = this.calculateRate(poolId, 300);    // 5-minute window

        // Detect accumulation patterns
        if (shortRate > mediumRate && mediumRate > longRate && longRate > 0) {
            return { pattern: "STRONG_ACCUMULATION", rate: shortRate, age: poolAge };
        } else if (shortRate > mediumRate && mediumRate > 0) {
            return { pattern: "ACCELERATING", rate: shortRate, age: poolAge };
        } else if (shortRate > 0 && mediumRate > 0) {
            return { pattern: "STEADY", rate: shortRate, age: poolAge };
        } else if (shortRate > 0 && (mediumRate - longRate) < 0) {
            return { pattern: "DECELERATING", rate: shortRate, age: poolAge };
        } else if (shortRate < 0) {
            return { pattern: "DISTRIBUTION", rate: shortRate, age: poolAge };
        }

        return { pattern: "NEUTRAL", rate: shortRate, age: poolAge };
    }

    private calculateLinearRegression(x: number[], y: number[]): number {
        const n = x.length;
        let sumX = 0, sumY = 0, sumXY = 0, sumXX = 0;
        
        for (let i = 0; i < n; i++) {
            sumX += x[i];
            sumY += y[i];
            sumXY += x[i] * y[i];
            sumXX += x[i] * x[i];
        }

        // Calculate slope (rate of change)
        return (n * sumXY - sumX * sumY) / (n * sumXX - sumX * sumX);
    }

    public getPrioritizedPools(): Array<PoolAnalysisResult> {
        const results: PoolAnalysisResult[] = [];
        
        for (const [poolId, snapshot] of this.poolSnapshots) {
            const analysis = this.detectAccumulation(poolId);
            if (analysis.pattern !== "TOO_OLD" && analysis.pattern !== "UNKNOWN") {
                results.push({
                    poolId,
                    pattern: analysis.pattern,
                    rate: analysis.rate,
                    age: analysis.age,
                    baseToken: snapshot.baseToken,
                    quoteToken: snapshot.quoteToken
                });
            }
        }

        // Sort by priority (STRONG_ACCUMULATION > ACCELERATING > STEADY)
        return results.sort((a, b) => {
            const patternPriority: Record<string, number> = {
                "STRONG_ACCUMULATION": 5,
                "ACCELERATING": 4,
                "STEADY": 3,
                "DECELERATING": 2,
                "NEUTRAL": 1,
                "DISTRIBUTION": 0
            };
            
            return (patternPriority[b.pattern] || 0) - (patternPriority[a.pattern] || 0) ||
                   b.rate - a.rate;
        });
    }
}