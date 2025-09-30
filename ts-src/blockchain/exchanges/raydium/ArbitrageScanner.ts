import { Connection, PublicKey } from '@solana/web3.js';
import { Token, TokenPair } from '../../models/TokenPair';
import { ArbitrageOpportunity, ArbitragePath, Exchange } from '../../models/ArbitrageOpportunity';
import { RaydiumSwap } from './RaydiumSwap';

/**
 * Configuration for the arbitrage scanner
 */
export interface ArbitrageScannerConfig {
    minProfitPercentage: number;  // Minimum profit percentage to consider an opportunity valid
    maxInputAmount: number;       // Maximum input amount for a trade
    gasEstimateInSOL: number;     // Estimated gas cost in SOL
    slippageTolerance: number;    // Slippage tolerance in percentage (1 = 1%)
    scanIntervalMs: number;       // Scan interval in milliseconds
}

/**
 * Default scanner configuration
 */
const DEFAULT_CONFIG: ArbitrageScannerConfig = {
    minProfitPercentage: 1.0,     // 1% minimum profit
    maxInputAmount: 1000,         // 1000 units of token
    gasEstimateInSOL: 0.01,       // 0.01 SOL for gas
    slippageTolerance: 1.0,       // 1% slippage tolerance
    scanIntervalMs: 10000,        // Scan every 10 seconds
};

/**
 * Scans for arbitrage opportunities across Raydium pools
 */
export class ArbitrageScanner {
    private config: ArbitrageScannerConfig;
    private raydiumSwap: RaydiumSwap;
    private tokenPairs: TokenPair[] = [];
    private isScanning: boolean = false;
    private scanInterval: NodeJS.Timeout | null = null;
    
    /**
     * Create a new ArbitrageScanner instance
     * @param connection The Solana connection
     * @param config Scanner configuration
     */
    constructor(
        private connection: Connection,
        config: Partial<ArbitrageScannerConfig> = {}
    ) {
        this.config = { ...DEFAULT_CONFIG, ...config };
        this.raydiumSwap = new RaydiumSwap(connection);
    }
    
    /**
     * Set the token pairs to scan for arbitrage opportunities
     * @param pairs Array of token pairs
     */
    public setTokenPairs(pairs: TokenPair[]): void {
        this.tokenPairs = pairs;
        console.log(`Loaded ${pairs.length} token pairs for arbitrage scanning`);
    }
    
    /**
     * Start scanning for arbitrage opportunities
     * @param callback Callback function to handle found opportunities
     */
    public startScanning(callback: (opportunity: ArbitrageOpportunity) => void): void {
        if (this.isScanning) {
            console.log('Scanner is already running');
            return;
        }
        
        if (this.tokenPairs.length === 0) {
            console.error('No token pairs configured for scanning');
            return;
        }
        
        this.isScanning = true;
        console.log(`Starting arbitrage scanner with ${this.tokenPairs.length} token pairs`);
        
        // Run initial scan immediately
        this.scanForOpportunities().then(opportunities => {
            opportunities.forEach(opportunity => callback(opportunity));
        });
        
        // Schedule regular scans
        this.scanInterval = setInterval(async () => {
            const opportunities = await this.scanForOpportunities();
            opportunities.forEach(opportunity => callback(opportunity));
        }, this.config.scanIntervalMs);
    }
    
    /**
     * Stop scanning for arbitrage opportunities
     */
    public stopScanning(): void {
        if (!this.isScanning) {
            return;
        }
        
        if (this.scanInterval) {
            clearInterval(this.scanInterval);
            this.scanInterval = null;
        }
        
        this.isScanning = false;
        console.log('Stopped arbitrage scanner');
    }
    
    /**
     * Scan for arbitrage opportunities across configured token pairs
     * @returns Array of arbitrage opportunities
     */
    public async scanForOpportunities(): Promise<ArbitrageOpportunity[]> {
        console.log('Scanning for arbitrage opportunities...');
        const opportunities: ArbitrageOpportunity[] = [];
        
        // Build triangular arbitrage paths
        const paths = this.buildArbitragePaths();
        console.log(`Generated ${paths.length} potential arbitrage paths`);
        
        // Check each path for profitable opportunities
        for (const path of paths) {
            try {
                const opportunity = await this.checkPathForArbitrage(path);
                if (opportunity && opportunity.isProfitable()) {
                    opportunities.push(opportunity);
                    console.log(`Found profitable opportunity: ${opportunity.getRouteDescription()}`);
                }
            } catch (error) {
                console.error(`Error checking path ${path.startToken.symbol}-${path.midToken.symbol}-${path.endToken.symbol}: ${error}`);
            }
        }
        
        console.log(`Found ${opportunities.length} profitable arbitrage opportunities`);
        return opportunities;
    }
    
    /**
     * Build possible triangular arbitrage paths from available token pairs
     */
    private buildArbitragePaths(): ArbitragePath[] {
        const paths: ArbitragePath[] = [];
        
        // Find all potential triangular paths
        for (const firstPair of this.tokenPairs) {
            const tokenA = firstPair.tokenA;
            const tokenB = firstPair.tokenB;
            
            // For each token in the first pair, check if it can form a triangle
            // First try tokenA -> tokenB -> tokenA
            const secondPairsForB = this.tokenPairs.filter(pair => 
                (pair.tokenA.address === tokenB.address || pair.tokenB.address === tokenB.address) && 
                (pair.tokenA.address === tokenA.address || pair.tokenB.address === tokenA.address) &&
                pair.poolAddress !== firstPair.poolAddress
            );
            
            for (const secondPair of secondPairsForB) {
                paths.push({
                    startToken: tokenA,
                    midToken: tokenB,
                    endToken: tokenA,
                    firstPair,
                    secondPair,
                    firstExchange: Exchange.RAYDIUM,
                    secondExchange: Exchange.RAYDIUM
                });
            }
            
            // Then try tokenB -> tokenA -> tokenB
            const secondPairsForA = this.tokenPairs.filter(pair => 
                (pair.tokenA.address === tokenA.address || pair.tokenB.address === tokenA.address) && 
                (pair.tokenA.address === tokenB.address || pair.tokenB.address === tokenB.address) &&
                pair.poolAddress !== firstPair.poolAddress
            );
            
            for (const secondPair of secondPairsForA) {
                paths.push({
                    startToken: tokenB,
                    midToken: tokenA,
                    endToken: tokenB,
                    firstPair,
                    secondPair,
                    firstExchange: Exchange.RAYDIUM,
                    secondExchange: Exchange.RAYDIUM
                });
            }
        }
        
        return paths;
    }
    
    /**
     * Check if a specific path offers an arbitrage opportunity
     */
    private async checkPathForArbitrage(path: ArbitragePath): Promise<ArbitrageOpportunity | null> {
        const { startToken, midToken, endToken, firstPair, secondPair } = path;
        const inputAmount = this.config.maxInputAmount;
        
        try {
            // Simulate the first swap
            const midTokenAmount = await this.raydiumSwap.getSwapQuote(
                startToken,
                midToken,
                inputAmount,
                new PublicKey(firstPair.poolAddress)
            );
            
            // Simulate the second swap
            const outputAmount = await this.raydiumSwap.getSwapQuote(
                midToken,
                endToken,
                midTokenAmount,
                new PublicKey(secondPair.poolAddress)
            );
            
            // Calculate profit
            const profitAmount = outputAmount - inputAmount;
            const profitPercentage = (profitAmount / inputAmount) * 100;
            
            // Estimate gas cost in terms of the token
            let estimatedGasCost = this.config.gasEstimateInSOL;
            if (startToken.symbol !== 'SOL' && startToken.price && startToken.price > 0) {
                // Convert SOL gas cost to token cost
                const solPrice = 1; // Should get actual SOL price in production
                estimatedGasCost = (this.config.gasEstimateInSOL * solPrice) / startToken.price;
            }
            
            // Create opportunity if profitable
            if (profitPercentage >= this.config.minProfitPercentage) {
                return new ArbitrageOpportunity(
                    path,
                    inputAmount,
                    outputAmount,
                    profitAmount,
                    profitPercentage,
                    estimatedGasCost
                );
            }
            
            return null;
        } catch (error) {
            console.error(`Error checking arbitrage for path: ${error}`);
            return null;
        }
    }
    
    /**
     * Update the scanner configuration
     */
    public updateConfig(config: Partial<ArbitrageScannerConfig>): void {
        this.config = { ...this.config, ...config };
        console.log('Updated arbitrage scanner configuration', this.config);
    }
}