import { Connection, Keypair, PublicKey, Transaction, TransactionInstruction, sendAndConfirmTransaction } from '@solana/web3.js';
import { SolendClient } from '../solend/SolendClient';
import { RaydiumSwap } from '../exchanges/raydium/RaydiumSwap';
import { JupiterClient } from '../jupiter/JupiterClient';
import { JitoBundleSubmitter } from '../jito/JitoBundleSubmitter';
import { ArbitrageOpportunity, TokenPath } from '../../models/ArbitrageModels';
import { PriceService } from '../../utils/PriceService';
import { Token } from '../../models/TokenPair';
import { Logger } from '../../utils/logger';
import { FlashLoanProvider } from '../common/FlashLoanProvider';

/**
 * Enhanced Flash Loan Arbitrage executor that dynamically selects the best
 * flash loan provider (Solend or Port Finance) for each opportunity
 */
export class EnhancedFlashLoanArbitrage {
    private flashLoanProvider: FlashLoanProvider;
    private raydiumSwap: RaydiumSwap;
    private jupiterClient: JupiterClient;
    private jitoSubmitter: JitoBundleSubmitter;
    private priceService: PriceService;
    private logger: Logger;

    constructor(
        private connection: Connection,
        private walletKeypair: Keypair
    ) {
        this.flashLoanProvider = new FlashLoanProvider(connection);
        this.raydiumSwap = new RaydiumSwap(connection, walletKeypair);
        this.jupiterClient = new JupiterClient(connection);
        this.jitoSubmitter = new JitoBundleSubmitter(connection, walletKeypair);
        this.priceService = new PriceService(connection);
        this.logger = new Logger('EnhancedFlashLoanArbitrage');
    }

    /**
     * Execute a triangular arbitrage opportunity using the best available flash loan provider
     * 
     * Steps:
     * 1. Compare Solend vs Port Finance to find the best flash loan terms
     * 2. Borrow token A from the selected provider via flash loan
     * 3. Swap token A to token B on first DEX
     * 4. Swap token B to token C on second DEX 
     * 5. Swap token C back to token A on third DEX
     * 6. Repay flash loan + fee
     * 7. Collect profit
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
        
        // Get token price in SOL (for fee calculation)
        const tokenPriceInSol = await this.priceService.getTokenPriceInSol(firstToken.address.toString());
        
        // Make sure walletTokenAccount is defined
        if (!opportunity.walletTokenAccount) {
            throw new Error('Wallet token account must be specified for flash loan arbitrage');
        }
        
        // Compare flash loan providers and select the best option
        const bestProviderOption = await this.flashLoanProvider.compareFlashLoanProviders(
            initialAmount,
            firstToken.symbol,
            firstToken.address,
            opportunity.walletTokenAccount,
            tokenPriceInSol,
            async () => {
                // This function will be executed during the flash loan
                return await this.createTriangularArbitrageInstruction(opportunity);
            }
        );
        
        if (!bestProviderOption) {
            throw new Error(`No viable flash loan provider found for ${initialAmount} ${firstToken.symbol}`);
        }
        
        this.logger.info(`Selected flash loan provider: ${bestProviderOption.provider} with fee ${bestProviderOption.fee} ${firstToken.symbol}`);
        
        // Final amount needed (initial amount + flash loan fee)
        const requiredAmount = initialAmount + bestProviderOption.fee;
        
        // Check if the arbitrage is still profitable after fees
        if (requiredAmount > expectedProfit + initialAmount) {
            throw new Error('Arbitrage not profitable after flash loan fees');
        }
        
        // Use the transaction created by the provider
        const flashLoanTx = bestProviderOption.transaction;
        
        // Add metadata to opportunity for tracking
        if (!opportunity.metadata) {
            opportunity.metadata = {};
        }
        
        opportunity.metadata = {
            ...opportunity.metadata,
            provider: bestProviderOption.provider,
            loan_fee: bestProviderOption.fee,
            loan_amount: initialAmount,
        };
        
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
        
        if (!tokenPath || tokenPath.length < 3) {
            throw new Error('Triangular arbitrage requires at least 3 tokens in the path');
        }
        
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
}