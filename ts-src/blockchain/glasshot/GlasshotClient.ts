import axios, { AxiosRequestConfig } from 'axios';
import { config } from '../../utils/config';

/**
 * Client for the Glasshot API service
 * API docs: https://docs.glasshot.io/
 */
export class GlasshotClient {
    private apiKey: string;
    private baseUrl: string;
    private timeout: number;
    private maxRetries: number;
    private retryDelay: number;

    constructor(
        apiKey: string = config.glasshotApiKey,
        baseUrl: string = config.glasshotApiUrl,
        timeout: number = 10000,
        maxRetries: number = config.maxRetries,
        retryDelay: number = config.retryDelay
    ) {
        this.apiKey = apiKey;
        this.baseUrl = baseUrl;
        this.timeout = timeout;
        this.maxRetries = maxRetries;
        this.retryDelay = retryDelay;

        if (!this.apiKey) {
            console.warn('No Glasshot API key provided. Some functionality may be limited.');
        }
        
        console.log(`Using Glasshot API at: ${this.baseUrl}`);
    }

    /**
     * Check if the Glasshot API is accessible
     */
    async checkApiHealth(): Promise<{ status: string; message?: string }> {
        try {
            const response = await this.makeApiRequest(`${this.baseUrl}/health`);
            return { status: 'online' };
        } catch (error: any) {
            const errorMessage = error.message || 'Unknown error';
            console.error('Error checking Glasshot API health:', errorMessage);
            return { 
                status: 'offline', 
                message: `Connection failed: ${errorMessage}` 
            };
        }
    }

    /**
     * Get real-time token price data
     * @param tokenAddress Mint address of the token
     */
    async getTokenPrice(tokenAddress: string): Promise<any> {
        try {
            return await this.makeApiRequest(`${this.baseUrl}/token/${tokenAddress}/price`);
        } catch (error) {
            console.error(`Error fetching token price for ${tokenAddress}:`, error);
            throw error;
        }
    }

    /**
     * Get liquidity pool data for a specific pool address
     * @param poolAddress Address of the pool
     */
    async getPoolData(poolAddress: string): Promise<any> {
        try {
            return await this.makeApiRequest(`${this.baseUrl}/pool/${poolAddress}`);
        } catch (error) {
            console.error(`Error fetching pool data for ${poolAddress}:`, error);
            throw error;
        }
    }

    /**
     * Analyze a transaction for arbitrage opportunities or other patterns
     * @param signature Transaction signature to analyze
     */
    async analyzeTransaction(signature: string): Promise<any> {
        try {
            return await this.makeApiRequest(`${this.baseUrl}/transaction/${signature}/analysis`);
        } catch (error) {
            console.error(`Error analyzing transaction ${signature}:`, error);
            throw error;
        }
    }

    /**
     * Get token market data including volume, market cap, etc.
     * @param tokenAddress Mint address of the token
     */
    async getTokenMarketData(tokenAddress: string): Promise<any> {
        try {
            return await this.makeApiRequest(`${this.baseUrl}/token/${tokenAddress}/market`);
        } catch (error) {
            console.error(`Error fetching market data for ${tokenAddress}:`, error);
            throw error;
        }
    }

    /**
     * Get recent transactions for a token or wallet
     * @param address Token or wallet address
     * @param limit Maximum number of transactions to return
     */
    async getRecentTransactions(address: string, limit: number = 10): Promise<any> {
        try {
            return await this.makeApiRequest(`${this.baseUrl}/address/${address}/transactions`, { limit });
        } catch (error) {
            console.error(`Error fetching transactions for ${address}:`, error);
            throw error;
        }
    }

    /**
     * Helper to set auth headers for API requests
     */
    private getHeaders() {
        return {
            'Authorization': `Bearer ${this.apiKey}`,
            'Content-Type': 'application/json'
        };
    }

    /**
     * Make an API request with retry logic
     * @param url API endpoint URL
     * @param params Optional query parameters
     */
    private async makeApiRequest(url: string, params: Record<string, any> = {}): Promise<any> {
        let retries = 0;
        let lastError: any;

        while (retries <= this.maxRetries) {
            try {
                const options: AxiosRequestConfig = {
                    headers: this.getHeaders(),
                    timeout: this.timeout,
                    params: Object.keys(params).length > 0 ? params : undefined
                };

                const response = await axios.get(url, options);
                return response.data;
            } catch (error: any) {
                lastError = error;
                
                // Don't retry if it's an authentication or validation error
                if (error.response && (error.response.status === 401 || error.response.status === 400)) {
                    throw error;
                }

                retries++;
                
                // Log retry attempt
                if (retries <= this.maxRetries) {
                    console.warn(`API request failed, retrying (${retries}/${this.maxRetries}): ${url}`);
                    // Wait before retrying
                    await new Promise(resolve => setTimeout(resolve, this.retryDelay));
                }
            }
        }

        // If we reached here, all retries failed
        const errorMessage = lastError?.message || 'Unknown error';
        const statusCode = lastError?.response?.status || 'no status';
        console.error(`All API request attempts failed (${statusCode}): ${errorMessage}`);
        throw lastError;
    }
}