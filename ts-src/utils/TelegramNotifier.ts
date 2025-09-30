import axios from 'axios';
import { BotConfig, TradeRecommendation } from '../../ts-src/models/BotConfig';

export interface TradingConfig {
    defaultSolAmount: number;
    maxSlippageBps: number;
    priorityFeeLamports: number;
    flashLoanFeeBps: number;
    bribesEnabled: boolean;
    bribeLamports: number;
    autoExecutionEnabled: boolean;
}

export class TelegramNotifier {
    private botToken: string = '';
    private chatId: string = '';
    private apiUrl: string = '';
    private config: BotConfig = {
        enableNotifications: true,
        notificationLevel: 'all'
    };
    private tradingConfig: TradingConfig = {
        defaultSolAmount: 0.1,
        maxSlippageBps: 100, // 1%
        priorityFeeLamports: 10000,
        flashLoanFeeBps: 30, // 0.3% Solend fee
        bribesEnabled: false,
        bribeLamports: 10000,
        autoExecutionEnabled: false
    };

    // Rate limiting parameters
    private lastMessageTime = 0;
    private readonly MIN_MESSAGE_INTERVAL = 500; // Base interval 500ms
    private readonly MAX_RETRY_ATTEMPTS = 3;
    private readonly MAX_BACKOFF_TIME = 30000; // Maximum backoff of 30 seconds
    private readonly RATE_LIMIT_WINDOW = 60000; // 1 minute window
    private messageCount = 0;
    private readonly MAX_MESSAGES_PER_WINDOW = 20; // Max 20 messages per minute

    constructor(config: { botToken: string; chatId: string }) {
        this.botToken = config.botToken;
        this.chatId = config.chatId;

        // Validate token and chat ID
        if (!this.botToken || this.botToken.trim() === '') {
            console.error('TelegramNotifier: Bot token is missing or empty. Notifications will not work.');
        }

        if (!this.chatId || this.chatId.trim() === '') {
            console.error('TelegramNotifier: Chat ID is missing or empty. Notifications will not work.');
        }

        this.apiUrl = `https://api.telegram.org/bot${this.botToken}`;

        // Initial setup verification
        this.verifyConnection().catch(err => {
            console.error('TelegramNotifier: Failed to verify Telegram connection:', err.message);
        });
    }

    private async verifyConnection(): Promise<void> {
        if (!this.botToken || !this.chatId) {
            return;
        }

        try {
            const response = await axios.get(`${this.apiUrl}/getMe`, {
                timeout: 10000
            });

            if (response.status === 200 && response.data.ok) {
                const botInfo = response.data.result;
                console.log(`TelegramNotifier: Successfully connected to Telegram API as @${botInfo.username}`);
            } else {
                console.error('TelegramNotifier: Failed to connect to Telegram API. Response:', response.data);
            }
        } catch (error: any) {
            console.error('TelegramNotifier: Connection verification failed:', error.message);
            if (error.response) {
                console.error('API response:', error.response.data);
            }
            throw error;
        }
    }

    private async rateLimiter(): Promise<void> {
        const now = Date.now();

        // Reset message count if we're in a new window
        if (now - this.lastMessageTime > this.RATE_LIMIT_WINDOW) {
            this.messageCount = 0;
        }

        // Check if we've exceeded rate limit
        if (this.messageCount >= this.MAX_MESSAGES_PER_WINDOW) {
            const timeToWait = this.RATE_LIMIT_WINDOW - (now - this.lastMessageTime);
            if (timeToWait > 0) {
                await new Promise(resolve => setTimeout(resolve, timeToWait));
            }
            this.messageCount = 0;
        }

        const timeSinceLastMessage = now - this.lastMessageTime;
        if (timeSinceLastMessage < this.MIN_MESSAGE_INTERVAL) {
            await new Promise(resolve =>
                setTimeout(resolve, this.MIN_MESSAGE_INTERVAL - timeSinceLastMessage)
            );
        }

        this.messageCount++;
        this.lastMessageTime = Date.now();
    }

    private async sendMessageWithRetry(text: string, parseMode: 'HTML' | 'Markdown' = 'HTML', retryCount = 0): Promise<boolean> {
        if (!this.botToken || !this.chatId) {
            console.error('TelegramNotifier: Cannot send message - Bot token or Chat ID is missing');
            return false;
        }

        try {
            // Rate limiting protection
            await this.rateLimiter();

            // Log the message attempt (debug only the first few chars to avoid flooding logs)
            console.log(`TelegramNotifier: Sending message to chat ${this.chatId.substring(0, 4)}****: ${text.substring(0, 30)}...`);

            const response = await axios.post(`${this.apiUrl}/sendMessage`, {
                chat_id: this.chatId,
                text: text.slice(0, 4096), // Telegram message length limit
                parse_mode: parseMode,
                disable_web_page_preview: true
            }, {
                timeout: 15000 // 15 second timeout
            });

            if (response.status === 200 && response.data.ok) {
                console.log('TelegramNotifier: Message sent successfully');
                return true;
            } else {
                console.error('TelegramNotifier: Message not sent. Response:', response.data);
                return false;
            }
        } catch (error: any) {
            if (error.response?.status === 429 && retryCount < this.MAX_RETRY_ATTEMPTS) {
                // Get retry_after from Telegram response if available
                const retryAfter = error.response.data?.parameters?.retry_after || 1;
                const backoffTime = Math.min(
                    Math.pow(2, retryCount) * 1000 * retryAfter,
                    this.MAX_BACKOFF_TIME
                );

                console.log(`TelegramNotifier: Rate limited. Retrying after ${backoffTime}ms (Attempt ${retryCount + 1}/${this.MAX_RETRY_ATTEMPTS})`);
                await new Promise(resolve => setTimeout(resolve, backoffTime));

                return this.sendMessageWithRetry(text, parseMode, retryCount + 1);
            }

            console.error('TelegramNotifier: Send error:', error.message);
            if (error.code === 'ENOTFOUND' || error.code === 'ECONNREFUSED' || error.code === 'ETIMEDOUT') {
                console.error('TelegramNotifier: Network connectivity issue. Will retry after delay.');
                if (retryCount < this.MAX_RETRY_ATTEMPTS) {
                    const backoffTime = Math.min(
                        Math.pow(2, retryCount) * 1000,
                        this.MAX_BACKOFF_TIME
                    );
                    await new Promise(resolve => setTimeout(resolve, backoffTime));
                    return this.sendMessageWithRetry(text, parseMode, retryCount + 1);
                }
            }

            await this.handleError(error, 'Sending message');
            return false;
        }
    }

    public async sendMessage(text: string, parseMode: 'HTML' | 'Markdown' = 'HTML'): Promise<boolean> {
        if (!text || text.trim() === '') {
            console.error('TelegramNotifier: Cannot send empty message');
            return false;
        }
        return this.sendMessageWithRetry(text, parseMode);
    }

    private async handleError(error: any, context: string): Promise<void> {
        let errorMessage = '⚠️ Error';

        if (error.response) {
            // Handle API errors
            switch (error.response.status) {
                case 400:
                    errorMessage = '⚠️ Invalid request parameters';
                    break;
                case 401:
                    errorMessage = '⚠️ Bot authentication failed. Please check your bot token';
                    break;
                case 403:
                    errorMessage = '⚠️ Bot lacks permissions for this action';
                    break;
                case 429:
                    errorMessage = '⚠️ Rate limit exceeded. Please wait a moment';
                    break;
                default:
                    errorMessage = `⚠️ API Error: ${error.response.status}`;
            }
        } else if (error.request) {
            errorMessage = '⚠️ Network error. Please check your connection';
        } else if (error instanceof Error) {
            // Handle validation and runtime errors
            if (error.message.includes('ENOTFOUND')) {
                errorMessage = '⚠️ Could not connect to Telegram API';
            } else if (error.message.includes('timeout')) {
                errorMessage = '⚠️ Request timed out. Please try again';
            } else {
                errorMessage = `⚠️ ${error.message}`;
            }
        }

        // Add context to error message
        errorMessage += `\nContext: ${context}`;

        // Log error for debugging
        console.error(`Telegram Bot Error (${context}):`, error);

        try {
            await this.sendMessage(errorMessage);
        } catch (sendError) {
            console.error('Failed to send error message:', sendError);
        }
    }

    public async handleCommand(command: string, args: string[]): Promise<void> {
        try {
            switch (command) {
                case '/setamount':
                    await this.handleSetAmount(args);
                    break;
                case '/setslippage':
                    await this.handleSetSlippage(args);
                    break;
                case '/setpriorityfee':
                    await this.handleSetPriorityFee(args);
                    break;
                case '/setflashfee':
                    await this.handleSetFlashLoanFee(args);
                    break;
                case '/togglebribes':
                    await this.handleToggleBribes(args);
                    break;
                case '/setbribe':
                    await this.handleSetBribe(args);
                    break;
                case '/toggleauto':
                    await this.handleToggleAutoExecution();
                    break;
                case '/config':
                    await this.handleShowConfig();
                    break;
                case '/help':
                    await this.handleHelp();
                    break;
                default:
                    const availableCommands = [
                        '/setamount', '/setslippage', '/setpriorityfee',
                        '/setflashfee', '/togglebribes', '/setbribe',
                        '/toggleauto', '/config', '/help'
                    ];

                    // Find closest matching command for typos
                    const closestMatch = this.findClosestCommand(command, availableCommands);
                    if (closestMatch) {
                        await this.sendMessage(`❌ Unknown command. Did you mean "${closestMatch}"?\nType /help to see all available commands.`);
                    } else {
                        await this.sendMessage('❌ Unknown command. Type /help to see available commands.');
                    }
            }
        } catch (error) {
            await this.handleError(error, `Command: ${command}`);
        }
    }

    private findClosestCommand(input: string, commands: string[]): string | null {
        // Simple Levenshtein distance for command suggestions
        const getDistance = (a: string, b: string): number => {
            if (a.length === 0) return b.length;
            if (b.length === 0) return a.length;

            const matrix: number[][] = [];

            // Initialize first row and column
            for (let i = 0; i <= b.length; i++) {
                matrix[i] = [i];
            }
            for (let j = 0; j <= a.length; j++) {
                if (!matrix[0]) matrix[0] = [];
                matrix[0][j] = j;
            }

            // Fill in the rest of the matrix
            for (let i = 1; i <= b.length; i++) {
                for (let j = 1; j <= a.length; j++) {
                    if (!matrix[i]) matrix[i] = [];
                    if (b.charAt(i - 1) === a.charAt(j - 1)) {
                        matrix[i][j] = matrix[i - 1][j - 1];
                    } else {
                        matrix[i][j] = Math.min(
                            matrix[i - 1][j - 1] + 1,
                            matrix[i][j - 1] + 1,
                            matrix[i - 1][j] + 1
                        );
                    }
                }
            }
            return matrix[b.length][a.length];
        };

        let closestCommand: string | null = null;
        let minDistance = Infinity;

        for (const cmd of commands) {
            const distance = getDistance(input, cmd);
            if (distance < minDistance && distance <= 3) { // Max 3 character difference
                minDistance = distance;
                closestCommand = cmd;
            }
        }

        return closestCommand;
    }

    private async handleSetAmount(args: string[]): Promise<void> {
        if (args.length !== 1 || isNaN(parseFloat(args[0]))) {
            await this.sendMessage('❌ Invalid format. Use: /setamount <sol_amount>\nExample: /setamount 0.5');
            return;
        }
        const amount = parseFloat(args[0]);
        if (amount <= 0 || amount > 100) {
            await this.sendMessage('❌ Amount must be between 0 and 100 SOL');
            return;
        }
        this.tradingConfig.defaultSolAmount = amount;
        await this.sendMessage(`✅ Default trading amount set to ${amount} SOL`);
    }

    private async handleSetSlippage(args: string[]): Promise<void> {
        if (args.length !== 1 || isNaN(parseFloat(args[0]))) {
            await this.sendMessage('❌ Invalid format. Use: /setslippage <basis_points>\nExample: /setslippage 100');
            return;
        }
        const bps = parseInt(args[0]);
        if (bps < 0 || bps > 1000) {
            await this.sendMessage('❌ Slippage must be between 0 and 1000 basis points (0-10%)');
            return;
        }
        this.tradingConfig.maxSlippageBps = bps;
        await this.sendMessage(`✅ Max slippage set to ${bps} bps (${(bps / 100).toFixed(2)}%)`);
    }

    private async handleSetPriorityFee(args: string[]): Promise<void> {
        if (args.length !== 1 || isNaN(parseInt(args[0]))) {
            await this.sendMessage('❌ Invalid format. Use: /setpriorityfee <lamports>\nExample: /setpriorityfee 10000');
            return;
        }
        const lamports = parseInt(args[0]);
        if (lamports < 0 || lamports > 1000000) {
            await this.sendMessage('❌ Priority fee must be between 0 and 1,000,000 lamports');
            return;
        }
        this.tradingConfig.priorityFeeLamports = lamports;
        await this.sendMessage(`✅ Priority fee set to ${lamports} lamports (${(lamports / 1e9).toFixed(6)} SOL)`);
    }

    private async handleSetFlashLoanFee(args: string[]): Promise<void> {
        if (args.length !== 1 || isNaN(parseInt(args[0]))) {
            await this.sendMessage('❌ Invalid format. Use: /setflashfee <basis_points>\nExample: /setflashfee 30');
            return;
        }
        const bps = parseInt(args[0]);
        if (bps < 0 || bps > 200) {
            await this.sendMessage('❌ Flash loan fee must be between 0 and 200 basis points (0-2%)');
            return;
        }
        this.tradingConfig.flashLoanFeeBps = bps;
        await this.sendMessage(`✅ Flash loan fee set to ${bps} bps (${(bps / 100).toFixed(2)}%)`);
    }

    private async handleToggleBribes(args: string[]): Promise<void> {
        this.tradingConfig.bribesEnabled = !this.tradingConfig.bribesEnabled;
        await this.sendMessage(`✅ Bribes ${this.tradingConfig.bribesEnabled ? 'enabled' : 'disabled'}`);
    }

    private async handleSetBribe(args: string[]): Promise<void> {
        if (args.length !== 1 || isNaN(parseInt(args[0]))) {
            await this.sendMessage('❌ Invalid format. Use: /setbribe <lamports>\nExample: /setbribe 10000');
            return;
        }
        const lamports = parseInt(args[0]);
        if (lamports < 0 || lamports > 1000000) {
            await this.sendMessage('❌ Bribe amount must be between 0 and 1,000,000 lamports');
            return;
        }
        this.tradingConfig.bribeLamports = lamports;
        await this.sendMessage(`✅ Bribe amount set to ${lamports} lamports (${(lamports / 1e9).toFixed(6)} SOL)`);
    }

    private async handleToggleAutoExecution(): Promise<void> {
        this.tradingConfig.autoExecutionEnabled = !this.tradingConfig.autoExecutionEnabled;
        await this.sendMessage(`✅ Auto-execution ${this.tradingConfig.autoExecutionEnabled ? 'enabled' : 'disabled'}`);
    }

    private async handleShowConfig(): Promise<void> {
        const config = this.tradingConfig;
        const message = `
🔧 <b>Current Configuration</b>

💰 Trading Amount: ${config.defaultSolAmount} SOL
📊 Max Slippage: ${config.maxSlippageBps} bps (${(config.maxSlippageBps / 100).toFixed(2)}%)
⚡️ Priority Fee: ${config.priorityFeeLamports} lamports (${(config.priorityFeeLamports / 1e9).toFixed(6)} SOL)
💸 Flash Loan Fee: ${config.flashLoanFeeBps} bps (${(config.flashLoanFeeBps / 100).toFixed(2)}%)
🎁 Bribes: ${config.bribesEnabled ? 'Enabled' : 'Disabled'}
💎 Bribe Amount: ${config.bribeLamports} lamports (${(config.bribeLamports / 1e9).toFixed(6)} SOL)
🤖 Auto-execution: ${config.autoExecutionEnabled ? 'Enabled' : 'Disabled'}
`;
        await this.sendMessage(message);
    }

    private async handleHelp(): Promise<void> {
        const helpMessage = `
🤖 <b>SolAssassin Bot Commands</b>

💰 Trading Configuration:
/setamount <sol> - Set default trading amount
/setslippage <bps> - Set max slippage in basis points
/setpriorityfee <lamports> - Set priority fee
/setflashfee <bps> - Set flash loan fee in basis points

🎁 MEV Features:
/togglebribes - Enable/disable validator bribes
/setbribe <lamports> - Set bribe amount
/toggleauto - Enable/disable auto-execution

ℹ️ Info Commands:
/config - Show current configuration
/status - Check bot status
/balance - Check wallet balance
/help - Show this help message

Examples:
/setamount 0.5
/setslippage 100
/setpriorityfee 10000
/setflashfee 30

<i>Example: /buy SOL 0.5</i>
`;
        await this.sendMessage(helpMessage);
    }

    /**
     * Sends a trade recommendation to Telegram
     */
    public async sendTradeRecommendation(rec: TradeRecommendation): Promise<boolean> {
        if (!this.config.enableNotifications) return false;

        // Create an emoji based on the recommendation
        const emoji = rec.recommendation === 'BUY'
            ? '🟢'
            : rec.recommendation === 'SELL'
                ? '🔴'
                : '⚪';

        // Format the decision
        const decision = rec.decision === 'YES'
            ? '<b>YES ✅</b>'
            : '<b>NO ❌</b>';

        // Risk level emoji
        const riskEmoji = rec.riskLevel === 'LOW'
            ? '🟢'
            : rec.riskLevel === 'MEDIUM'
                ? '🟡'
                : '🔴';

        // Add quick action buttons for recommended trades
        const actionText = rec.decision === 'YES' ? `\n\n<b>Actions:</b> /buy_${rec.tokenSymbol.toLowerCase()} ${rec.tradingAmount}` : '';

        // Build the message
        const message = `
${emoji} <b>${rec.recommendation}</b> ${rec.tokenSymbol} (${rec.tokenName || 'Unknown Token'})

Decision: ${decision}
Confidence: ${rec.confidence.toFixed(1)}%
Amount: ${rec.tradingAmount} SOL
Expected Return: ${rec.expectedReturn.toFixed(4)} SOL
Risk Level: ${riskEmoji} ${rec.riskLevel}

<b>Analysis:</b>
${rec.reasoning.map(reason => `• ${reason}`).join('\n')}
${actionText}
`;

        return this.sendMessage(message);
    }

    /**
     * Sends a trade execution result to Telegram
     */
    public async sendTradeResult(success: boolean, action: 'BUY' | 'SELL', symbol: string, amount: number, txId?: string): Promise<boolean> {
        const emoji = success ? '✅' : '❌';
        const actionEmoji = action === 'BUY' ? '🟢' : '🔴';
        const txLink = txId ? `\n\nTransaction: <a href="https://solscan.io/tx/${txId}">View on Solscan</a>` : '';

        const message = `
${emoji} ${actionEmoji} <b>${action} ${symbol}</b>

Amount: ${amount} SOL
Status: ${success ? 'Successful' : 'Failed'}${txLink}
`;
        return this.sendMessage(message);
    }

    /**
     * Sends a wallet balance update to Telegram
     */
    public async sendBalanceUpdate(balance: number, profitLoss: number): Promise<boolean> {
        if (!this.config.enableNotifications) return false;

        const emoji = profitLoss >= 0 ? '📈' : '📉';
        const profitLossText = profitLoss >= 0
            ? `<b>+${profitLoss.toFixed(4)}</b>`
            : `<b>${profitLoss.toFixed(4)}</b>`;

        const message = `
${emoji} <b>Wallet Update</b>

Current Balance: <b>${balance.toFixed(4)} SOL</b>
Profit/Loss: ${profitLossText} SOL
`;

        return this.sendMessage(message);
    }
}