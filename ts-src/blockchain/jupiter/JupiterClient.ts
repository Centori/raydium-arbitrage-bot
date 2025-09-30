import { Connection, PublicKey, TransactionInstruction } from '@solana/web3.js';
import axios from 'axios';

// Define TokenMeta interface directly in this file since it's not exported from PoolData
export interface TokenMeta {
    address: string;
    symbol: string;
    decimals: number;
    name?: string;
}

export interface JupiterQuoteResponse {
    inputMint: string;
    outputMint: string;
    amount: string;
    outputAmount: string;
    routes: any[];
    priceImpact: number;
    slippageBps: number;
}

export interface JupiterRouteResult {
    swapInstruction: TransactionInstruction;
    inputMint: string;
    outputMint: string;
    amount: string;
    outputAmount: string;
}

export class JupiterClient {
    private connection: Connection;
    private jupiterApiUrl = 'https://quote-api.jup.ag/v6';
    private jupiterPriceApiUrl = 'https://price.jup.ag/v6';
    
    constructor(connection: Connection) {
        this.connection = connection;
    }

    async getPrice(inputMint: string, outputMint: string): Promise<number> {
        try {
            // Use Jupiter v6 price API format
            const response = await axios.get(`${this.jupiterPriceApiUrl}/price`, {
                params: {
                    ids: inputMint,
                    vsToken: outputMint
                },
                timeout: 10000 // 10 second timeout
            });
            
            // Check if response contains the expected data structure
            if (response.data && 
                response.data.data && 
                response.data.data[inputMint] && 
                typeof response.data.data[inputMint].price === 'number') {
                
                return response.data.data[inputMint].price;
            }
            
            console.error('Invalid price data format from Jupiter API:', response.data);
            throw new Error('Invalid price data format from Jupiter API');
        } catch (err: any) {
            console.error(`Error getting Jupiter price for ${inputMint} vs ${outputMint}:`, err.message);
            throw new Error(`Failed to get price from Jupiter: ${err.message}`);
        }
    }

    async getRoute(
        inputMint: string, 
        outputMint: string, 
        amount: string,
        options: { slippageBps: number; onlyDirectRoutes?: boolean } = { slippageBps: 50 }
    ): Promise<JupiterRouteResult | null> {
        try {
            // First get a quote
            const quote = await this.getQuote(inputMint, outputMint, amount, options);
            
            // For example purposes, we're creating a mock instruction
            // In production, you would use Jupiter SDK to get the actual swap instruction
            const swapInstruction = new TransactionInstruction({
                keys: [],
                programId: new PublicKey("JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"),
                data: Buffer.from([])
            });
            
            return {
                swapInstruction,
                inputMint,
                outputMint,
                amount,
                outputAmount: quote.outputAmount
            };
        } catch (error) {
            console.error('Error getting route from Jupiter:', error);
            return null;
        }
    }
    
    async getQuote(
        inputMint: string, 
        outputMint: string, 
        amount: string,
        options: { slippageBps: number; onlyDirectRoutes?: boolean } = { slippageBps: 50 }
    ): Promise<JupiterQuoteResponse> {
        try {
            // Use Jupiter quote API instead of SDK
            const response = await axios.get(`${this.jupiterApiUrl}/quote`, {
                params: {
                    inputMint,
                    outputMint,
                    amount,
                    slippageBps: options.slippageBps,
                    onlyDirectRoutes: options.onlyDirectRoutes || false,
                    platformFeeBps: 0
                }
            });
            if (!response.data || !response.data.outAmount) {
                throw new Error('Invalid response from Jupiter API');
            }
            // Parse price impact as a number to ensure consistent type
            const priceImpact = parseFloat(response.data.priceImpactPct || '0');
            return {
                inputMint,
                outputMint,
                amount,
                outputAmount: response.data.outAmount,
                routes: response.data.routesInfos || [],
                priceImpact,
                slippageBps: options.slippageBps
            };
        } catch (err) {
            console.error('Error getting quote from Jupiter:', err);
            throw err;
        }
    }

    async getTokenInfo(mintAddress: string): Promise<TokenMeta> {
        try {
            const mint = new PublicKey(mintAddress);
            const tokenInfo = await this.connection.getParsedAccountInfo(mint);
            
            if (!tokenInfo.value || !tokenInfo.value.data) {
                throw new Error(`No data found for token ${mintAddress}`);
            }
            
            const parsedData = tokenInfo.value.data as any;
            return {
                address: mintAddress,
                symbol: parsedData.parsed?.info?.symbol || 'Unknown',
                decimals: parsedData.parsed?.info?.decimals || 0,
                name: parsedData.parsed?.info?.name
            };
        } catch (err) {
            console.error(`Error fetching token info for ${mintAddress}:`, err);
            throw err;
        }
    }
}