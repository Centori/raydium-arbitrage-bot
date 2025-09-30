import { config } from '../utils/config';
import { JitoBundleSubmitter } from '../blockchain/jito/JitoBundleSubmitter';
import { RaydiumClient } from '../blockchain/raydium/RaydiumClient';
import { JupiterClient } from '../blockchain/jupiter/JupiterClient';
import { Connection, Keypair } from '@solana/web3.js';
import * as fs from 'fs';
import chalk from 'chalk';

async function testSolanaConnection() {
    console.log('\n--- Testing Solana RPC Connection ---');
    try {
        const connection = new Connection(config.rpcEndpoint, 'confirmed');
        const blockHeight = await connection.getBlockHeight();
        console.log(chalk.green('✓ Successfully connected to Solana RPC'));
        console.log(`  Block Height: ${blockHeight}`);
        return true;
    } catch (err) {
        const error = err as Error;
        console.log(chalk.red('✗ Failed to connect to Solana RPC'));
        console.error('  Error:', error.message || 'Unknown error');
        return false;
    }
}

async function testJitoConnection() {
    console.log('\n--- Testing Jito Connection ---');
    try {
        const connection = new Connection(config.rpcEndpoint, 'confirmed');

        // Load wallet keypair
        let walletKeypair: Keypair;
        try {
            walletKeypair = Keypair.fromSecretKey(
                new Uint8Array(JSON.parse(fs.readFileSync(config.walletKeyPath, 'utf-8')))
            );
        } catch (err) {
            console.log(chalk.yellow('Generating new test wallet keypair...'));
            walletKeypair = Keypair.generate();
            fs.writeFileSync(config.walletKeyPath, JSON.stringify(Array.from(walletKeypair.secretKey)));
        }

        const jitoClient = new JitoBundleSubmitter(connection, walletKeypair);
        await jitoClient.connect();

        const nextLeader = await jitoClient.getNextLeader();
        console.log(chalk.green('✓ Successfully connected to Jito'));
        console.log(`  Next leader slot: ${nextLeader.nextLeaderSlot}`);
        console.log(`  Next leader identity: ${nextLeader.nextLeaderIdentity}`);
        
        return true;
    } catch (err) {
        const error = err as Error;
        console.log(chalk.red('✗ Failed to connect to Jito'));
        console.error('  Error:', error.message || 'Unknown error');
        return false;
    }
}

async function testRaydiumConnection() {
    console.log('\n--- Testing Raydium Connection ---');
    try {
        const raydiumClient = new RaydiumClient(config.raydiumApiEndpoint);
        const pools = await raydiumClient.fetchAllPools(); // Fixed: changed getPools to fetchAllPools
        console.log(chalk.green('✓ Successfully connected to Raydium'));
        console.log(`  Found ${pools.length} AMM pools`);
        if (pools.length > 0) {
            const samplePool = pools[0];
            console.log('\n  Sample Pool Details:');
            console.log(`    ID: ${samplePool.id}`);
            console.log(`    Base Token: ${samplePool.baseToken.symbol}`);
            console.log(`    Quote Token: ${samplePool.quoteToken.symbol}`);
        }
        return true;
    } catch (err) {
        const error = err as Error;
        console.log(chalk.red('✗ Failed to connect to Raydium'));
        console.error('  Error:', error.message || 'Unknown error');
        return false;
    }
}

async function testJupiterConnection() {
    console.log('\n--- Testing Jupiter Connection ---');
    try {
        const jupiterClient = new JupiterClient(config.rpcEndpoint);
        
        // Test with SOL -> USDC quote
        const inputMint = 'So11111111111111111111111111111111111111112'; // SOL
        const outputMint = 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v'; // USDC
        const amount = '100000000'; // 0.1 SOL
        
        const quote = await jupiterClient.getQuote(
            inputMint,
            outputMint,
            amount,
            {
                slippageBps: 50,
                onlyDirectRoutes: true
            }
        );
        
        console.log(chalk.green('✓ Successfully connected to Jupiter'));
        console.log('\n  Sample Quote Details:');
        console.log(`    Input: 0.1 SOL`);
        console.log(`    Output: ${Number(quote.outputAmount) / 1e6} USDC`);
        console.log(`    Price Impact: ${quote.priceImpact.toFixed(2)}%`);
        return true;
    } catch (err) {
        const error = err as Error;
        console.log(chalk.red('✗ Failed to connect to Jupiter'));
        console.error('  Error:', error.message || 'Unknown error');
        return false;
    }
}

async function main() {
    console.log(chalk.blue.bold('='.repeat(50)));
    console.log(chalk.blue.bold('          Blockchain Endpoint Tests'));
    console.log(chalk.blue.bold('='.repeat(50)));
    
    // Run all tests
    const results = await Promise.all([
        testSolanaConnection(),
        testJitoConnection(),
        testRaydiumConnection(),
        testJupiterConnection()
    ]);
    
    // Print summary
    console.log(chalk.blue.bold('\n='.repeat(50)));
    console.log(chalk.blue.bold('               Results'));
    console.log(chalk.blue.bold('='.repeat(50)));
    console.log(`Solana RPC:  ${results[0] ? chalk.green('✓ Connected') : chalk.red('✗ Failed')}`);
    console.log(`Jito:        ${results[1] ? chalk.green('✓ Connected') : chalk.red('✗ Failed')}`);
    console.log(`Raydium:     ${results[2] ? chalk.green('✓ Connected') : chalk.red('✗ Failed')}`);
    console.log(`Jupiter:     ${results[3] ? chalk.green('✓ Connected') : chalk.red('✗ Failed')}`);
    console.log(chalk.blue.bold('='.repeat(50)));
    
    // Overall status
    const allSuccessful = results.every(r => r);
    if (allSuccessful) {
        console.log(chalk.green.bold('\n✓ All connections successful!'));
        process.exit(0);
    } else {
        console.log(chalk.yellow.bold('\n⚠ Some connections failed. Check errors above.'));
        process.exit(1);
    }
}

// Run the tests
main().catch(error => {
    console.error('Fatal error:', error);
    process.exit(1);
});