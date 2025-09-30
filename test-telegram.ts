/**
 * Simple test script to verify Telegram integration
 * Run with: ts-node test-telegram.ts
 */

import dotenv from 'dotenv';
import axios from 'axios';
import * as fs from 'fs';
import * as path from 'path';

// Load environment variables
dotenv.config();

// Main test function
async function runTests() {
  console.log('Starting Telegram integration tests...');
  
  // Use hardcoded values for testing (correct values from your .env file)
  const token = '7370347913:AAFtgEJvRiHVIGXytI7YANXHzhDVGaOcteE';
  const chatId = '895455956'; 
  
  console.log(`Using token: ${token.substring(0, 5)}...${token.substring(token.length - 5)}`);
  console.log(`Using chat ID: ${chatId}`);
  
  // Test the token
  try {
    console.log('Testing Telegram token...');
    const tokenResponse = await axios.get(
      `https://api.telegram.org/bot${token}/getMe`,
      { timeout: 10000 }
    );
    
    if (tokenResponse.status === 200 && tokenResponse.data.ok) {
      console.log('✅ Telegram token is valid');
      console.log(`Bot info: @${tokenResponse.data.result.username} (${tokenResponse.data.result.first_name})`);
    } else {
      console.error('❌ Telegram token validation failed');
      process.exit(1);
    }
  } catch (error: any) {
    console.error('❌ Error validating Telegram token:', error.message);
    process.exit(1);
  }
  
  // Test sending a message
  try {
    const testMessage = `🧪 Test message from Raydium Bot\nTimestamp: ${new Date().toISOString()}`;
    console.log(`Attempting to send message to chat ID: ${chatId}`);
    
    const messageResponse = await axios.post(
      `https://api.telegram.org/bot${token}/sendMessage`,
      {
        chat_id: chatId,
        text: testMessage,
        parse_mode: 'HTML'
      },
      { timeout: 10000 }
    );
    
    if (messageResponse.status === 200 && messageResponse.data.ok) {
      console.log('✅ Test message sent successfully');
      console.log('✅ All tests passed! Telegram integration is working correctly.');
    } else {
      console.error('❌ Failed to send test message');
      process.exit(1);
    }
  } catch (error: any) {
    console.error('❌ Error sending test message:', error.message);
    if (error.response) {
      console.error('API error details:', error.response.data);
    }
    process.exit(1);
  }
}

// Run the tests
runTests().catch((error: any) => {
  console.error('Fatal error during tests:', error);
  process.exit(1);
});