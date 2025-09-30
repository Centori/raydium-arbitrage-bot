import axios from 'axios';
import { Connection } from '@solana/web3.js';

export class HeliusClient {
    private connection: Connection;
    private apiEndpoint: string;

    constructor(rpcEndpoint: string, apiEndpoint: string) {
        this.connection = new Connection(rpcEndpoint);
        this.apiEndpoint = apiEndpoint;
    }

    /**
     * Check if the Helius API is accessible
     */
    async checkApiHealth(): Promise<{ status: string }> {
        try {
            // Make a simple request to the API to check connectivity
            const parseEndpoint = this.apiEndpoint.replace('/v0/', '/v0/transactions/');
            const response = await axios.get(`${this.apiEndpoint.split('?')[0]}/healthcheck`, {
                params: {
                    'api-key': this.getApiKey()
                }
            });

            if (response.status === 200) {
                return { status: 'online' };
            } else {
                return { status: `error: ${response.status}` };
            }
        } catch (error) {
            console.error('Error checking Helius API health:', error);
            return { status: 'offline' };
        }
    }

    /**
     * Parse a transaction using Helius enhanced API
     * @param signature Transaction signature to parse
     */
    async parseTransaction(signature: string) {
        const parseEndpoint = `${this.apiEndpoint.replace('/v0/', '/v0/transactions/')}`;
        
        const response = await axios.get(`${parseEndpoint}`, {
            params: {
                'api-key': this.getApiKey(),
                'commitment': 'confirmed',
                'transactions': [signature]
            }
        });
        
        return response.data;
    }

    /**
     * Get transaction history for an address
     * @param address Wallet or contract address
     * @param limit Maximum number of transactions to return
     * @param before Transaction signature to start before (for pagination)
     * @param until Transaction signature to end at (for pagination)
     */
    async getTransactionHistory(
        address: string, 
        limit: number = 10, 
        before: string = '', 
        until: string = ''
    ) {
        const historyEndpoint = `${this.apiEndpoint.replace('/v0/', '/v0/addresses/')}${address}/transactions`;
        
        const params: any = {
            'api-key': this.getApiKey(),
            'commitment': 'confirmed',
            'limit': limit
        };
        
        if (before) params.before = before;
        if (until) params.until = until;
        
        const response = await axios.get(historyEndpoint, { params });
        return response.data;
    }
    
    /**
     * Helper to extract API key from endpoint URL
     */
    private getApiKey(): string {
        const url = new URL(this.apiEndpoint);
        return url.searchParams.get('api-key') || '';
    }
    
    /**
     * Check for NFT mints in a transaction
     * @param signature Transaction signature to check
     */
    async checkForNftMints(signature: string) {
        const parsed = await this.parseTransaction(signature);
        
        // Extract NFT mint events
        const nftMints = [];
        
        if (parsed && Array.isArray(parsed)) {
            for (const tx of parsed) {
                // Look for NFT mint events in the enhanced transaction
                if (tx.events && tx.events.nft) {
                    nftMints.push(...tx.events.nft.filter((event: any) => event.type === 'NFT_MINT'));
                }
            }
        }
        
        return nftMints;
    }
    
    /**
     * Get enriched data for a token
     * @param tokenAddress Mint address of the token
     */
    async getTokenData(tokenAddress: string) {
        const tokenEndpoint = `${this.apiEndpoint.replace('/v0/', '/v0/tokens/')}${tokenAddress}`;
        
        const response = await axios.get(tokenEndpoint, {
            params: {
                'api-key': this.getApiKey()
            }
        });
        
        return response.data;
    }
}