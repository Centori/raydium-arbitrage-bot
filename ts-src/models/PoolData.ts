/**
 * Token model
 */
export interface Token {
  symbol: string;
  mint: string; // Changed from PublicKey to string
  decimals: number;
}

/**
 * Pool data model representing liquidity pool information
 */
export interface PoolData {
  id: string;
  version: number;
  baseToken: Token;
  quoteToken: Token;
  lpMint: string; // Changed from PublicKey to string
  baseVault: string; // Changed from PublicKey to string
  quoteVault: string; // Changed from PublicKey to string
  baseAmount: number; // Number to preserve precision
  quoteAmount: number; // Number to preserve precision
  feeRate: number; // In basis points (e.g., 30 = 0.3%)
  status: 'online' | 'offline'; // Pool activity status
  creationTime: number;  // Unix timestamp in seconds
  timestamp: number; // Unix timestamp in seconds
}

/**
 * Arbitrage opportunity model
 */
export interface ArbitrageOpportunity {
  sourcePoolId: string;
  targetPoolId: string;
  tokenPath: string[];  // Path of token addresses
  expectedProfit: string;  // In USD, as string to preserve precision
  profitPercentage: number;
  estimatedGasCost: string;
  routeType: string;
  timestamp: number;
}