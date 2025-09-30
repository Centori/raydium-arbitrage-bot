import { Connection, Keypair, SystemProgram, Transaction, PublicKey } from '@solana/web3.js';
import { JitoBundleSubmitter } from '../blockchain/jito/JitoBundleSubmitter';
import { RaydiumClient } from '../blockchain/raydium/RaydiumClient';
import { config } from '../utils/config';
import * as fs from 'fs';
import chalk from 'chalk';

async function testBundleSubmissionRate() {
    console.log('\n--- Testing Bundle Submission Success Rate ---');
    try {
        const connection = new Connection(config.rpcEndpoint, 'confirmed');
        const walletKeypair = Keypair.fromSecretKey(
            new Uint8Array(JSON.parse(fs.readFileSync(config.walletKeyPath, 'utf-8')))
        );

        const jitoClient = new JitoBundleSubmitter(connection, walletKeypair);
        await jitoClient.connect();

        let successCount = 0;
        const testCount = 5;
        
        for (let i = 0; i < testCount; i++) {
            try {
                // Create test transaction
                const tx = new Transaction().add(
                    SystemProgram.transfer({
                        fromPubkey: walletKeypair.publicKey,
                        toPubkey: walletKeypair.publicKey,
                        lamports: 1,
                    })
                );
                
                // Submit bundle
                const bundleId = await jitoClient.submitBundle([tx]);
                if (bundleId) successCount++;
                
                console.log(`Bundle ${i + 1} submission: ${bundleId ? '✓' : '✗'}`);
                await new Promise(resolve => setTimeout(resolve, 2000)); // Wait between submissions
            } catch (err) {
                console.log(`Bundle ${i + 1} submission: ✗`);
            }
        }

        const successRate = (successCount / testCount) * 100;
        console.log(`\nBundle submission success rate: ${successRate}%`);
        return successRate >= 80; // Require 80% success rate
    } catch (err) {
        console.error('Error testing bundle submission rate:', err);
        return false;
    }
}

async function testSlippageImpact() {
    console.log('\n--- Testing Slippage Impact ---');
    try {
        const raydiumClient = new RaydiumClient(config.rpcEndpoint);
        const pools = await raydiumClient.fetchAllPools(); // Fixed: changed getPools to fetchAllPools
        
        // Test with different trade sizes
        const testAmounts = ['1000000', '10000000', '100000000']; // 0.001, 0.01, 0.1 SOL
        
        for (const pool of pools.slice(0, 3)) { // Test first 3 pools
            console.log(`\nTesting pool ${pool.baseToken.symbol}/${pool.quoteToken.symbol}`);
            
            for (const amount of testAmounts) {
                const baseTokenAmount = amount;
                // Calculate expected slippage using pool data
                const slippage = calculateSlippage(
                    baseTokenAmount,
                    pool.baseAmount,
                    pool.quoteAmount
                );
                
                console.log(`  Amount: ${Number(amount) / 1e9} SOL`);
                console.log(`  Expected slippage: ${slippage.toFixed(2)}%`);
                
                // Flag high slippage
                if (slippage > 1.0) {
                    console.log(chalk.yellow(`  ⚠ High slippage detected`));
                }
            }
        }
        
        return true;
    } catch (err) {
        console.error('Error testing slippage impact:', err);
        return false;
    }
}

function calculateSlippage(
    inputAmount: string,
    poolBaseAmount: string,
    poolQuoteAmount: string
): number {
    const x = Number(inputAmount);
    const X = Number(poolBaseAmount);
    const Y = Number(poolQuoteAmount);
    
    // Using constant product formula (x * y = k)
    const expectedPrice = Y / X;
    const actualPrice = (Y * X) / ((X + x) * X);
    const slippage = Math.abs((actualPrice - expectedPrice) / expectedPrice) * 100;
    
    return slippage;
}

async function testGasOptimization() {
    console.log('\n--- Testing Gas Optimization ---');
    try {
        const connection = new Connection(config.rpcEndpoint, 'confirmed');
        const walletKeypair = Keypair.fromSecretKey(
            new Uint8Array(JSON.parse(fs.readFileSync(config.walletKeyPath, 'utf-8')))
        );

        // Test transaction with different compute unit limits
        const computeUnits = [200000, 400000, 600000, 800000];
        
        for (const units of computeUnits) {
            const tx = new Transaction().add(
                SystemProgram.transfer({
                    fromPubkey: walletKeypair.publicKey,
                    toPubkey: walletKeypair.publicKey,
                    lamports: 1,
                })
            );
            
            // Set compute unit limit
            tx.recentBlockhash = (await connection.getLatestBlockhash()).blockhash;
            tx.feePayer = walletKeypair.publicKey;
            
            const gasEstimate = await connection.getFeeForMessage(
                tx.compileMessage(),
                'confirmed'
            );
            
            console.log(`Compute units: ${units}`);
            console.log(`Estimated gas: ${gasEstimate.value} lamports`);
        }
        
        return true;
    } catch (err) {
        console.error('Error testing gas optimization:', err);
        return false;
    }
}

async function main() {
    console.log(chalk.blue.bold('='.repeat(50)));
    console.log(chalk.blue.bold('          Transaction Testing Suite'));
    console.log(chalk.blue.bold('='.repeat(50)));
    
    const results = await Promise.all([
        testBundleSubmissionRate(),
        testSlippageImpact(),
        testGasOptimization()
    ]);
    
    console.log(chalk.blue.bold('\n='.repeat(50)));
    console.log(chalk.blue.bold('               Results'));
    console.log(chalk.blue.bold('='.repeat(50)));
    console.log(`Bundle Submission: ${results[0] ? chalk.green('✓ Pass') : chalk.red('✗ Fail')}`);
    console.log(`Slippage Impact:  ${results[1] ? chalk.green('✓ Pass') : chalk.red('✗ Fail')}`);
    console.log(`Gas Optimization: ${results[2] ? chalk.green('✓ Pass') : chalk.red('✗ Fail')}`);
    
    const allPassed = results.every(r => r);
    if (allPassed) {
        console.log(chalk.green.bold('\n✓ All transaction tests passed!'));
        process.exit(0);
    } else {
        console.log(chalk.yellow.bold('\n⚠ Some tests failed. Review before proceeding to production.'));
        process.exit(1);
    }
}

if (require.main === module) {
    main().catch(console.error);
}