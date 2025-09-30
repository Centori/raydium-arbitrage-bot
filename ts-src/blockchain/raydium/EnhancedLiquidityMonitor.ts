import { RaydiumClient } from './RaydiumClient';
import { LiquidityFlowAnalyzer } from './LiquidityFlowAnalyzer';
import { AlertService, AlertConfig } from '../../utils/AlertService';
import { LiquidityDataStore, LiquidityRecord } from '../../utils/DataPersistence';
import { TokenValidator } from '../../utils/TokenValidator';
import { PerformanceMetrics, MetricType } from '../../utils/PerformanceMetrics';
import { MetricsDashboard } from '../../utils/MetricsDashboard';
import { TradeRecommender, TradeConfig, TradeRecommendation } from '../../utils/TradeRecommender';
import { PoolData } from '../../models/PoolData';
import chalk from 'chalk';
import { EventEmitter } from 'events';

export interface MonitoringOptions {
    samplingInterval: number;      // Time between samples in ms
    maxPoolAge: number;            // Max age in seconds to consider a pool "new"
    minLiquidityRate: number;      // Minimum ΔL/Δt to consider significant
    minTotalLiquidity: number;     // Minimum total liquidity value
    rpcEndpoint: string;           // Solana RPC endpoint
    enableRiskAnalysis: boolean;   // Enable token risk analysis
    alertConfig: Partial<AlertConfig>; // Alert configuration
    enableMetrics: boolean;        // Enable performance metrics
    enableDashboard: boolean;      // Enable metrics dashboard
    enableTradeRecommendations: boolean;  // Enable trade recommendations
    tradeConfig: Partial<TradeConfig>;    // Trade configuration
}

export interface PoolOpportunity {
    poolId: string;
    poolData: PoolData;
    baseToken: string;
    quoteToken: string;
    pattern: string;
    rate: number;
    age: number;
    score: number;         // Opportunity score 0-100
    totalLiquidity: number;
    riskScore?: number;    // Risk score if risk analysis enabled
    warnings?: string[];   // Warning messages
    detectionTimestamp: number; // When the opportunity was detected
}

export class EnhancedLiquidityMonitor extends EventEmitter {
    private options: MonitoringOptions;
    private raydiumClient: RaydiumClient;
    private analyzer: LiquidityFlowAnalyzer;
    private alertService: AlertService;
    private dataStore: LiquidityDataStore;
    private tokenValidator: TokenValidator | null = null;
    private metrics: PerformanceMetrics | null = null;
    private dashboard: MetricsDashboard | null = null;
    private tradeRecommender: TradeRecommender | null = null;
    
    private isRunning: boolean = false;
    private monitorInterval: NodeJS.Timeout | null = null;
    private lastAPICallTime: number = 0;
    private lastRecommendations: TradeRecommendation[] = [];
    
    constructor(options?: Partial<MonitoringOptions>) {
        super();
        
        // Default configuration
        this.options = {
            samplingInterval: 3000,         // 3 seconds
            maxPoolAge: 2700,               // 45 minutes
            minLiquidityRate: 50,           // Units/second
            minTotalLiquidity: 1000,        // Minimum liquidity
            rpcEndpoint: 'https://api.mainnet-beta.solana.com',
            enableRiskAnalysis: true,
            alertConfig: {
                enableConsoleAlerts: true,
                enableFileLogging: true
            },
            enableMetrics: true,
            enableDashboard: false,
            enableTradeRecommendations: true,
            tradeConfig: {
                solAmount: 0.5,              // Default 0.5 SOL per trade
                walletKeyPath: './keys/wallet-keypair.json'
            },
            ...options
        };
        
        // Initialize components
        this.raydiumClient = new RaydiumClient(this.options.rpcEndpoint);
        this.analyzer = new LiquidityFlowAnalyzer();
        this.alertService = new AlertService({
            ...this.options.alertConfig,
            minLiquidityRate: this.options.minLiquidityRate,
            maxPoolAge: this.options.maxPoolAge,
            minTotalLiquidity: this.options.minTotalLiquidity
        });
        this.dataStore = new LiquidityDataStore();
        
        // Initialize token validator if risk analysis is enabled
        if (this.options.enableRiskAnalysis) {
            this.tokenValidator = new TokenValidator({
                rpcEndpoint: this.options.rpcEndpoint,
                rugPullDetection: true,
                tokenVerification: true
            });
        }
        
        // Initialize performance metrics if enabled
        if (this.options.enableMetrics) {
            this.metrics = new PerformanceMetrics();
            
            // Initialize dashboard if enabled
            if (this.options.enableDashboard) {
                this.dashboard = new MetricsDashboard(this.metrics);
            }
        }
        
        // Initialize trade recommender if enabled
        if (this.options.enableTradeRecommendations) {
            this.tradeRecommender = new TradeRecommender(
                this.options.rpcEndpoint,
                this.options.tradeConfig
            );
        }
    }
    
    /**
     * Start monitoring liquidity flows
     */
    public async start(): Promise<void> {
        if (this.isRunning) return;
        
        console.log(chalk.blue.bold('\n=== Enhanced Liquidity Flow Monitoring ===\n'));
        console.log(`Starting liquidity monitoring with ${this.options.samplingInterval}ms sampling interval`);
        console.log(`Looking for new pools up to ${this.options.maxPoolAge/60} minutes old`);
        console.log(chalk.gray('Alerts will be logged to liquidity-alerts.log\n'));
        
        if (this.options.enableTradeRecommendations) {
            const solAmount = this.options.tradeConfig.solAmount || 0.5;
            console.log(`Trade recommendations enabled with ${solAmount} SOL preset amount`);
            
            // Check wallet balance if recommender is enabled
            if (this.tradeRecommender) {
                const balance = await this.tradeRecommender.getWalletBalance();
                if (balance > 0) {
                    console.log(chalk.green(`✓ Wallet connected with ${balance.toFixed(4)} SOL available`));
                } else {
                    console.log(chalk.yellow('⚠ Wallet not found or balance is zero. Recommendations will still be provided.'));
                }
            }
        }
        
        // Load verified tokens if risk analysis is enabled
        if (this.tokenValidator) {
            await this.tokenValidator.loadVerifiedTokens();
        }
        
        // Start dashboard if enabled
        if (this.dashboard) {
            this.dashboard.start();
        }
        
        this.isRunning = true;
        let iterationCount = 0;
        
        // Start monitoring loop
        this.monitorInterval = setInterval(async () => {
            try {
                iterationCount++;
                
                // Record metrics for this iteration if enabled
                let endProcessingTimer = this.metrics?.startTimer(MetricType.DATA_PROCESSING);
                let apiCallTimer;
                
                // Fetch latest pool data
                try {
                    this.lastAPICallTime = Date.now();
                    apiCallTimer = this.metrics?.startTimer(MetricType.API_LATENCY);
                    const pools = await this.raydiumClient.fetchAllPools();
                    apiCallTimer && apiCallTimer();
                    
                    // Record the number of pools analyzed
                    this.metrics?.recordMetric(MetricType.POOLS_ANALYZED, pools.length);
                    
                    // Add samples to analyzer
                    let endAnalysisTimer = this.metrics?.startTimer(MetricType.ANALYSIS_TIME);
                    pools.forEach(pool => this.analyzer.addPoolSample(pool));
                    endAnalysisTimer && endAnalysisTimer();
                    
                    // Get prioritized opportunities
                    let endPatternTimer = this.metrics?.startTimer(MetricType.PATTERN_DETECTION);
                    const opportunities = this.analyzer.getPrioritizedPools();
                    endPatternTimer && endPatternTimer();
                    
                    // Filter for new pools
                    const newPools = opportunities.filter(p => p.age <= this.options.maxPoolAge);
                    
                    // Process each opportunity
                    const processedOpportunities: PoolOpportunity[] = [];
                    let accumPatternCount = 0;
                    let strongSignalCount = 0;
                    let alertCount = 0;
                    
                    for (const pool of newPools) {
                        const poolData = pools.find(p => p.id === pool.poolId);
                        if (poolData) {
                            const totalLiquidity = Number(poolData.baseAmount) + Number(poolData.quoteAmount);
                            
                            // Create opportunity object
                            const opportunity: PoolOpportunity = {
                                poolId: pool.poolId,
                                poolData,
                                baseToken: pool.baseToken,
                                quoteToken: pool.quoteToken,
                                pattern: pool.pattern,
                                rate: pool.rate,
                                age: pool.age,
                                score: this.calculateOpportunityScore(pool.pattern, pool.rate),
                                totalLiquidity,
                                detectionTimestamp: Date.now()
                            };
                            
                            // Track accumulation patterns
                            if (pool.pattern === 'ACCELERATING' || pool.pattern === 'STRONG_ACCUMULATION') {
                                accumPatternCount++;
                            }
                            
                            // Track strong signals
                            if (pool.pattern === 'STRONG_ACCUMULATION') {
                                strongSignalCount++;
                            }
                            
                            // Add risk analysis if enabled
                            if (this.tokenValidator) {
                                // Validate base token if it's not a common token
                                if (!['SOL', 'USDC', 'USDT', 'ETH', 'BTC'].includes(pool.baseToken)) {
                                    const baseTokenRisk = await this.tokenValidator.validateToken(
                                        poolData.baseToken.address, 
                                        pool.poolId, 
                                        totalLiquidity
                                    );
                                    
                                    opportunity.riskScore = baseTokenRisk.riskScore;
                                    opportunity.warnings = baseTokenRisk.warnings;
                                }
                            }
                            
                            // Record the opportunity
                            processedOpportunities.push(opportunity);
                            
                            // Store the data
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
                            
                            this.dataStore.addRecord(record);
                            
                            // Send alert for significant opportunities
                            if ((pool.pattern === 'STRONG_ACCUMULATION' || pool.pattern === 'ACCELERATING')
                                && opportunity.score > 75) {
                                
                                // Don't alert on high risk tokens if risk analysis is enabled
                                const riskTooHigh = opportunity.riskScore && opportunity.riskScore > 70;
                                
                                if (!riskTooHigh) {
                                    this.alertService.alert({
                                        poolId: pool.poolId,
                                        baseToken: pool.baseToken,
                                        quoteToken: pool.quoteToken,
                                        pattern: pool.pattern,
                                        rate: pool.rate,
                                        age: pool.age,
                                        timestamp: Date.now(),
                                        totalLiquidity
                                    });
                                    alertCount++;
                                }
                            }
                        }
                    }
                    
                    // Process recommendations if enabled
                    if (this.tradeRecommender && processedOpportunities.length > 0) {
                        this.lastRecommendations = await this.tradeRecommender.evaluateOpportunities(
                            processedOpportunities.filter(opp => opp.score >= 60)
                        );
                        
                        // Emit recommendations event
                        if (this.lastRecommendations.length > 0) {
                            this.emit('recommendations', this.lastRecommendations);
                            
                            // Display top recommendation periodically
                            if (iterationCount % 10 === 0 && this.lastRecommendations.length > 0) {
                                const top = this.lastRecommendations[0];
                                this.displayTradeRecommendation(top);
                            }
                        }
                    }
                    
                    // Update metrics for this iteration
                    if (this.metrics) {
                        this.metrics.recordMetric(MetricType.OPPORTUNITIES_FOUND, processedOpportunities.length);
                        this.metrics.recordMetric(MetricType.ACCUMULATION_DETECTED, accumPatternCount);
                        this.metrics.recordMetric(MetricType.STRONG_SIGNALS, strongSignalCount);
                        this.metrics.recordMetric(MetricType.ALERT_COUNT, alertCount);
                        
                        // Calculate and record signal accuracy
                        // For now, we use a simplified approach based on the score of detected opportunities
                        const avgScore = processedOpportunities.length > 0 
                            ? processedOpportunities.reduce((sum, opp) => sum + opp.score, 0) / processedOpportunities.length
                            : 0;
                        
                        this.metrics.recordMetric(MetricType.SIGNAL_ACCURACY, avgScore);
                    }
                    
                    // Emit opportunities event
                    if (processedOpportunities.length > 0) {
                        this.emit('opportunities', processedOpportunities);
                    }
                    
                    // Print summary every ~30 seconds
                    if (iterationCount % 10 === 0) {
                        const highValueOpps = processedOpportunities.filter(opp => opp.score >= 75);
                        console.log(chalk.gray(`[${new Date().toLocaleTimeString()}] Monitoring ${pools.length} pools, found ${newPools.length} new pools with activity${highValueOpps.length > 0 ? ` (${highValueOpps.length} high value)` : ''}`));
                    }
                    
                } catch (error) {
                    console.error('Error during monitoring:', error);
                    this.emit('error', error);
                    
                    // Record API error in metrics
                    if (apiCallTimer && Date.now() - this.lastAPICallTime > 5000) {
                        apiCallTimer();
                    }
                }
                
                // End data processing timing
                endProcessingTimer && endProcessingTimer();
                
            } catch (error) {
                console.error('Critical error in monitoring loop:', error);
                this.emit('error', error);
            }
        }, this.options.samplingInterval);
    }
    
    /**
     * Stop the monitoring process
     */
    public stop(): void {
        if (!this.isRunning) return;
        
        if (this.monitorInterval) {
            clearInterval(this.monitorInterval);
            this.monitorInterval = null;
        }
        
        // Stop dashboard if running
        if (this.dashboard) {
            this.dashboard.stop();
        }
        
        // Flush metrics if enabled
        if (this.metrics) {
            this.metrics.flushMetrics();
        }
        
        // Ensure all data is persisted
        this.dataStore.cleanup();
        
        this.isRunning = false;
        console.log(chalk.blue('\nLiquidity monitoring stopped. Data persisted to disk.'));
    }
    
    /**
     * Get performance metrics summary
     */
    public getMetricsSummary(): Record<string, any> | null {
        return this.metrics ? this.metrics.getSummary() : null;
    }
    
    /**
     * Show performance dashboard (if metrics are enabled)
     */
    public showDashboard(): void {
        if (!this.metrics) {
            console.log(chalk.yellow('Performance metrics are not enabled. Cannot show dashboard.'));
            return;
        }
        
        if (!this.dashboard) {
            this.dashboard = new MetricsDashboard(this.metrics);
            this.dashboard.start();
        }
    }
    
    /**
     * Hide performance dashboard
     */
    public hideDashboard(): void {
        if (this.dashboard) {
            this.dashboard.stop();
            this.dashboard = null;
        }
    }
    
    /**
     * Get the latest trading recommendations
     */
    public getRecommendations(): TradeRecommendation[] {
        return this.lastRecommendations;
    }
    
    /**
     * Set the SOL amount for trade recommendations
     */
    public setTradingAmount(amount: number): void {
        if (this.tradeRecommender) {
            this.tradeRecommender.setTradingAmount(amount);
            console.log(`Trading amount updated to ${amount} SOL`);
        }
    }
    
    /**
     * Display a trade recommendation in a formatted way
     */
    private displayTradeRecommendation(rec: TradeRecommendation): void {
        const decisionColor = rec.decision === 'YES' ? chalk.green.bold : chalk.red;
        const recColor = rec.recommendation === 'BUY' 
            ? chalk.green.bold
            : rec.recommendation === 'SELL' 
                ? chalk.red.bold 
                : chalk.gray;
        
        console.log('\n------ TRADE RECOMMENDATION ------');
        console.log(`${recColor(rec.recommendation)} ${rec.tokenSymbol} (${rec.tokenName || 'Unknown Token'})`);
        console.log(`Decision: ${decisionColor(rec.decision)}`);
        console.log(`Confidence: ${chalk.yellow(rec.confidence.toFixed(1) + '%')}`);
        console.log(`Amount: ${rec.tradingAmount} SOL`);
        console.log(`Expected Return: ${rec.expectedReturn.toFixed(4)} SOL`);
        console.log(`Risk Level: ${
            rec.riskLevel === 'LOW' 
                ? chalk.green(rec.riskLevel) 
                : rec.riskLevel === 'MEDIUM' 
                    ? chalk.yellow(rec.riskLevel) 
                    : chalk.red(rec.riskLevel)
        }`);
        
        console.log('\nAnalysis:');
        rec.reasoning.forEach(reason => console.log(` - ${reason}`));
        console.log('----------------------------------\n');
    }
    
    /**
     * Calculate an opportunity score based on pattern and rate
     */
    private calculateOpportunityScore(pattern: string, rate: number): number {
        // Base score by pattern
        const patternScores: Record<string, number> = {
            'STRONG_ACCUMULATION': 80,
            'ACCELERATING': 70,
            'STEADY': 50,
            'DECELERATING': 30,
            'NEUTRAL': 20,
            'DISTRIBUTION': 0
        };
        
        // Get base score for pattern
        let score = patternScores[pattern] || 20;
        
        // Adjust based on rate (0-20 points)
        const rateScore = Math.min(20, Math.max(0, rate / 100 * 20));
        score += rateScore;
        
        // Ensure score is in 0-100 range
        return Math.min(100, Math.max(0, score));
    }
}