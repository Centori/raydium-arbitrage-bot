import { PublicKey } from '@solana/web3.js';
import { Token } from './TokenPair';

/**
 * Enum for supported DEXes
 */
export enum DEX {
  RAYDIUM = 'Raydium',
  JUPITER = 'Jupiter',
  ORCA = 'Orca',
  METEORA = 'Meteora',
  DLLM = 'DLLM',
}

/**
 * Route types for arbitrage opportunities
 */
export enum ArbitrageRouteType {
  TWO_HOP = 'two-hop',
  TRIANGULAR = 'triangular',
  MULTI_DEX = 'multi-dex',
}

/**
 * Represents a single step in an arbitrage route
 */
export class ArbitrageStep {
  dex: DEX;
  tokenIn: Token;
  tokenOut: Token;
  amountIn: number;
  amountOut: number;
  slippage: number;
  gasEstimate: number;

  constructor(
    dex: DEX, 
    tokenIn: Token, 
    tokenOut: Token, 
    amountIn: number, 
    amountOut: number, 
    slippage: number = 0.01, 
    gasEstimate: number = 0
  ) {
    this.dex = dex;
    this.tokenIn = tokenIn;
    this.tokenOut = tokenOut;
    this.amountIn = amountIn;
    this.amountOut = amountOut;
    this.slippage = slippage;
    this.gasEstimate = gasEstimate;
  }

  /**
   * Calculate profit in basis points
   */
  profitBps(): number {
    return Math.floor((this.amountOut / this.amountIn - 1) * 10000);
  }

  /**
   * Calculate estimated price impact
   */
  estimatedPriceImpact(): number {
    return this.amountIn / (this.amountIn + this.amountOut);
  }

  /**
   * Convert to JSON-serializable object
   */
  toJSON() {
    return {
      dex: this.dex,
      tokenIn: this.tokenIn.symbol,
      tokenOut: this.tokenOut.symbol,
      amountIn: this.amountIn,
      amountOut: this.amountOut,
      slippage: this.slippage,
      gasEstimate: this.gasEstimate,
      profitBps: this.profitBps(),
      priceImpact: this.estimatedPriceImpact()
    };
  }
}

/**
 * Represents a token path step for flash loan arbitrage
 */
export interface TokenPath {
  token: Token;
  amount: number;
  exchangeType: 'raydium' | 'jupiter' | 'orca';
  poolAddress: PublicKey;
}

/**
 * Represents a complete arbitrage route
 */
export interface ArbitrageRoute {
  entryPool: PublicKey;
  exitPool: PublicKey;
  walletTokenAccount: PublicKey;
}

/**
 * Represents an arbitrage opportunity
 */
export interface ArbitrageOpportunity {
  routeType: ArbitrageRouteType;
  steps: ArbitrageStep[];
  initialAmount: number;
  finalAmount: number;
  expectedProfit: number;
  profitPercentage: number;
  estimatedGas: number;
  tokenPath?: TokenPath[];
  walletTokenAccount?: PublicKey;
  metadata?: Record<string, any>;
}