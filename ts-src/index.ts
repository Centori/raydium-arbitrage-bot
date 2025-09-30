import dotenv from 'dotenv';
import { config } from './utils/config';
import { Connection } from '@solana/web3.js';

// Start the API server explicitly
console.log('Starting Raydium Arbitrage Bot TypeScript Service...');
console.log(`Using RPC endpoint: ${config.rpcEndpoint}`);

// Log Jito endpoint if available
const jitoEndpoint = process.env.JITO_ENDPOINT || 'Not configured';
console.log(`Using Jito endpoint: ${jitoEndpoint}`);

// Import the API server to ensure it starts
import './api/server';

// Test connection to Solana
const connection = new Connection(config.rpcEndpoint, 'confirmed');
connection.getBlockHeight().then(height => {
    console.log(`Successfully connected to Solana (current block height: ${height})`);
}).catch(err => {
    console.error('Failed to connect to Solana:', err);
});

// Graceful shutdown
process.on('SIGINT', () => {
    console.log('Shutting down TypeScript services...');
    process.exit(0);
});

process.on('unhandledRejection', (reason, promise) => {
    console.error('Unhandled Rejection at:', promise, 'reason:', reason);
});