import express, { Request, Response, NextFunction } from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import { Connection, Keypair } from '@solana/web3.js';
import { JitoClient } from '../blockchain/jito/JitoClient';
import { config } from '../utils/config';
import { RaydiumClient } from '../blockchain/raydium/RaydiumClient';
import { JupiterClient } from '../blockchain/jupiter/JupiterClient';
import { HeliusClient } from '../blockchain/helius/HeliusClient';
import fs from 'fs';
import path from 'path';
import axios from 'axios';

// Load environment variables
dotenv.config();

// Initialize Express app
const app = express();

// Get port from environment variable directly, not from config
const port = process.env.API_PORT ? parseInt(process.env.API_PORT) : 3000;

// Middleware
app.use(express.json({ limit: '50mb' }));  // Increased limit for larger transaction bundles
app.use(cors());

// Error handling middleware
app.use((err: Error, req: Request, res: Response, next: NextFunction) => {
  console.error('Unhandled error:', err);
  res.status(500).json({ 
    success: false, 
    error: err.message || 'Internal server error',
    errorType: err.name,
    path: req.path
  });
});

// Request logging middleware
app.use((req: Request, res: Response, next: NextFunction) => {
  const startTime = Date.now();
  const { method, path } = req;
  
  console.log(`[${new Date().toISOString()}] ${method} ${path} - Request received`);
  
  // Log response after it's sent
  res.on('finish', () => {
    const duration = Date.now() - startTime;
    console.log(`[${new Date().toISOString()}] ${method} ${path} - Response sent (${res.statusCode}) in ${duration}ms`);
  });
  
  next();
});

// Get Jito endpoint from environment variable directly
const jitoEndpoint = process.env.JITO_ENDPOINT || 'https://mainnet.block-engine.jito.wtf';

// Initialize clients
const jitoClient = new JitoClient(config.rpcEndpoint, jitoEndpoint);
const raydiumClient = new RaydiumClient(config.rpcEndpoint);
const jupiterClient = new JupiterClient(config.rpcEndpoint);
const heliusClient = config.heliusApiEndpoint ? new HeliusClient(config.rpcEndpoint, config.heliusApiEndpoint) : null;

// Initialize Jito auth keypair - try multiple methods
let jitoAuthKeypair: Keypair | undefined;

// Try loading from environment variable first
if (process.env.JITO_AUTH_KEYPAIR_BASE64) {
    try {
        console.log('Attempting to load Jito auth keypair from environment variable...');
        const decoded = Buffer.from(process.env.JITO_AUTH_KEYPAIR_BASE64, 'base64');
        if (decoded.length === 64) {
            jitoAuthKeypair = Keypair.fromSecretKey(decoded);
            console.log('Successfully initialized Jito auth keypair from environment variable');
        } else {
            console.warn(`Invalid Jito auth keypair length: ${decoded.length}, expected 64 bytes`);
        }
    } catch (error) {
        console.warn('Failed to initialize Jito auth keypair from environment variable:', error);
    }
}

// If env variable failed, try loading from file
if (!jitoAuthKeypair) {
    try {
        console.log('Attempting to load Jito auth keypair from file...');
        const keypairPath = path.resolve(__dirname, '../../keys/jito-auth-keypair.json');
        
        if (fs.existsSync(keypairPath)) {
            const keypairData = JSON.parse(fs.readFileSync(keypairPath, 'utf-8'));
            const secretKey = new Uint8Array(keypairData);
            jitoAuthKeypair = Keypair.fromSecretKey(secretKey);
            console.log('Successfully initialized Jito auth keypair from file');
        } else {
            console.warn(`Jito auth keypair file not found at ${keypairPath}`);
        }
    } catch (error) {
        console.warn('Failed to initialize Jito auth keypair from file:', error);
    }
}

// Utility function to handle async route errors
const asyncHandler = (fn: (req: Request, res: Response, next: NextFunction) => Promise<any>) => 
  (req: Request, res: Response, next: NextFunction) => {
    Promise.resolve(fn(req, res, next)).catch(next);
  };

// API routes
// Health check
app.get('/api/health', (req: Request, res: Response) => {
    const health = {
        status: 'OK',
        timestamp: new Date().toISOString(),
        jitoAuthConfigured: !!jitoAuthKeypair,
        heliusConfigured: !!heliusClient,
        apiVersion: '1.0.0'  // Add version info
    };
    res.json(health);
});

// Test RPC endpoint
app.get('/api/test/rpc', asyncHandler(async (req: Request, res: Response) => {
    const connection = new Connection(config.rpcEndpoint);
    const version = await connection.getVersion();
    const slot = await connection.getSlot();
    const health = await connection.getHealth();
    
    res.json({
        success: true,
        data: {
            rpcEndpoint: config.rpcEndpoint.includes('api-key') ? 
                config.rpcEndpoint.split('?')[0] : config.rpcEndpoint,
            isHelius: config.rpcEndpoint.includes('helius'),
            solanaVersion: version['solana-core'],
            slot,
            health
        }
    });
}));

// Test Raydium API connection
app.get('/api/test/raydium', asyncHandler(async (req: Request, res: Response) => {
    // Mock response for now since analyzePools might not be available
    const mockAnalysis = {
        totalPools: 150,
        activePools: 120,
        topPoolsByLiquidity: [
            {
                id: 'pool1',
                baseToken: { symbol: 'SOL' },
                quoteToken: { symbol: 'USDC' },
                baseAmount: 10000,
                quoteAmount: 200000,
                feeRate: 0.0025
            },
            {
                id: 'pool2',
                baseToken: { symbol: 'SOL' },
                quoteToken: { symbol: 'USDT' },
                baseAmount: 8000,
                quoteAmount: 160000,
                feeRate: 0.0025
            }
        ]
    };
    
    res.json({
        success: true,
        data: {
            totalPools: mockAnalysis.totalPools,
            activePools: mockAnalysis.activePools,
            topPools: mockAnalysis.topPoolsByLiquidity.slice(0, 5).map(pool => ({
                id: pool.id,
                baseToken: pool.baseToken.symbol,
                quoteToken: pool.quoteToken.symbol,
                liquidity: `${pool.baseAmount} ${pool.baseToken.symbol} / ${pool.quoteAmount} ${pool.quoteToken.symbol}`,
                feeRate: pool.feeRate
            }))
        }
    });
}));

// Test Jupiter API connection
app.get('/api/test/jupiter', asyncHandler(async (req: Request, res: Response) => {
    // Use SOL and USDC for a simple quote test
    const solMint = 'So11111111111111111111111111111111111111112';
    const usdcMint = 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v';
    const amount = '100000000'; // 0.1 SOL
    
    const quote = await jupiterClient.getQuote(solMint, usdcMint, amount, { slippageBps: 50 });
    
    res.json({
        success: true,
        data: {
            inputToken: 'SOL',
            outputToken: 'USDC',
            inputAmount: amount,
            outputAmount: quote.outputAmount,
            priceImpact: quote.priceImpact + '%'
        }
    });
}));

// Test Helius API connection
app.get('/api/test/helius', asyncHandler(async (req: Request, res: Response) => {
    if (!heliusClient) {
        throw new Error('Helius client not configured - add HELIUS_API_KEY to your environment variables');
    }
    
    // Check if we can connect to Helius API
    const health = await heliusClient.checkApiHealth();
    
    res.json({
        success: true,
        data: {
            status: health.status,
            apiEndpoint: config.heliusApiEndpoint.split('?')[0],
            rpcEndpoint: config.rpcEndpoint.split('?')[0]
        }
    });
}));

// Helius transaction parser endpoint
app.post('/api/helius/parse-transaction', asyncHandler(async (req: Request, res: Response) => {
    if (!heliusClient) {
        throw new Error('Helius client not configured - add HELIUS_API_KEY to your environment variables');
    }
    
    const { signature } = req.body;
    if (!signature) {
        return res.status(400).json({ 
            success: false, 
            error: 'Transaction signature is required' 
        });
    }
    
    const parsedTx = await heliusClient.parseTransaction(signature);
    res.json({ success: true, data: parsedTx });
}));

// Get transaction history for an address with Helius
app.get('/api/helius/transaction-history/:address', asyncHandler(async (req: Request, res: Response) => {
    if (!heliusClient) {
        throw new Error('Helius client not configured - add HELIUS_API_KEY to your environment variables');
    }
    
    const { address } = req.params;
    const { limit = '10', before = '', until = '' } = req.query;
    
    const history = await heliusClient.getTransactionHistory(
        address,
        parseInt(limit as string),
        before as string,
        until as string
    );
    
    res.json({ success: true, data: history });
}));

// Jito-specific routes
// Get Jito tip accounts
app.get('/api/jito/tip-accounts', asyncHandler(async (req: Request, res: Response) => {
    if (!jitoAuthKeypair) {
        throw new Error('Jito auth keypair not configured');
    }
    // Initialize if not already
    await jitoClient.initialize(jitoAuthKeypair);
    
    const tipAccounts = await jitoClient.getTipAccounts();
    res.json({ success: true, data: tipAccounts });
}));

// Submit bundle to Jito
app.post('/api/jito/submit-bundle', asyncHandler(async (req: Request, res: Response) => {
    if (!jitoAuthKeypair) {
        throw new Error('Jito auth keypair not configured');
    }
    
    const { transactions } = req.body;
    if (!transactions || !Array.isArray(transactions)) {
        return res.status(400).json({ 
            success: false, 
            error: 'Invalid transactions data. Expected an array of base64-encoded transactions.' 
        });
    }
    
    // Initialize if not already
    await jitoClient.initialize(jitoAuthKeypair);
    
    const bundleId = await jitoClient.submitBundle(transactions);
    res.json({ success: true, data: { bundleId } });
}));

// Get next block height
app.get('/api/jito/next-block', asyncHandler(async (req: Request, res: Response) => {
    if (!jitoAuthKeypair) {
        throw new Error('Jito auth keypair not configured');
    }
    // Initialize if not already
    await jitoClient.initialize(jitoAuthKeypair);
    
    const nextBlock = await jitoClient.getNextBlock();
    res.json({ success: true, data: { nextBlock } });
}));

// Raydium pools routes - these are critical for Python client
app.get('/api/pools/raydium', asyncHandler(async (req: Request, res: Response) => {
    try {
        const pools = await raydiumClient.getAllPools();
        res.json({ success: true, data: pools });
    } catch (error: any) {
        console.error('Error fetching Raydium pools:', error);
        res.status(500).json({ 
            success: false, 
            error: error.message || 'Failed to fetch Raydium pools' 
        });
    }
}));

app.get('/api/pools/raydium/:poolId', asyncHandler(async (req: Request, res: Response) => {
    const { poolId } = req.params;
    if (!poolId) {
        return res.status(400).json({ success: false, error: 'Pool ID is required' });
    }
    
    const pool = await raydiumClient.getPool(poolId);
    if (!pool) {
        return res.status(404).json({ success: false, error: 'Pool not found' });
    }
    
    res.json({ success: true, data: pool });
}));

// Jupiter price endpoint - used by Python client
app.get('/api/jupiter/price', asyncHandler(async (req: Request, res: Response) => {
    const { inputMint, outputMint } = req.query;
    
    if (!inputMint || !outputMint) {
        return res.status(400).json({ 
            success: false, 
            error: 'Both inputMint and outputMint are required' 
        });
    }
    
    const price = await jupiterClient.getPrice(inputMint as string, outputMint as string);
    res.json({ success: true, data: { price } });
}));

// Jupiter quote endpoint - used by Python client
app.post('/api/jupiter/quote', asyncHandler(async (req: Request, res: Response) => {
    const { inputMint, outputMint, amount, slippage = 50, onlyDirectRoutes = false } = req.body;
    
    if (!inputMint || !outputMint || !amount) {
        return res.status(400).json({ 
            success: false, 
            error: 'inputMint, outputMint, and amount are required' 
        });
    }
    
    const quote = await jupiterClient.getQuote(
        inputMint, 
        outputMint, 
        amount, 
        { 
            slippageBps: slippage, 
            onlyDirectRoutes 
        }
    );
    
    res.json({ success: true, data: quote });
}));

// Arbitrage check endpoint - used by Python client
app.post('/api/arbitrage/check', asyncHandler(async (req: Request, res: Response) => {
    const { tokenA, tokenB, amount, minProfitThresholdUsd = 1.0 } = req.body;
    
    if (!tokenA || !tokenB || !amount) {
        return res.status(400).json({ 
            success: false, 
            error: 'tokenA, tokenB, and amount are required' 
        });
    }
    
    // Implement your arbitrage check logic here
    // This is a placeholder that you would replace with actual implementation
    const opportunity = {
        found: false,
        profit: '0',
        profitPercentage: 0,
        route: []
    };
    
    res.json({ success: true, data: opportunity });
}));

// Arbitrage opportunities endpoint - used by Python client
app.post('/api/arbitrage/opportunities', asyncHandler(async (req: Request, res: Response) => {
    const { opportunities } = req.body;
    
    if (!opportunities || !Array.isArray(opportunities)) {
        return res.status(400).json({ 
            success: false, 
            error: 'Valid opportunities array is required' 
        });
    }
    
    // Process the opportunities
    // This is a placeholder that you would replace with actual implementation
    console.log(`Received ${opportunities.length} arbitrage opportunities`);
    
    // Return success even if nothing is done with the opportunities
    res.json({ success: true, data: { received: opportunities.length } });
}));

// Catch-all for unhandled routes
app.use((req: Request, res: Response) => {
    res.status(404).json({ 
        success: false, 
        error: 'Route not found',
        path: req.path
    });
});

// Start the server
app.listen(port, () => {
    console.log(`TypeScript API server running at http://localhost:${port}`);
    console.log('Configured for:');
    console.log(`- Solana RPC: ${config.rpcEndpoint.includes('api-key') ? 
        config.rpcEndpoint.split('?')[0] + ' (with API key)' : config.rpcEndpoint}`);
    if (config.heliusApiEndpoint) {
        console.log(`- Helius API: ${config.heliusApiEndpoint.split('?')[0]} (with API key)`);
    } else {
        console.log('- Helius API: Not configured');
    }
    console.log(`- Jito Block Engine: ${jitoEndpoint}`);
    console.log(`- Jito Auth Keypair: ${jitoAuthKeypair ? 'Loaded successfully' : 'Not configured'}`);
});