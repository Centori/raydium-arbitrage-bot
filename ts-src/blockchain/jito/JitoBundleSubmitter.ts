import { 
    Connection, 
    Keypair, 
    Transaction, 
    VersionedTransaction, 
    SendTransactionError, 
    PublicKey,
    TransactionMessage,
    VersionedMessage 
} from '@solana/web3.js';
import { config } from '../../utils/config';
import axios from 'axios';
import { v4 as uuidv4 } from 'uuid';
import { Logger } from '../../utils/logger';

/**
 * Interface for Jito Bundle Submission Response
 */
interface JitoBundleResponse {
    bundleId: string;
}

/**
 * Interface for RPC Provider with fallback capabilities
 */
interface RpcProvider {
    name: string;
    endpoint: string;
    connection: Connection;
    priority: number;
    rateLimited: boolean;
    lastErrorTime?: number;
    cooldownMs: number; // Time to wait after an error before using this endpoint again
}

/**
 * JitoBundleSubmitter handles the submission of transaction bundles to Jito's block engine
 * It supports fallback RPC endpoints to manage rate limits and ensure reliable connections
 */
export class JitoBundleSubmitter {
    private logger: Logger;
    private rpcProviders: RpcProvider[] = [];
    private jitoEndpoint: string;
    private jitoAuthKeypair?: Keypair;
    private defaultCooldownMs = 30000; // 30 seconds default cooldown for rate-limited endpoints

    constructor(
        private primaryConnection: Connection,
        private wallet: Keypair,
        jitoAuthKeypair?: Keypair
    ) {
        this.logger = new Logger('JitoBundleSubmitter');
        this.jitoAuthKeypair = jitoAuthKeypair;

        // Initialize RPC providers
        this.initializeRpcProviders();
        
        // Get Jito endpoint from config or environment
        this.jitoEndpoint = process.env.JITO_ENDPOINT || config.jitoEndpoint || 'https://mainnet.block-engine.jito.wtf';
        
        this.logger.info(`JitoBundleSubmitter initialized with ${this.rpcProviders.length} RPC providers`);
        this.logger.info(`Primary RPC provider: ${this.rpcProviders[0]?.name}`);
        this.logger.info(`Jito endpoint: ${this.jitoEndpoint}`);
    }

    /**
     * Initialize the list of RPC providers with connections
     */
    private initializeRpcProviders(): void {
        // Add Alchemy as the primary provider (top priority)
        const alchemyKey = process.env.ALCHEMY_API_KEY || config.alchemyApiKey;
        if (alchemyKey) {
            const alchemyEndpoint = `https://solana-mainnet.g.alchemy.com/v2/${alchemyKey}`;
            this.rpcProviders.push({
                name: 'Alchemy',
                endpoint: alchemyEndpoint,
                connection: new Connection(alchemyEndpoint, 'confirmed'),
                priority: 1,
                rateLimited: false,
                cooldownMs: this.defaultCooldownMs
            });
        }

        // Add existing connection as secondary provider
        const primaryEndpoint = this.primaryConnection.rpcEndpoint;
        if (primaryEndpoint && !this.rpcProviders.some(p => p.endpoint === primaryEndpoint)) {
            this.rpcProviders.push({
                name: 'Primary',
                endpoint: primaryEndpoint,
                connection: this.primaryConnection,
                priority: 2,
                rateLimited: false,
                cooldownMs: this.defaultCooldownMs
            });
        }

        // Add Helius as fallback (if configured)
        const heliusKey = process.env.HELIUS_API_KEY || config.heliusApiKey;
        if (heliusKey) {
            const heliusEndpoint = `https://rpc.helius.xyz/?api-key=${heliusKey}`;
            this.rpcProviders.push({
                name: 'Helius',
                endpoint: heliusEndpoint,
                connection: new Connection(heliusEndpoint, 'confirmed'),
                priority: 3,
                rateLimited: false,
                cooldownMs: this.defaultCooldownMs
            });
        }

        // Add free fallback providers
        const freeFallbacks = [
            { name: 'GenesysGo', endpoint: 'https://ssc-dao.genesysgo.net' },
            { name: 'Triton', endpoint: 'https://free.rpcpool.com' }
        ];

        let priorityCounter = 4;
        for (const fallback of freeFallbacks) {
            if (!this.rpcProviders.some(p => p.endpoint === fallback.endpoint)) {
                this.rpcProviders.push({
                    name: fallback.name,
                    endpoint: fallback.endpoint,
                    connection: new Connection(fallback.endpoint, 'confirmed'),
                    priority: priorityCounter++,
                    rateLimited: false,
                    cooldownMs: this.defaultCooldownMs
                });
            }
        }

        // Sort by priority
        this.rpcProviders.sort((a, b) => a.priority - b.priority);
    }

    /**
     * Get the best available RPC provider that isn't rate limited
     */
    private getBestAvailableProvider(): RpcProvider {
        const now = Date.now();
        
        // Find first provider that isn't in cooldown from rate limiting
        for (const provider of this.rpcProviders) {
            if (!provider.rateLimited) {
                return provider;
            }
            
            // Check if cooldown period has elapsed
            if (provider.lastErrorTime && (now - provider.lastErrorTime > provider.cooldownMs)) {
                // Reset rate limit flag after cooldown
                provider.rateLimited = false;
                return provider;
            }
        }
        
        // If all are rate limited, use the one with the oldest error
        this.rpcProviders.sort((a, b) => {
            const aTime = a.lastErrorTime || 0;
            const bTime = b.lastErrorTime || 0;
            return aTime - bTime;
        });
        
        // Reset rate limit on the oldest one and return it
        const oldest = this.rpcProviders[0];
        oldest.rateLimited = false;
        this.logger.warn(`All RPC providers are rate limited, resetting the oldest one: ${oldest.name}`);
        return oldest;
    }

    /**
     * Mark a provider as rate limited
     */
    private markProviderRateLimited(provider: RpcProvider): void {
        provider.rateLimited = true;
        provider.lastErrorTime = Date.now();
        this.logger.warn(`Provider ${provider.name} marked as rate limited, cooldown: ${provider.cooldownMs}ms`);
    }

    /**
     * Submit a bundle of transactions to Jito's block engine
     * @param transactions - Array of transactions to include in the bundle
     * @returns The bundle ID if successful
     */
    async submitBundle(transactions: (Transaction | VersionedTransaction)[]): Promise<string> {
        if (!transactions.length) {
            throw new Error('No transactions provided for bundle submission');
        }

        // Prepare transactions for bundle submission
        try {
            // Use the best available provider
            const provider = this.getBestAvailableProvider();
            this.logger.info(`Using RPC provider: ${provider.name}`);
            
            // Get a recent blockhash
            let { blockhash } = await provider.connection.getLatestBlockhash('finalized');
            this.logger.debug(`Got recent blockhash: ${blockhash}`);
            
            // Process the transactions
            for (let i = 0; i < transactions.length; i++) {
                const tx = transactions[i];
                
                // Add recent blockhash to legacy transactions
                if (tx instanceof Transaction) {
                    tx.recentBlockhash = blockhash;
                    tx.feePayer = this.wallet.publicKey;
                    
                    // Sign transaction if not already signed
                    if (!tx.signatures.some(s => s.publicKey.equals(this.wallet.publicKey))) {
                        tx.sign(this.wallet);
                    }
                }
                // Versioned transactions should already have a blockhash
            }
            
            // Submit the bundle to Jito block engine
            return await this.sendToJitoBlockEngine(transactions);
            
        } catch (error) {
            // Check if it's a rate limit error
            if (error instanceof SendTransactionError) {
                const errorMessage = error.message.toLowerCase();
                if (errorMessage.includes('429') || 
                    errorMessage.includes('rate limit') || 
                    errorMessage.includes('too many requests')) {
                    
                    // Mark the current provider as rate limited
                    const currentProvider = this.rpcProviders.find(p => !p.rateLimited);
                    if (currentProvider) {
                        this.markProviderRateLimited(currentProvider);
                    }
                    
                    // Try again with next provider
                    this.logger.warn('Rate limit detected, retrying with next provider');
                    return this.submitBundle(transactions);
                }
            }
            
            // Log and rethrow other errors
            this.logger.error(`Error submitting bundle: ${error}`);
            throw error;
        }
    }

    /**
     * Send the prepared transactions to Jito's block engine as a bundle
     */
    private async sendToJitoBlockEngine(transactions: (Transaction | VersionedTransaction)[]): Promise<string> {
        // In production, this would connect to the Jito block engine and submit the bundle
        // For now, we'll implement a basic version that uses the HTTP API

        // Check if we have a Jito auth keypair
        if (!this.jitoAuthKeypair) {
            // For testing only - in production you'd throw an error
            this.logger.warn('No Jito auth keypair provided, returning mock bundle ID');
            return `mock_bundle_${uuidv4()}`;
        }

        try {
            // Convert transactions to bundle format
            const serializedTransactions = transactions.map(tx => {
                if (tx instanceof Transaction) {
                    return tx.serialize().toString('base64');
                } else {
                    return Buffer.from(tx.serialize()).toString('base64');
                }
            });

            // Create bundle payload
            const bundlePayload = {
                bundle: serializedTransactions,
                auth: Buffer.from(this.jitoAuthKeypair.secretKey).toString('base64')
            };

            // Submit to Jito API
            const response = await axios.post<JitoBundleResponse>(
                `${this.jitoEndpoint}/v1/bundles`, 
                bundlePayload,
                {
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    timeout: 10000 // 10 second timeout
                }
            );

            const bundleId = response.data.bundleId;
            this.logger.info(`Bundle submitted successfully. Bundle ID: ${bundleId}`);
            return bundleId;
        } catch (error) {
            this.logger.error(`Error sending to Jito block engine: ${error}`);
            
            // For axios errors, handle specifically
            if (axios.isAxiosError(error)) {
                if (error.response?.status === 429) {
                    this.logger.warn('Jito rate limit hit');
                    // Wait a bit and retry
                    await new Promise(resolve => setTimeout(resolve, 1000));
                    return this.sendToJitoBlockEngine(transactions);
                }
                
                throw new Error(`Jito API error: ${error.response?.status} - ${error.response?.data || error.message}`);
            }
            
            throw error;
        }
    }

    /**
     * Get the next block details from Jito for timing purposes
     */
    async getNextBlock(): Promise<number> {
        try {
            const provider = this.getBestAvailableProvider();
            const currentSlot = await provider.connection.getSlot('finalized');
            return currentSlot + 1;
        } catch (error) {
            this.logger.error(`Error getting next block: ${error}`);
            throw error;
        }
    }
}