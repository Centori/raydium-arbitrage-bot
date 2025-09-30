import { Connection } from '@solana/web3.js';
import { PublicKey } from '@solana/web3.js';
import { Liquidity, LiquidityPoolKeys } from '@raydium-io/raydium-sdk';

/**
 * Cache for Raydium pool data to avoid repeated fetches
 */
export class RaydiumPoolCache {
    private static instance: RaydiumPoolCache;
    private poolKeysCache: Map<string, LiquidityPoolKeys> = new Map();
    
    private constructor(private connection: Connection) {}
    
    /**
     * Get the singleton instance of the pool cache
     */
    public static getInstance(connection: Connection): RaydiumPoolCache {
        if (!RaydiumPoolCache.instance) {
            RaydiumPoolCache.instance = new RaydiumPoolCache(connection);
        }
        return RaydiumPoolCache.instance;
    }
    
    /**
     * Get pool keys for a specific pool address, using cache if available
     */
    public async getPoolKeys(poolAddress: PublicKey): Promise<LiquidityPoolKeys> {
        const poolKey = poolAddress.toString();
        
        // Check if pool keys are in cache
        if (this.poolKeysCache.has(poolKey)) {
            console.log(`Using cached pool keys for ${poolKey}`);
            return this.poolKeysCache.get(poolKey)!;
        }
        
        console.log(`Fetching pool keys for ${poolKey}`);
        
        try {
            // Fetch all pools and filter the one we need
            // In a production implementation, you might want to optimize this
            const allPoolKeys = await Liquidity.fetchAllPoolKeys(this.connection);
            
            const poolKeys = allPoolKeys.find(
                (keys) => keys.id.toString() === poolKey
            );
            
            if (!poolKeys) {
                throw new Error(`Pool not found: ${poolKey}`);
            }
            
            // Cache the result
            this.poolKeysCache.set(poolKey, poolKeys);
            
            return poolKeys;
        } catch (error) {
            console.error(`Failed to fetch pool keys: ${error}`);
            throw new Error(`Failed to fetch pool keys: ${error}`);
        }
    }
    
    /**
     * Clear the cache
     */
    public clearCache(): void {
        this.poolKeysCache.clear();
    }
    
    /**
     * Prefetch and cache keys for multiple pools
     */
    public async prefetchPoolKeys(poolAddresses: PublicKey[]): Promise<void> {
        try {
            const allPoolKeys = await Liquidity.fetchAllPoolKeys(this.connection);
            
            for (const poolAddress of poolAddresses) {
                const poolKey = poolAddress.toString();
                const poolKeys = allPoolKeys.find(
                    (keys) => keys.id.toString() === poolKey
                );
                
                if (poolKeys) {
                    this.poolKeysCache.set(poolKey, poolKeys);
                    console.log(`Cached pool keys for ${poolKey}`);
                }
            }
        } catch (error) {
            console.error(`Failed to prefetch pool keys: ${error}`);
        }
    }
}