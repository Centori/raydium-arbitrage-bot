// filepath: /Users/lm/Desktop/raydium-arbitrage-bot/ts-src/test-raydium-flash-loan.ts
import { Connection, Keypair } from '@solana/web3.js';
import * as fs from 'fs';
import * as dotenv from 'dotenv';
import { RaydiumSwap } from './blockchain/raydium/RaydiumSwap';
import { SolendClient } from './blockchain/solend/SolendClient';
import { TOKEN_MINTS, POOL_ADDRESSES } from './blockchain/solend/constants';
import { TokenPair } from './models/TokenPair';

// Load environment variables
dotenv.config();

// Initialize connection to Solana network
const connection = new Connection(
    process.env.RPC_ENDPOINT || 'https://api.mainnet-beta.solana.com',
    'confirmed'
);

// Load wallet keypair from file
const loadWalletFromFile = (filePath: string): Keypair => {
    try {
        const keypairData = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
        return Keypair.fromSecretKey(Uint8Array.from(keypairData));
    } catch (error) {
        console.error(`Error loading wallet: ${error}`);
        throw new Error(`Failed to load wallet from ${filePath}`);
    }
};

// Define token pairs for testing
const getTestTokenPairs = (): TokenPair[] => {
    return [
        {
            name: 'SOL/USDC',
            tokenA: {
                symbol: 'SOL',
                name: 'Solana',
                address: TOKEN_MINTS.SOL,
                decimals: 9
            },
            tokenB: {
                symbol: 'USDC',
                name: 'USD Coin',
                address: TOKEN_MINTS.USDC,
                decimals: 6
            },
            poolAddress: POOL_ADDRESSES.SOL_USDC
        },
        {
            name: 'SOL/USDT',
            tokenA: {
                symbol: 'SOL',
                name: 'Solana',
                address: TOKEN_MINTS.SOL,
                decimals: 9
            },
            tokenB: {
                symbol: 'USDT',
                name: 'Tether USD',
                address: TOKEN_MINTS.USDT,
                decimals: 6
            },
            poolAddress: POOL_ADDRESSES.SOL_USDT
        }
    ];
};

// Test Solend flash loan fee calculation
const testFlashLoanFees = async () => {
    console.log('==== Testing Solend Flash Loan Fees ====');
    
    const solendClient = new SolendClient(connection);
    
    // Test both SOL and USDC amounts
    const solAmounts = [0.1, 1, 10, 100];
    const usdAmounts = [100, 1000, 10000, 100000];
    
    console.log('Testing SOL flash loan fees:');
    for (const amount of solAmounts) {
        const fee = await solendClient.getFlashLoanFee(amount, true);
        const isViable = await solendClient.checkFlashLoanViability(amount, 'SOL');
        console.log(`Amount: ${amount} SOL, Fee: ${fee} SOL, Viable: ${isViable}`);
    }
    
    console.log('\nTesting USDC/USDT flash loan fees:');
    for (const amount of usdAmounts) {
        const fee = await solendClient.getFlashLoanFee(amount, false);
        const isViable = await solendClient.checkFlashLoanViability(amount);
        console.log(`Amount: ${amount} USD, Fee: ${fee} USD, Viable: ${isViable}`);
    }
    
    console.log('==== Flash Loan Fee Test Complete ====\n');
};

// Test Raydium swap with flash loan
const testRaydiumFlashLoan = async () => {
    console.log('==== Testing Raydium Flash Loan Swap ====');
    
    try {
        // Load wallet keypair
        const wallet = process.env.WALLET_KEYPAIR_PATH 
            ? loadWalletFromFile(process.env.WALLET_KEYPAIR_PATH)
            : loadWalletFromFile('./keys/wallet-keypair.json');
        
        console.log(`Using wallet: ${wallet.publicKey.toString()}`);
        
        // Initialize RaydiumSwap
        const raydiumSwap = new RaydiumSwap(connection);
        
        // Get test token pairs
        const tokenPairs = getTestTokenPairs();
        
        // Test both SOL/USDC and SOL/USDT pairs
        for (const pair of tokenPairs) {
            console.log(`\nTesting flash loan swap with ${pair.name} pair`);
            
            // Set flash loan parameters based on pair
            const flashLoanAmount = pair.tokenB.symbol === 'USDC' ? 1000 : 1000; // 1000 USDC or USDT
            const expectedProfitPercent = 1; // 1% profit expected
            
            console.log(`Flash loan amount: ${flashLoanAmount} ${pair.tokenB.symbol}`);
            console.log(`Expected profit: ${expectedProfitPercent}%`);
            
            // Execute flash loan swap
            const signature = await raydiumSwap.executeSwapWithFlashLoan(
                wallet,
                pair,
                flashLoanAmount,
                expectedProfitPercent
            );
            
            console.log(`Flash loan swap completed with signature: ${signature}`);
        }
    } catch (error) {
        console.error(`Error in flash loan test: ${error}`);
    }
    
    console.log('==== Raydium Flash Loan Test Complete ====\n');
};

// Main function to run all tests
const main = async () => {
    console.log('Starting Raydium Flash Loan Tests');
    
    try {
        // Test flash loan fees
        await testFlashLoanFees();
        
        // Test Raydium flash loan swap
        await testRaydiumFlashLoan();
        
        console.log('All tests completed successfully');
    } catch (error) {
        console.error(`Error running tests: ${error}`);
        process.exit(1);
    }
};

// Run the main function
main()
    .then(() => process.exit(0))
    .catch((error) => {
        console.error(error);
        process.exit(1);
    });