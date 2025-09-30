import { Connection, Keypair } from '@solana/web3.js';
import { JitoBundleSubmitter } from '../blockchain/jito/JitoBundleSubmitter';
import { config } from '../utils/config';
import * as fs from 'fs';
import chalk from 'chalk';

async function testJitoConnection() {
    console.log(chalk.blue.bold('\n=== Testing Jito Connection ===\n'));
    
    try {
        // Initialize connection
        console.log(`Connecting to RPC endpoint: ${config.rpcEndpoint}`);
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

        // Initialize Jito client
        const jitoClient = new JitoBundleSubmitter(connection, walletKeypair);
        
        // Connect to Jito services
        console.log('Connecting to Jito services...');
        await jitoClient.connect();
        
        // Get next leader information
        console.log('\nGetting next leader information...');
        const nextLeader = await jitoClient.getNextLeader();
        console.log(chalk.green('\n✓ Successfully connected to Jito'));
        console.log(`  Current Slot: ${nextLeader.currentSlot}`);
        console.log(`  Next Leader Slot: ${nextLeader.nextLeaderSlot}`);
        console.log(`  Next Leader: ${nextLeader.nextLeaderIdentity}`);
        
        return true;
    } catch (err) {
        const error = err as Error;
        console.log(chalk.red('\n✗ Failed to connect to Jito'));
        console.error('Error:', error.message || 'Unknown error');
        return false;
    }
}

// Run the test
testJitoConnection().then(success => {
    if (!success) {
        process.exit(1);
    }
    process.exit(0);
}).catch(error => {
    console.error('Fatal error:', error);
    process.exit(1);
});