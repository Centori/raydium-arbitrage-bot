import axios from 'axios';
import { PoolData } from '../../models/PoolData';

interface RaydiumApiResponse<T> {
    data: T;
    tokens: Record<string, any>;
    success: boolean;
}

export class RaydiumClient {
    private apiEndpoint: string;

    constructor(apiEndpoint: string) {
        this.apiEndpoint = apiEndpoint;
    }

    public async fetchAllPools(): Promise<PoolData[]> {
        try {
            const response = await axios.get<RaydiumApiResponse<any[]>>(this.apiEndpoint + '/pools');
            const data = response.data;

            if (!data.success) {
                throw new Error('Failed to fetch pool data');
            }

            const tokens = data.tokens as Record<string, any>;
            const poolsData = data.data as any[];
            const currentTime = Math.floor(Date.now() / 1000);

            return poolsData.map(pool => ({
                id: pool.id,
                version: pool.version || 1,
                baseToken: {
                    symbol: tokens[pool.baseMint]?.symbol || 'UNKNOWN',
                    mint: pool.baseMint,
                    decimals: tokens[pool.baseMint]?.decimals || 0
                },
                quoteToken: {
                    symbol: tokens[pool.quoteMint]?.symbol || 'UNKNOWN',
                    mint: pool.quoteMint,
                    decimals: tokens[pool.quoteMint]?.decimals || 0
                },
                baseAmount: Number(pool.baseAmount),
                quoteAmount: Number(pool.quoteAmount),
                lpMint: pool.lpMint,
                baseVault: pool.baseVault,
                quoteVault: pool.quoteVault,
                feeRate: pool.feeRate || 30, // Default 0.3%
                status: pool.status || 'online',
                creationTime: pool.creationTime || currentTime,
                timestamp: currentTime
            }));
        } catch (error) {
            console.error('Error fetching Raydium pools:', error);
            return [];
        }
    }
}