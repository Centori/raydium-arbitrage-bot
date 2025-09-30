import { Connection, Keypair, SystemProgram, Transaction } from "@solana/web3.js";
import { JitoBundleSubmitter } from "../blockchain/jito/JitoBundleSubmitter";
import * as fs from "fs";
import * as dotenv from "dotenv";

dotenv.config();

async function main() {
    try {
        // Initialize connection
        const rpcUrl = process.env.RPC_URL || "https://api.mainnet-beta.solana.com";
        const connection = new Connection(rpcUrl, "confirmed");

        // Load keypairs
        const walletPath = process.env.WALLET_KEYPAIR_PATH || "./wallet-keypair.json";

        const walletKeypair = Keypair.fromSecretKey(
            new Uint8Array(JSON.parse(fs.readFileSync(walletPath, 'utf-8')))
        );

        // Initialize Jito bundle submitter - removing the third parameter (authKeypair)
        const jitoSubmitter = new JitoBundleSubmitter(
            connection,
            walletKeypair
        );

        // Connect to Jito services
        await jitoSubmitter.connect();

        // Create a sample transaction
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

        // Get next leader information
        const nextLeader = await jitoSubmitter.getNextLeader();
        console.log("Next leader information:", nextLeader);

        // Submit bundle
        const result = await jitoSubmitter.submitBundle([transaction]);
        console.log("Bundle submitted:", result);

        // Wait a moment then check status
        await new Promise(resolve => setTimeout(resolve, 5000));

        // Fix: Use the result directly as the bundle ID instead of result.uuid
        const status = await jitoSubmitter.getBundleStatus(result);
        console.log("Bundle status:", status);

    } catch (error) {
        console.error("Error:", error);
    }
}

if (require.main === module) {
    main().catch(console.error);
}