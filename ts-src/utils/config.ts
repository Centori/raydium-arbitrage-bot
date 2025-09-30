import dotenv from 'dotenv';
import path from 'path';

// Load environment variables
dotenv.config({ path: path.resolve(process.cwd(), '.env') });

export interface Config {
    rpcEndpoint: string;
    heliusApiEndpoint: string;
    jitoEndpoint: string;
    telegramBotToken: string;
    telegramChatId: string;
    apiPort: number;
    apiHost: string;
    debug: boolean;
    maxRetries: number;
    retryDelay: number;
    glasshotApiKey: string;
    glasshotApiUrl: string;
}

// RPC endpoints
const ALCHEMY_ENDPOINT = process.env.ALCHEMY_API_KEY
    ? `https://solana-mainnet.g.alchemy.com/v2/${process.env.ALCHEMY_API_KEY}`
    : '';

const HELIUS_ENDPOINT = process.env.HELIUS_API_KEY
    ? `https://mainnet.helius-rpc.com/?api-key=${process.env.HELIUS_API_KEY}`
    : '';

const HELIUS_API_ENDPOINT = process.env.HELIUS_API_KEY
    ? `https://api.helius.xyz/v0/?api-key=${process.env.HELIUS_API_KEY}`
    : '';

// Default fallbacks
const DEFAULT_RPC = 'https://api.mainnet-beta.solana.com';
const DEFAULT_JITO_ENDPOINT = 'https://mainnet.block-engine.jito.wtf';
const DEFAULT_GLASSHOT_API_URL = 'https://api.glasshot.io/v1';

// Determine which RPC endpoint to use
let activeRpcEndpoint = DEFAULT_RPC;

if (process.env.RPC_ENDPOINT) {
    activeRpcEndpoint = process.env.RPC_ENDPOINT;
} else if (HELIUS_ENDPOINT) {
    activeRpcEndpoint = HELIUS_ENDPOINT;
    console.log('Using Helius RPC endpoint');
} else if (ALCHEMY_ENDPOINT) {
    activeRpcEndpoint = ALCHEMY_ENDPOINT;
    console.log('Using Alchemy RPC endpoint');
} else {
    console.warn('No RPC API key provided, using public endpoint. Performance may be limited.');
}

// Config object
export const config: Config = {
    rpcEndpoint: activeRpcEndpoint,
    heliusApiEndpoint: HELIUS_API_ENDPOINT,
    jitoEndpoint: process.env.JITO_ENDPOINT || DEFAULT_JITO_ENDPOINT,
    telegramBotToken: process.env.TELEGRAM_BOT_TOKEN || '',
    telegramChatId: process.env.TELEGRAM_CHAT_ID || '',
    apiPort: process.env.API_PORT ? parseInt(process.env.API_PORT) : 3000,
    apiHost: process.env.API_HOST || 'localhost',
    debug: process.env.DEBUG === 'true',
    maxRetries: process.env.MAX_RETRIES ? parseInt(process.env.MAX_RETRIES) : 3,
    retryDelay: process.env.RETRY_DELAY ? parseInt(process.env.RETRY_DELAY) : 1000,
    glasshotApiKey: process.env.GLASSHOT_API_KEY || '',
    glasshotApiUrl: process.env.GLASSHOT_API_URL || DEFAULT_GLASSHOT_API_URL
};