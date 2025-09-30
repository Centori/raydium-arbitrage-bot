import { Connection, Keypair, PublicKey, TransactionInstruction } from '@solana/web3.js';
import { SolendClient } from './SolendClient';
import { SOLEND_RESERVES } from './constants';
import { ArbitrageOpportunity } from '../../models/ArbitrageModels';
import { JitoBundleSubmitter } from '../jito/JitoBundleSubmitter';
import { RaydiumSwap } from '../exchanges/raydium/RaydiumSwap';
import { Token } from '../../models/TokenPair';
import { GlasshotClient } from '../glasshot/GlasshotClient';

export class FlashLoanExecutor {
    private solendClient: SolendClient;
    private jitoSubmitter: JitoBundleSubmitter;
    private connection: Connection;
    private raydiumSwap: RaydiumSwap;
    private glasshotClient: GlasshotClient;

    constructor(
        connection: Connection,
        walletKeypair: Keypair
    ) {
        this.connection = connection;
        this.solendClient = new SolendClient(connection);
        this.jitoSubmitter = new JitoBundleSubmitter(connection, walletKeypair);
        this.raydiumSwap = new RaydiumSwap(connection, walletKeypair);
        this.glasshotClient = new GlasshotClient();
    }

    async executeArbitrageWithFlashLoan(opportunity: ArbitrageOpportunity): Promise<string> {
        const { token, initialAmount, finalAmount } = opportunity;
        
        // Get reserve account for the token
        const reserveAccount = new PublicKey(SOLEND_RESERVES[token.symbol]);
        
        // Calculate required flash loan amount including fees
        const flashLoanAmount = initialAmount;
        
        // Get token price in SOL if needed (for non-SOL tokens)
        let tokenPriceInSol = 1.0; // Default for SOL
        if (token.symbol !== 'SOL') {
            try {
                // Try to fetch token price from Glasshot API first
                tokenPriceInSol = await this.getTokenPriceFromGlasshot(token.address.toString());
                console.log(`[Glasshot] Token price for ${token.symbol}: ${tokenPriceInSol} SOL`);
            } catch (error) {
                // Fall back to the original price method
                try {
                    tokenPriceInSol = await this.getTokenPriceInSol(token.symbol);
                    console.log(`[Fallback] Token price for ${token.symbol}: ${tokenPriceInSol} SOL`);
                } catch (fallbackError) {
                    console.warn(`Failed to get price for ${token.symbol}, using default: 1.0`);
                }
            }
        }
        
        // Check if the flash loan is viable (fees <= 0.1 SOL)
        const isViable = await this.solendClient.checkFlashLoanViability(flashLoanAmount, tokenPriceInSol);
        if (!isViable) {
            throw new Error(`Flash loan fee would exceed 0.1 SOL for amount ${flashLoanAmount} ${token.symbol}`);
        }
        
        // Calculate fees and required repayment amount
        const flashLoanFee = await this.solendClient.getFlashLoanFee(flashLoanAmount);
        const requiredRepayAmount = flashLoanAmount + flashLoanFee;
        
        // Verify profitability after flash loan fees
        const expectedProfit = finalAmount - requiredRepayAmount;
        if (expectedProfit <= 0) {
            throw new Error('Opportunity not profitable after flash loan fees');
        }

        console.log(`Executing arbitrage with flash loan: ${flashLoanAmount} ${token.symbol}`);
        console.log(`Expected profit: ${expectedProfit} ${token.symbol} (${expectedProfit * tokenPriceInSol} SOL)`);
        
        // Create flash loan transaction
        const flashLoanTx = await this.solendClient.executeFlashLoan(
            flashLoanAmount,
            token.address,
            reserveAccount,
            opportunity.route.walletTokenAccount,
            async () => {
                // Execute the arbitrage instruction
                return await this.createArbitrageInstruction(opportunity);
            }
        );

        // Submit transaction via Jito MEV bundle
        const bundleId = await this.jitoSubmitter.submitBundle([flashLoanTx]);
        return bundleId;
    }

    private async createArbitrageInstruction(opportunity: ArbitrageOpportunity): Promise<TransactionInstruction> {
        const { route, token, initialAmount, finalAmount } = opportunity;
        
        // Create swap instruction for entry pool
        const entryPoolSwapIx = await this.createSwapInstruction(
            route.entryPool,
            token,
            initialAmount,
            true // isBuy
        );

        // Create swap instruction for exit pool
        const exitPoolSwapIx = await this.createSwapInstruction(
            route.exitPool,
            token,
            finalAmount,
            false // isSell
        );

        // Combine instructions by concatenating their accounts and data
        const combinedKeys = [...entryPoolSwapIx.keys, ...exitPoolSwapIx.keys];
        const combinedData = Buffer.concat([entryPoolSwapIx.data, exitPoolSwapIx.data]);

        // Create a new instruction that combines both swaps
        return new TransactionInstruction({
            keys: combinedKeys,
            programId: route.entryPool,
            data: combinedData
        });
    }

    private async createSwapInstruction(
        poolAddress: PublicKey,
        token: Token,
        amount: number,
        isBuy: boolean
    ): Promise<TransactionInstruction> {
        return this.raydiumSwap.createSwapInstruction({
            poolAddress,
            tokenIn: token,
            tokenOut: token, // For flash loans, we're swapping the same token
            amount,
            isBuy,
            slippage: 0.01 // 1% default slippage
        });
    }
    
    /**
     * Get token price from Glasshot API
     * @param tokenAddress The mint address of the token
     * @returns Price in SOL
     */
    private async getTokenPriceFromGlasshot(tokenAddress: string): Promise<number> {
        try {
            const priceData = await this.glasshotClient.getTokenPrice(tokenAddress);
            
            // Extract SOL price from the response
            if (priceData && priceData.solPrice) {
                return parseFloat(priceData.solPrice);
            }
            
            throw new Error('Invalid price data format from Glasshot API');
        } catch (error) {
            console.error(`Error fetching price from Glasshot: ${error}`);
            throw error;
        }
    }
    
    private async getTokenPriceInSol(symbol: string): Promise<number> {
        // This is a placeholder - implement your actual price fetching logic here
        // You can use any available price oracle like Pyth, Switchboard, or your own price service
        
        // For testing, return some hardcoded values
        const mockPrices: {[key: string]: number} = {
            'USDC': 0.033, // 1 USDC = 0.033 SOL
            'USDT': 0.033,
            'ETH': 30.0,   // 1 ETH = 30 SOL
            'BTC': 450.0,  // 1 BTC = 450 SOL
            'RAY': 0.005,  // 1 RAY = 0.005 SOL
            'SRM': 0.001   // 1 SRM = 0.001 SOL
        };
        
        return mockPrices[symbol] || 0.01; // Default to 0.01 if token not found
    }
}