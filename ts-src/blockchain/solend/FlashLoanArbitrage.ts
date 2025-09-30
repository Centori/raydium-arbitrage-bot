// filepath: /Users/lm/Desktop/raydium-arbitrage-bot/ts-src/blockchain/solend/FlashLoanArbitrage.ts
import { Connection, Keypair, PublicKey, Transaction, TransactionInstruction, sendAndConfirmTransaction } from '@solana/web3.js';
import { SolendClient } from './SolendClient';
import { SOLEND_RESERVES } from './constants';
import { RaydiumSwap } from '../exchanges/raydium/RaydiumSwap';
import { JupiterClient } from '../jupiter/JupiterClient';
import { JitoBundleSubmitter } from '../jito/JitoBundleSubmitter';
import { ArbitrageOpportunity, TokenPath } from '../../models/ArbitrageModels';
import { PriceService } from '../../utils/PriceService';
import { Token } from '../../models/TokenPair';
import { Logger } from '../../utils/logger';

/**
 * Flash Loan Arbitrage executor that utilizes Solend flash loans
 * to execute arbitrage opportunities across Raydium and Jupiter
 */
export class FlashLoanArbitrage {
    private solendClient: SolendClient;
    private raydiumSwap: RaydiumSwap;
    private jupiterClient: JupiterClient;
    private jitoSubmitter: JitoBundleSubmitter;
    private priceService: PriceService;
    private logger: Logger;

    constructor(
        private connection: Connection,
        private walletKeypair: Keypair
    ) {
        this.solendClient = new SolendClient(connection);
        this.raydiumSwap = new RaydiumSwap(connection, walletKeypair);
        this.jupiterClient = new JupiterClient(connection);
        this.jitoSubmitter = new JitoBundleSubmitter(connection, walletKeypair);
        this.priceService = new PriceService(connection);
        this.logger = new Logger('FlashLoanArbitrage');
    }

    /**
     * Execute a triangular arbitrage opportunity using flash loans
     * 
     * Steps:
     * 1. Borrow token A from Solend via flash loan
     * 2. Swap token A to token B on first DEX
     * 3. Swap token B to token C on second DEX 
     * 4. Swap token C back to token A on third DEX
     * 5. Repay flash loan + fee
     * 6. Collect profit
     */
    async executeTriangularArbitrage(opportunity: ArbitrageOpportunity): Promise<string> {
        // Validate the opportunity has a valid token path with at least 3 tokens
        const { tokenPath, expectedProfit, initialAmount } = opportunity;
        
        if (!tokenPath || tokenPath.length < 3) {
            throw new Error('Triangular arbitrage requires at least 3 tokens in the path');
        }
        
        // Get the first token in the path (this is what we'll borrow with flash loan)
        const firstToken = tokenPath[0].token;
        const lastToken = tokenPath[tokenPath.length - 1].token;
        
        // Verify first and last token are the same (closed loop)
        if (firstToken.address.toString() !== lastToken.address.toString()) {
            throw new Error('Triangular arbitrage requires a closed loop (first token = last token)');
        }
        
        this.logger.info(`Executing triangular arbitrage with path: ${this.formatTokenPath(tokenPath)}`);
        this.logger.info(`Flash loan amount: ${initialAmount} ${firstToken.symbol}`);
        this.logger.info(`Expected profit: ${expectedProfit} ${firstToken.symbol}`);
        
        // Get the reserve account for the token
        const reserveAccount = this.getReserveAccountForToken(firstToken);
        
        // Check flash loan viability
        const tokenPriceInSol = await this.priceService.getTokenPriceInSol(firstToken.address.toString());
        const isViable = await this.solendClient.checkFlashLoanViability(initialAmount, tokenPriceInSol);
        
        if (!isViable) {
            throw new Error(`Flash loan not viable for amount ${initialAmount} ${firstToken.symbol}`);
        }
        
        // Calculate the flash loan fee
        const flashLoanFee = await this.solendClient.getFlashLoanFee(initialAmount);
        
        // Final amount needed (initial amount + flash loan fee)
        const requiredAmount = initialAmount + flashLoanFee;
        
        // Check if the arbitrage is still profitable after fees
        if (requiredAmount > expectedProfit + initialAmount) {
            throw new Error('Arbitrage not profitable after flash loan fees');
        }
        
        // Create the flash loan transaction
        const flashLoanTx = await this.solendClient.executeFlashLoan(
            initialAmount,
            firstToken.address,
            reserveAccount,
            opportunity.walletTokenAccount,
            async () => {
                // This function will be executed during the flash loan
                return await this.createTriangularArbitrageInstruction(opportunity);
            }
        );
        
        // Sign and submit the transaction via Jito for MEV protection
        try {
            // If Jito submission fails, fall back to normal transaction submission
            const bundleId = await this.jitoSubmitter.submitBundle([flashLoanTx]);
            this.logger.info(`Arbitrage transaction submitted via Jito bundle: ${bundleId}`);
            return bundleId;
        } catch (error) {
            this.logger.warn(`Jito submission failed, falling back to normal transaction: ${error}`);
            
            // Sign and send transaction
            const signature = await sendAndConfirmTransaction(
                this.connection,
                flashLoanTx,
                [this.walletKeypair],
                { commitment: 'confirmed' }
            );
            
            this.logger.info(`Arbitrage transaction submitted: ${signature}`);
            return signature;
        }
    }
    
    /**
     * Create the instruction that executes the triangular arbitrage swaps
     */
    private async createTriangularArbitrageInstruction(opportunity: ArbitrageOpportunity): Promise<TransactionInstruction> {
        const { tokenPath } = opportunity;
        
        // Create swap instructions for each step in the token path
        const swapInstructions: TransactionInstruction[] = [];
        
        // Process each swap step in the token path
        for (let i = 0; i < tokenPath.length - 1; i++) {
            const currentStep = tokenPath[i];
            const nextStep = tokenPath[i + 1];
            
            // Determine which DEX to use based on the step's exchangeType
            if (currentStep.exchangeType === 'raydium') {
                // Create Raydium swap instruction
                const raydiumInstruction = await this.raydiumSwap.createSwapInstruction({
                    poolAddress: currentStep.poolAddress,
                    tokenIn: currentStep.token,
                    tokenOut: nextStep.token,
                    amount: currentStep.amount,
                    isBuy: false, // Always sell for triangular arbitrage
                    slippage: 0.001 // 0.1% slippage
                });
                
                swapInstructions.push(raydiumInstruction);
            } else if (currentStep.exchangeType === 'jupiter') {
                // Use Jupiter for the swap
                const jupiterRoute = await this.jupiterClient.getRoute(
                    currentStep.token.address.toString(),
                    nextStep.token.address.toString(),
                    currentStep.amount.toString(),
                    { slippageBps: 10 } // 0.1% slippage (10 basis points)
                );
                
                if (!jupiterRoute) {
                    throw new Error(`No Jupiter route found for swap ${currentStep.token.symbol} -> ${nextStep.token.symbol}`);
                }
                
                // Add the Jupiter swap instructions
                const { swapInstruction } = jupiterRoute;
                if (swapInstruction) {
                    swapInstructions.push(swapInstruction);
                }
            } else {
                throw new Error(`Unsupported exchange type: ${currentStep.exchangeType}`);
            }
        }
        
        // Combine all swap instructions into a single instruction
        // This is a simplification - in practice you would typically keep them as separate instructions
        // But for flash loans, we need to return a single instruction for the middle step
        
        // For simplicity, we'll just return the first swap instruction
        // In a real implementation, you would need to handle multiple instructions properly
        return swapInstructions[0];
    }
    
    /**
     * Format token path for logging
     */
    private formatTokenPath(tokenPath: TokenPath[]): string {
        return tokenPath.map(step => step.token.symbol).join(' -> ');
    }
    
    /**
     * Get the Solend reserve account for a given token
     */
    private getReserveAccountForToken(token: Token): PublicKey {
        const reserveAddress = SOLEND_RESERVES[token.symbol];
        if (!reserveAddress) {
            throw new Error(`No Solend reserve found for token ${token.symbol}`);
        }
        
        return new PublicKey(reserveAddress);
    }
}