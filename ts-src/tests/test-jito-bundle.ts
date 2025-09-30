import { Connection, Keypair, SystemProgram, Transaction } from "@solana/web3.js";
import { JitoBundleSubmitter } from "../blockchain/jito/JitoBundleSubmitter";
import { config } from "../utils/config";
import * as fs from "fs";
import * as path from "path";
import chalk from "chalk";

async function testJitoBundleSubmission() {
    console.log(chalk.blue.bold('\n=== Testing Jito Bundle Submission ===\n'));
    
    try {
        // Initialize connection
        console.log(`Connecting to RPC endpoint: ${config.rpcEndpoint}`);
        const connection = new Connection(config.rpcEndpoint, "confirmed");

        // Load wallet keypair
        console.log('Loading wallet keypair...');
        console.log(`Wallet path: ${config.walletKeyPath}`);

        // Ensure keys directory exists
        const keysDir = path.dirname(config.walletKeyPath);
        if (!fs.existsSync(keysDir)) {
            console.log(`Creating keys directory: ${keysDir}`);
            fs.mkdirSync(keysDir, { recursive: true });
        }

        let walletKeypair: Keypair;

        try {
            walletKeypair = Keypair.fromSecretKey(
                new Uint8Array(JSON.parse(fs.readFileSync(config.walletKeyPath, 'utf-8')))
            );
        } catch (err) {
            console.log(chalk.yellow('Wallet keypair file not found. Generating new one for testing...'));
            
            // Generate new keypair for testing
            walletKeypair = Keypair.generate();

            // Save the keypair
            fs.writeFileSync(config.walletKeyPath, JSON.stringify(Array.from(walletKeypair.secretKey)));
            
            console.log(chalk.green('Generated and saved new wallet keypair'));
            console.log(`Wallet public key: ${walletKeypair.publicKey.toString()}`);
        }

        // Initialize Jito bundle submitter
        console.log('Initializing Jito bundle submitter...');
        const jitoSubmitter = new JitoBundleSubmitter(
            connection,
            walletKeypair
        );

        // Connect to Jito services
        console.log('Connecting to Jito services...');
        await jitoSubmitter.connect();

        // Get next leader information
        console.log('\nGetting next leader information...');
        const nextLeader = await jitoSubmitter.getNextLeader();
        console.log('Next leader info:', nextLeader);

        // Create a sample transaction
        console.log('\nCreating sample transaction...');
        const recentBlockhash = await connection.getLatestBlockhash();
        const transaction = new Transaction({
            feePayer: walletKeypair.publicKey,
            recentBlockhash: recentBlockhash.blockhash,
        }).add(
            SystemProgram.transfer({
                fromPubkey: walletKeypair.publicKey,
                toPubkey: walletKeypair.publicKey,
                lamports: 1,
            })
        );
        
        transaction.sign(walletKeypair);

        // Submit bundle
        console.log('Submitting bundle...');
        const bundleId = await jitoSubmitter.submitBundle([transaction]);
        console.log(chalk.green(`\n✓ Bundle submitted successfully with ID: ${bundleId}`));

        // Set up bundle result listener
        console.log('\nWaiting for bundle result...');
        const unsubscribe = jitoSubmitter.onBundleResult(
            (result) => {
                console.log('Bundle result:', result);
                unsubscribe();
                process.exit(0);
            },
            (error) => {
                console.error('Bundle error:', error);
                unsubscribe();
                process.exit(1);
            }
        );

        // Wait for a bit to see the result
        setTimeout(() => {
            console.log(chalk.yellow('\nTimeout waiting for bundle result'));
            unsubscribe();
            process.exit(0);
        }, 30000); // Wait 30 seconds max

    } catch (err) {
        const error = err as Error;
        console.log(chalk.red('\n✗ Failed to test Jito bundle submission'));
        console.error('Error:', error.message || 'Unknown error');
        process.exit(1);
    }
}

// Run the test
testJitoBundleSubmission().catch(error => {
    console.error('Fatal error:', error);
    process.exit(1);
});