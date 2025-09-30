import { Connection } from '@solana/web3.js';
import { GlasshotClient } from './ts-src/blockchain/glasshot/GlasshotClient';
import { config } from './ts-src/utils/config';

// SOL and some common token addresses for testing
const TOKEN_ADDRESSES = {
    SOL: 'So11111111111111111111111111111111111111112',  // Wrapped SOL
    USDC: 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',
    USDT: 'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB',
    RAY: '4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R',
    ETH: '7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs'  // Wrapped ETH
};

async function testGlasshotApi() {
    console.log('Testing Glasshot API integration...');
    
    const connection = new Connection(config.rpcEndpoint, 'confirmed');
    const glasshotClient = new GlasshotClient();
    
    // Check API health
    console.log('Checking API health...');
    const healthStatus = await glasshotClient.checkApiHealth();
    console.log(`Glasshot API status: ${healthStatus.status}`);
    
    // Test token price retrieval
    console.log('\nTesting token price retrieval:');
    for (const [symbol, address] of Object.entries(TOKEN_ADDRESSES)) {
        try {
            console.log(`Fetching price data for ${symbol}...`);
            const priceData = await glasshotClient.getTokenPrice(address);
            console.log(`${symbol} price data:`, JSON.stringify(priceData, null, 2));
        } catch (error: any) {
            console.error(`Error fetching price for ${symbol}:`, error.message || 'Unknown error');
        }
    }
    
    // Test pool data retrieval (using a known Raydium pool)
    const raydiumPoolAddress = 'HfsedaWauvDaLPm6rwgMc6D5QRmhr8siqGtS6tf2wthU'; // Example: SOL-USDC pool
    try {
        console.log('\nTesting pool data retrieval...');
        const poolData = await glasshotClient.getPoolData(raydiumPoolAddress);
        console.log(`Pool data:`, JSON.stringify(poolData, null, 2));
    } catch (error: any) {
        console.error(`Error fetching pool data:`, error.message || 'Unknown error');
    }
    
    console.log('\nTests completed.');
}

testGlasshotApi().catch(err => {
    console.error('Test failed:', err);
    process.exit(1);
});