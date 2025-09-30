import axios from 'axios';
import * as dotenv from 'dotenv';

// Load environment variables
dotenv.config();

/**
 * Registers commands with the Telegram Bot API to create a visible command menu
 */
export class TelegramBotSetup {
    private botToken: string;
    private apiUrl: string;

    constructor(botToken?: string) {
        this.botToken = botToken || process.env.TELEGRAM_BOT_TOKEN || '';
        this.apiUrl = `https://api.telegram.org/bot${this.botToken}`;
    }

    /**
     * Registers the bot commands with Telegram to create a visible menu
     */
    public async registerBotCommands(): Promise<boolean> {
        if (!this.botToken) {
            console.error('Telegram bot token is not set');
            return false;
        }

        try {
            // Define the commands that will appear in the Telegram menu
            const commands = [
                { command: 'buy', description: 'Buy a token - /buy SOL 0.5' },
                { command: 'sell', description: 'Sell a token - /sell SOL 0.5' },
                { command: 'status', description: 'Check bot status and metrics' },
                { command: 'balance', description: 'Check wallet balance' },
                { command: 'setamount', description: 'Set default trading amount - /setamount 0.5' },
                { command: 'help', description: 'Show available commands' }
            ];

            // Register the commands with Telegram
            const response = await axios.post(`${this.apiUrl}/setMyCommands`, {
                commands: commands
            });

            if (response.status === 200 && response.data.ok) {
                console.log('Successfully registered bot commands with Telegram');
                return true;
            } else {
                console.error('Failed to register bot commands:', response.data);
                return false;
            }
        } catch (error) {
            console.error('Error registering bot commands:', error);
            return false;
        }
    }

    /**
     * Sends a test message to the specified chat ID
     */
    public async sendTestMessage(chatId: string): Promise<boolean> {
        if (!this.botToken) {
            console.error('Telegram bot token is not set');
            return false;
        }

        try {
            const response = await axios.post(`${this.apiUrl}/sendMessage`, {
                chat_id: chatId,
                text: '🤖 <b>Raydium Arbitrage Bot</b>\n\nConnection test successful! The bot is properly configured.\n\nType /help to see available commands.',
                parse_mode: 'HTML'
            });

            return response.status === 200 && response.data.ok;
        } catch (error) {
            console.error('Error sending test message:', error);
            return false;
        }
    }
}

// This allows the file to be executed directly for command registration
if (require.main === module) {
    const setup = new TelegramBotSetup();
    
    (async () => {
        const chatId = process.env.TELEGRAM_CHAT_ID;
        if (!chatId) {
            console.error('TELEGRAM_CHAT_ID is not set in environment variables');
            process.exit(1);
        }
        
        // Register commands
        const commandsResult = await setup.registerBotCommands();
        console.log(`Command registration ${commandsResult ? 'successful' : 'failed'}`);
        
        // Send test message
        const messageResult = await setup.sendTestMessage(chatId);
        console.log(`Test message ${messageResult ? 'sent successfully' : 'failed'}`);
        
        process.exit(0);
    })();
}