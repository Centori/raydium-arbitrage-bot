import { PublicKey } from '@solana/web3.js';
import { Token, TokenPair } from './TokenPair';

/**
 * Represents an exchange in the Solana ecosystem
 */
export enum Exchange {
    RAYDIUM = 'Raydium',
    ORCA = 'Orca',
    JUPITER = 'Jupiter',
    SERUM = 'Serum',
    SOLEND = 'Solend'
}

/**
 * Interface for representing an arbitrage path
 */
export interface ArbitragePath {
    startToken: Token;
    midToken: Token;
    endToken: Token;
    firstPair: TokenPair;
    secondPair: TokenPair;
    firstExchange: Exchange;
    secondExchange: Exchange;
}

/**
 * Class representing an arbitrage opportunity
 */
export class ArbitrageOpportunity {
    public readonly id: string;
    
    constructor(
        public readonly path: ArbitragePath,
        public readonly inputAmount: number,
        public readonly expectedOutputAmount: number,
        public readonly profitAmount: number,
        public readonly profitPercentage: number,
        public readonly estimatedGasCost: number,
        public readonly timestamp: number = Date.now()
    ) {
        // Generate a unique ID for the opportunity
        this.id = `${path.startToken.symbol}-${path.midToken.symbol}-${path.endToken.symbol}-${timestamp}`;
    }

    /**
     * Calculate the profit after gas costs
     */
    public getProfitAfterGas(): number {
        return this.profitAmount - this.estimatedGasCost;
    }

    /**
     * Check if the opportunity is profitable after gas costs
     */
    public isProfitable(): boolean {
        return this.getProfitAfterGas() > 0;
    }

    /**
     * Get the route description for this arbitrage opportunity
     */
    public getRouteDescription(): string {
        const { startToken, midToken, endToken, firstExchange, secondExchange } = this.path;
        return `${startToken.symbol} → ${midToken.symbol} (${firstExchange}) → ${endToken.symbol} (${secondExchange})`;
    }

    /**
     * Convert to a human-readable format for logging
     */
    public toString(): string {
        return `Arbitrage: ${this.getRouteDescription()}
        Input: ${this.inputAmount} ${this.path.startToken.symbol}
        Output: ${this.expectedOutputAmount} ${this.path.endToken.symbol}
        Profit: ${this.profitAmount} ${this.path.endToken.symbol} (${this.profitPercentage.toFixed(2)}%)
        Gas Cost: ${this.estimatedGasCost} ${this.path.endToken.symbol}
        Net Profit: ${this.getProfitAfterGas()} ${this.path.endToken.symbol}
        Timestamp: ${new Date(this.timestamp).toISOString()}`;
    }
}