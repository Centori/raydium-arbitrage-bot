import { monitorLiquidityFlow } from './ts-src/tests/test-liquidity-monitor';
import dotenv from 'dotenv';

// Load environment variables
dotenv.config();

// Default monitoring duration of 45 minutes (2700 seconds)
const MONITORING_DURATION = 2700;

// Configure SolAssassin_bot for monitoring
const botConfig = {
  botName: process.env.TELEGRAM_BOT_NAME || 'SolAssassin_bot',
  chatId: process.env.TELEGRAM_CHAT_ID || '',
  token: process.env.TELEGRAM_BOT_TOKEN || ''
};

// Check if SolAssassin_bot is properly configured
if (!botConfig.token || botConfig.token === 'SolAssassin_bot_token_here') {
  console.error('⚠️ WARNING: SolAssassin_bot token not configured properly');
  console.error('Please set your SolAssassin_bot token in the .env file');
} else {
  console.log(`✅ SolAssassin_bot configured for transaction and risk monitoring`);
}

console.log('Starting Raydium liquidity monitoring with SolAssassin_bot...');
console.log('Press Ctrl+C to stop monitoring\n');

// Fixed to use only the duration parameter
monitorLiquidityFlow(MONITORING_DURATION).catch(error => {
    console.error('Fatal error:', error);
    process.exit(1);
});