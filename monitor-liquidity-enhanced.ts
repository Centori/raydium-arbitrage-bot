import { Connection } from '@solana/web3.js';
import { monitorLiquidityFlowEnhanced } from './ts-src/tests/test-liquidity-monitor';
import { TelegramNotifier } from './ts-src/utils/TelegramNotifier';
import dotenv from 'dotenv';

// Load environment variables
dotenv.config();

// Initialize connection
const rpcEndpoint = process.env.RPC_ENDPOINT || 'https://api.mainnet-beta.solana.com';
const connection = new Connection(rpcEndpoint, 'confirmed');

// Validate Telegram configuration
const telegramBotToken = process.env.TELEGRAM_BOT_TOKEN || '';
const telegramChatId = process.env.TELEGRAM_CHAT_ID || '';

if (!telegramBotToken || telegramBotToken.trim() === '') {
    console.error('ERROR: TELEGRAM_BOT_TOKEN environment variable is missing or empty');
    console.error('Please set it in your .env file');
    process.exit(1);
}

if (!telegramChatId || telegramChatId.trim() === '') {
    console.error('ERROR: TELEGRAM_CHAT_ID environment variable is missing or empty');
    console.error('Please set it in your .env file');
    process.exit(1);
}

// Create Telegram notifier
const telegramNotifier = new TelegramNotifier({
    botToken: telegramBotToken,
    chatId: telegramChatId
});

// Log configuration
console.log('Starting enhanced Raydium liquidity monitoring with Telegram integration...');
console.log(`RPC Endpoint: ${rpcEndpoint}`);
console.log(`Telegram Bot Token: ${telegramBotToken.substring(0, 5)}...${telegramBotToken.substring(telegramBotToken.length - 5)}`);
console.log(`Telegram Chat ID: ${telegramChatId}`);
console.log('Press Ctrl+C to stop monitoring\n');

// Send initial status message
telegramNotifier.sendMessage('🚀 <b>Bot Started</b>\n\nRaydium arbitrage monitoring service is now active. You will receive alerts for significant market events.')
    .then(success => {
        if (!success) {
            console.error('Failed to send initial Telegram message. Notifications may not work.');
        }
    })
    .catch(error => {
        console.error('Error sending initial message:', error.message);
    });

// Start enhanced monitoring with Telegram integration
monitorLiquidityFlowEnhanced(
    connection,
    undefined, // Use default duration
    telegramNotifier,
    {
        enableRiskAnalysis: true,
        enableMetrics: true,
        transactionAlerts: true,
        riskManagementAlerts: true
    }
).catch(error => {
    console.error('Fatal error:', error);
    telegramNotifier.sendMessage(`⛔️ <b>Critical Error</b>\n\n${error.message}`).catch(() => {});
    process.exit(1);
});

// Handle graceful shutdown
process.on('SIGINT', async () => {
    console.log('\nReceived shutdown signal...');
    await telegramNotifier.sendMessage('⚠️ <b>Bot Shutting Down</b>\n\nStopping monitoring services...');
    process.exit(0);
});