import { Connection, Keypair, PublicKey, Transaction, TransactionInstruction } from '@solana/web3.js';
import { Token } from '../../models/TokenPair';
import { SolendClient } from '../solend/SolendClient';
import { RaydiumSwap } from '../exchanges/raydium/RaydiumSwap';
import { SOLEND_RESERVES } from '../solend/constants';
import { ArbitrageOpportunity, TokenPath } from '../../models/ArbitrageModels';

/**
 * Example implementation of a flash loan arbitrage using Solend and Raydium
 */
export class FlashLoanArbitrage {
    private solendClient: SolendClient;
    private raydiumSwap: RaydiumSwap;

    constructor(
        private connection: Connection,
        private wallet: Keypair
    ) {
        this.solendClient = new SolendClient(connection);
        this.raydiumSwap = new RaydiumSwap(connection, wallet);
    }

    /**
     * Execute flash loan arbitrage based on an opportunity
     * @param opportunity The arbitrage opportunity to execute
     */
    async executeArbitrage(opportunity: ArbitrageOpportunity): Promise<Transaction> {
        if (!opportunity.tokenPath || opportunity.tokenPath.length < 2) {
            throw new Error('Invalid opportunity: token path must have at least 2 steps');
        }

        const { tokenPath } = opportunity;
        const initialToken = tokenPath[0].token;
        const initialAmount = tokenPath[0].amount;

        // Get Solend reserve info for the initial token
        const tokenMint = new PublicKey(initialToken.address);
        const reserveAccount = new PublicKey(SOLEND_RESERVES[initialToken.symbol] || '');
        const tokenAccount = opportunity.walletTokenAccount || PublicKey.default;

        // Check if flash loan is viable (fees not too high)
        const isViable = await this.solendClient.checkFlashLoanViability(
            initialAmount,
            initialToken.symbol === 'SOL' ? 1 : initialToken.price
        );

        if (!isViable) {
            throw new Error(`Flash loan not viable due to high fees: ${initialAmount} ${initialToken.symbol}`);
        }

        // Create the flash loan with arbitrage execution
        return await this.solendClient.executeFlashLoan(
            initialAmount,
            tokenMint,
            reserveAccount,
            tokenAccount,
            () => this.createArbitrageInstruction(tokenPath)
        );
    }

    /**
     * Create arbitrage instructions for the token path
     */
    private async createArbitrageInstruction(tokenPath: TokenPath[]): Promise<TransactionInstruction> {
        if (tokenPath.length < 2) {
            throw new Error('Token path must have at least 2 steps');
        }

        // For this example, we're just doing a single swap from the first to second token
        // In a real implementation, you would chain multiple swaps to complete the arbitrage
        const firstStep = tokenPath[0];
        const secondStep = tokenPath[1];

        console.log(`Creating swap from ${firstStep.token.symbol} to ${secondStep.token.symbol}`);

        const swapIx = await this.raydiumSwap.createSwapInstruction({
            poolAddress: firstStep.poolAddress,
            tokenIn: firstStep.token,
            tokenOut: secondStep.token,
            amount: firstStep.amount,
            isBuy: false, // We're selling our token
            slippage: 0.005 // 0.5% slippage
        });

        return swapIx;
    }

    /**
     * Estimate profit for an arbitrage opportunity
     */
    async estimateProfit(opportunity: ArbitrageOpportunity): Promise<{ 
        estimatedProfit: number, 
        profitPercentage: number 
    }> {
        if (!opportunity.tokenPath || opportunity.tokenPath.length < 2) {
            throw new Error('Invalid opportunity: token path must have at least 2 steps');
        }

        const { tokenPath } = opportunity;
        const initialToken = tokenPath[0].token;
        const initialAmount = tokenPath[0].amount;
        const finalToken = tokenPath[tokenPath.length - 1].token;
        const finalAmount = opportunity.finalAmount;

        // Calculate flash loan fee
        const flashLoanFee = await this.solendClient.getFlashLoanFee(initialAmount);
        
        // Calculate estimated profit after fees
        const estimatedProfit = finalAmount - initialAmount - flashLoanFee;
        const profitPercentage = estimatedProfit / initialAmount * 100;

        console.log(`Profit estimate: ${estimatedProfit} ${finalToken.symbol} (${profitPercentage.toFixed(2)}%)`);
        console.log(`Flash loan fee: ${flashLoanFee} ${initialToken.symbol}`);

        return {
            estimatedProfit,
            profitPercentage
        };
    }
}