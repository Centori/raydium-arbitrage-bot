import { PublicKey } from '@solana/web3.js';

/**
 * Represents a token in the Solana ecosystem
 */
export interface Token {
    symbol: string;      // Token symbol e.g., 'SOL', 'USDC'
    name: string;        // Full token name
    address: string;     // Mint address as string
    decimals: number;    // Token decimals
    price?: number;      // Current price in USD (optional)
    logoURI?: string;    // Token logo URI (optional)
}

/**
 * Represents a token pair for trading
 */
export interface TokenPair {
    name: string;           // Pair name, e.g., 'SOL/USDC'
    tokenA: Token;          // First token in the pair
    tokenB: Token;          // Second token in the pair
    poolAddress: string;    // Liquidity pool address
    poolVersion?: number;   // Pool version (for different AMM versions)
    tvl?: number;           // Total value locked in USD
    volume24h?: number;     // 24-hour trading volume
    inverse: () => TokenPair;
    hasToken: (tokenAddress: string) => boolean;
    getCounterpart: (tokenAddress: string) => Token | null;
    sharesTokenWith: (otherPair: TokenPair) => boolean;
}

/**
 * Create a token pair name from two token symbols
 */
export function createPairName(tokenA: Token, tokenB: Token): string {
    return `${tokenA.symbol}/${tokenB.symbol}`;
}

/**
 * Convert a mint address string to PublicKey
 * @param mintAddress Token mint address as string
 * @returns PublicKey object
 */
export function mintToPublicKey(mintAddress: string): PublicKey {
    try {
        return new PublicKey(mintAddress);
    } catch (error) {
        throw new Error(`Invalid mint address: ${mintAddress}. Error: ${error}`);
    }
}

/**
 * Create a TokenPair from raw data
 * @param name Pair name (e.g., "SOL/USDC")
 * @param tokenASymbol Symbol for token A (e.g., "SOL")
 * @param tokenAName Name for token A (e.g., "Solana")
 * @param tokenAAddress Mint address for token A
 * @param tokenADecimals Decimals for token A
 * @param tokenBSymbol Symbol for token B (e.g., "USDC")
 * @param tokenBName Name for token B (e.g., "USD Coin")
 * @param tokenBAddress Mint address for token B
 * @param tokenBDecimals Decimals for token B
 * @param poolAddress Address of the liquidity pool
 * @returns TokenPair object
 */
export function createTokenPair(
    name: string,
    tokenASymbol: string,
    tokenAName: string,
    tokenAAddress: string,
    tokenADecimals: number,
    tokenBSymbol: string,
    tokenBName: string,
    tokenBAddress: string,
    tokenBDecimals: number,
    poolAddress: string
): TokenPair {
    const pair = {
        name,
        tokenA: {
            symbol: tokenASymbol,
            name: tokenAName,
            address: tokenAAddress,
            decimals: tokenADecimals
        },
        tokenB: {
            symbol: tokenBSymbol,
            name: tokenBName,
            address: tokenBAddress,
            decimals: tokenBDecimals
        },
        poolAddress,
        inverse: function() {
            return reverseTokenPair(this);
        },
        hasToken: function(tokenAddress: string) {
            return this.tokenA.address === tokenAddress || this.tokenB.address === tokenAddress;
        },
        getCounterpart: function(tokenAddress: string) {
            if (this.tokenA.address === tokenAddress) return this.tokenB;
            if (this.tokenB.address === tokenAddress) return this.tokenA;
            return null;
        },
        sharesTokenWith: function(otherPair: TokenPair) {
            return this.hasToken(otherPair.tokenA.address) || this.hasToken(otherPair.tokenB.address);
        }
    };
    return pair;
}

/**
 * Reverse a token pair (swap token A and token B)
 * @param pair Original token pair
 * @returns Reversed token pair
 */
export function reverseTokenPair(pair: TokenPair): TokenPair {
    return {
        name: `${pair.tokenB.symbol}/${pair.tokenA.symbol}`,
        tokenA: pair.tokenB,
        tokenB: pair.tokenA,
        poolAddress: pair.poolAddress,
        inverse: function() {
            return reverseTokenPair(this);
        },
        hasToken: function(tokenAddress: string) {
            return this.tokenA.address === tokenAddress || this.tokenB.address === tokenAddress;
        },
        getCounterpart: function(tokenAddress: string) {
            if (this.tokenA.address === tokenAddress) return this.tokenB;
            if (this.tokenB.address === tokenAddress) return this.tokenA;
            return null;
        },
        sharesTokenWith: function(otherPair: TokenPair) {
            return this.hasToken(otherPair.tokenA.address) || this.hasToken(otherPair.tokenB.address);
        }
    };
}