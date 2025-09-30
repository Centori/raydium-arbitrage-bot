import { PoolOpportunity } from '../blockchain/raydium/EnhancedLiquidityMonitor';
import { Connection, PublicKey, LAMPORTS_PER_SOL } from '@solana/web3.js';
import * as fs from 'fs';

/**
 * Configuration for trade recommendations
 */
export interface TradeConfig {
  solAmount: number;               // Default amount of SOL to use for trades
  walletKeyPath: string;           // Path to wallet keypair for balance checks
  minLiquidityThreshold: number;   // Minimum liquidity threshold
  minScore: number;                // Minimum opportunity score (0-100)
  maxRiskScore: number;            // Maximum risk score to consider (0-100)
  enableAutomatic: boolean;        // Enable automatic recommendations
  profitThresholdPercent: number;  // Minimum expected profit percentage
  maxSlippagePercent: number;      // Maximum acceptable slippage
}

/**
 * Trade recommendation object with decision logic
 */
export interface TradeRecommendation {
  tokenSymbol: string;
  tokenName: string | undefined;
  tokenAddress: string;
  poolId: string;
  liquidityFlow: string;
  recommendation: 'BUY' | 'SELL' | 'HOLD';
  confidence: number;              // 0-100%
  reasoning: string[];
  tradingAmount: number;           // Amount in SOL
  expectedReturn: number;          // Expected return in SOL
  riskLevel: 'LOW' | 'MEDIUM' | 'HIGH';
  decision: 'YES' | 'NO';
  timestamp: number;
}

/**
 * Analyzes liquidity flow patterns and provides trading recommendations
 */
export class TradeRecommender {
  private config: TradeConfig;
  private connection: Connection;
  private walletPubkey: PublicKey | null = null;
  
  constructor(rpcEndpoint: string, config: Partial<TradeConfig> = {}) {
    this.connection = new Connection(rpcEndpoint, 'confirmed');
    
    // Default configuration
    this.config = {
      solAmount: 0.5,              // Default 0.5 SOL per trade
      walletKeyPath: './keys/wallet-keypair.json',
      minLiquidityThreshold: 10000, // Minimum liquidity
      minScore: 75,                // Minimum opportunity score
      maxRiskScore: 40,            // Maximum risk score (lower is better)
      enableAutomatic: false,      // Default to manual approval
      profitThresholdPercent: 5,   // 5% minimum expected profit
      maxSlippagePercent: 2.5,     // 2.5% max slippage
      ...config
    };
    
    // Try to load wallet public key
    this.loadWalletPubkey();
  }
  
  /**
   * Load wallet public key from keypair file
   */
  private loadWalletPubkey(): void {
    try {
      if (fs.existsSync(this.config.walletKeyPath)) {
        const keypairData = JSON.parse(fs.readFileSync(this.config.walletKeyPath, 'utf-8'));
        const pubkeyBytes = keypairData.slice(32, 64); // Extract public key bytes
        this.walletPubkey = new PublicKey(pubkeyBytes);
      }
    } catch (error) {
      console.warn('Could not load wallet keypair:', error);
    }
  }
  
  /**
   * Get wallet SOL balance
   */
  public async getWalletBalance(): Promise<number> {
    if (!this.walletPubkey) {
      return 0;
    }
    
    try {
      const balance = await this.connection.getBalance(this.walletPubkey);
      return balance / LAMPORTS_PER_SOL;
    } catch (error) {
      console.error('Error fetching wallet balance:', error);
      return 0;
    }
  }
  
  /**
   * Set trading amount in SOL
   */
  public setTradingAmount(solAmount: number): void {
    this.config.solAmount = solAmount;
  }
  
  /**
   * Evaluate a detected opportunity and provide a recommendation
   */
  public async evaluateOpportunity(opportunity: PoolOpportunity): Promise<TradeRecommendation> {
    const baseSymbol = opportunity.baseToken;
    const baseToken = opportunity.poolData.baseToken;
    const quoteToken = opportunity.poolData.quoteToken;
    const pattern = opportunity.pattern;
    
    // Calculate confidence based on score and other factors
    let confidence = opportunity.score;
    
    // Adjust confidence based on risk score if available
    if (opportunity.riskScore !== undefined) {
      confidence = Math.max(0, confidence - opportunity.riskScore * 0.5);
    }
    
    // Determine recommendation based on liquidity pattern
    let recommendation: 'BUY' | 'SELL' | 'HOLD' = 'HOLD';
    const reasoning: string[] = [];
    
    if (pattern === 'STRONG_ACCUMULATION' || pattern === 'ACCELERATING') {
      recommendation = 'BUY';
      reasoning.push(`Strong ${pattern.toLowerCase().replace('_', ' ')} pattern detected`);
      reasoning.push(`Liquidity flow rate: +${opportunity.rate.toFixed(2)} units/sec`);
      
      if (opportunity.age < 900) { // Less than 15 minutes old
        reasoning.push('Recently created pool shows early accumulation');
        confidence += 5;
      }
    } else if (pattern === 'DISTRIBUTION') {
      recommendation = 'SELL';
      reasoning.push('Distribution pattern detected (liquidity outflow)');
      reasoning.push(`Liquidity flow rate: ${opportunity.rate.toFixed(2)} units/sec`);
    } else if (pattern === 'DECELERATING') {
      recommendation = 'SELL';
      reasoning.push('Decelerating accumulation pattern suggests potential reversal');
      reasoning.push(`Slowing liquidity flow: ${opportunity.rate.toFixed(2)} units/sec`);
    } else {
      reasoning.push(`${pattern} pattern provides insufficient signal`);
      reasoning.push(`Liquidity flow rate: ${opportunity.rate.toFixed(2)} units/sec`);
    }
    
    // Add risk assessment if available
    if (opportunity.riskScore !== undefined) {
      const riskPercent = opportunity.riskScore;
      if (riskPercent > 70) {
        reasoning.push(`⚠️ HIGH RISK TOKEN: ${riskPercent.toFixed(0)}% risk score`);
        recommendation = 'HOLD';
      } else if (riskPercent > 40) {
        reasoning.push(`⚠️ MEDIUM RISK TOKEN: ${riskPercent.toFixed(0)}% risk score`);
      } else {
        reasoning.push(`✓ Low risk token: ${riskPercent.toFixed(0)}% risk score`);
        confidence += 10;
      }
    }
    
    // Estimate expected return based on liquidity flow
    // (simplified calculation for illustration purposes)
    const liquidityImpact = opportunity.rate / opportunity.totalLiquidity;
    const expectedReturn = this.config.solAmount * (1 + (liquidityImpact * 100));
    const expectedProfit = expectedReturn - this.config.solAmount;
    
    // Determine risk level
    let riskLevel: 'LOW' | 'MEDIUM' | 'HIGH' = 'MEDIUM';
    if (opportunity.riskScore !== undefined) {
      if (opportunity.riskScore > 70) {
        riskLevel = 'HIGH';
      } else if (opportunity.riskScore < 30) {
        riskLevel = 'LOW';
      }
    } else {
      // Without explicit risk score, use age and liquidity as risk indicators
      if (opportunity.age < 300 || opportunity.totalLiquidity < 5000) {
        riskLevel = 'HIGH';
      } else if (opportunity.age > 1800 && opportunity.totalLiquidity > 50000) {
        riskLevel = 'LOW';
      }
    }
    
    // Make final YES/NO decision
    let decision: 'YES' | 'NO' = 'NO';
    
    if (
      recommendation === 'BUY' &&
      confidence >= this.config.minScore &&
      (!opportunity.riskScore || opportunity.riskScore <= this.config.maxRiskScore) &&
      opportunity.totalLiquidity >= this.config.minLiquidityThreshold &&
      expectedProfit / this.config.solAmount * 100 >= this.config.profitThresholdPercent
    ) {
      decision = 'YES';
      
      // Final safety check - do we have enough balance?
      if (this.walletPubkey) {
        const walletBalance = await this.getWalletBalance();
        if (walletBalance < this.config.solAmount) {
          decision = 'NO';
          reasoning.push(`❌ Insufficient SOL balance: ${walletBalance.toFixed(4)} SOL available`);
        } else {
          reasoning.push(`✓ Sufficient SOL balance: ${walletBalance.toFixed(4)} SOL available`);
        }
      }
    }
    
    // Create recommendation object
    return {
      tokenSymbol: baseSymbol,
      tokenName: baseToken.name,
      tokenAddress: baseToken.address,
      poolId: opportunity.poolId,
      liquidityFlow: pattern,
      recommendation,
      confidence,
      reasoning,
      tradingAmount: this.config.solAmount,
      expectedReturn,
      riskLevel,
      decision,
      timestamp: Date.now()
    };
  }
  
  /**
   * Evaluate multiple opportunities and provide recommendations
   */
  public async evaluateOpportunities(opportunities: PoolOpportunity[]): Promise<TradeRecommendation[]> {
    const recommendations: TradeRecommendation[] = [];
    
    for (const opportunity of opportunities) {
      const recommendation = await this.evaluateOpportunity(opportunity);
      recommendations.push(recommendation);
    }
    
    // Sort by confidence (highest first)
    return recommendations.sort((a, b) => b.confidence - a.confidence);
  }
}