import { Connection, Keypair, PublicKey, Transaction, TransactionInstruction } from '@solana/web3.js';
import { ArbitrageOpportunity } from '../../models/ArbitrageOpportunity';
import { Token } from '../../models/TokenPair';
import { SolendClient } from '../../blockchain/solend/SolendClient';
import { RaydiumSwap } from './RaydiumSwap';
import { SOLEND_RESERVES } from '../../blockchain/solend/constants';

/**
 * Executes arbitrage opportunities using Raydium swaps and Solend flash loans
 */
export class ArbitrageExecutor {
    private solendClient: SolendClient;
    private raydiumSwap: RaydiumSwap;
    
    /**
     * Creates a new ArbitrageExecutor instance
     * @param connection The Solana connection
     * @param wallet The user's wallet keypair
     */
    constructor(
        private connection: Connection,
        private wallet: Keypair
    ) {
        this.solendClient = new SolendClient(connection);
        this.raydiumSwap = new RaydiumSwap(connection);
    }
    
    /**
     * Execute an arbitrage opportunity
     * @param opportunity The arbitrage opportunity to execute
     * @returns Transaction signature if successful
     */
    public async executeArbitrage(opportunity: ArbitrageOpportunity): Promise<string> {
        console.log(`Executing arbitrage: ${opportunity.getRouteDescription()}`);
        
        if (!opportunity.isProfitable()) {
            throw new Error('Cannot execute unprofitable arbitrage opportunity');
        }
        
        const {
            path: { startToken, midToken, endToken, firstPair, secondPair },
            inputAmount
        } = opportunity;
        
        // Determine if we need a flash loan based on wallet balance
        const useFlashLoan = await this.shouldUseFlashLoan(startToken, inputAmount);
        
        if (useFlashLoan) {
            return this.executeWithFlashLoan(opportunity);
        } else {
            return this.executeWithWalletFunds(opportunity);
        }
    }
    
    /**
     * Execute arbitrage using tokens from wallet
     */
    private async executeWithWalletFunds(opportunity: ArbitrageOpportunity): Promise<string> {
        const {
            path: { startToken, midToken, endToken, firstPair, secondPair },
            inputAmount,
            expectedOutputAmount
        } = opportunity;
        
        console.log(`Executing arbitrage with wallet funds: ${inputAmount} ${startToken.symbol}`);
        
        try {
            const walletPubkey = this.wallet.publicKey;
            
            // Create first swap transaction
            const firstSwapTransaction = await this.raydiumSwap.createSwapTransaction(
                walletPubkey,
                startToken,
                midToken,
                inputAmount,
                1.0, // 1% slippage tolerance
                new PublicKey(firstPair.poolAddress)
            );
            
            // Get the expected output from first swap (input for second swap)
            const midTokenAmount = await this.raydiumSwap.getSwapQuote(
                startToken,
                midToken,
                inputAmount,
                new PublicKey(firstPair.poolAddress)
            );
            
            // Create second swap transaction
            const secondSwapTransaction = await this.raydiumSwap.createSwapTransaction(
                walletPubkey,
                midToken,
                endToken,
                midTokenAmount,
                1.0, // 1% slippage tolerance
                new PublicKey(secondPair.poolAddress)
            );
            
            // Combine instructions from both transactions
            const transaction = new Transaction();
            firstSwapTransaction.instructions.forEach(ix => transaction.add(ix));
            secondSwapTransaction.instructions.forEach(ix => transaction.add(ix));
            
            // Send and confirm transaction
            const { blockhash } = await this.connection.getLatestBlockhash();
            transaction.recentBlockhash = blockhash;
            transaction.feePayer = walletPubkey;
            
            // Sign the transaction
            transaction.sign(this.wallet);
            
            // Send the transaction
            const signature = await this.connection.sendRawTransaction(
                transaction.serialize()
            );
            
            // Wait for confirmation
            await this.connection.confirmTransaction(signature);
            
            console.log(`Arbitrage executed successfully: ${signature}`);
            return signature;
        } catch (error) {
            console.error(`Failed to execute arbitrage: ${error}`);
            throw new Error(`Failed to execute arbitrage: ${error}`);
        }
    }
    
    /**
     * Execute arbitrage using a flash loan
     */
    private async executeWithFlashLoan(opportunity: ArbitrageOpportunity): Promise<string> {
        const {
            path: { startToken, midToken, endToken, firstPair, secondPair },
            inputAmount,
            expectedOutputAmount
        } = opportunity;
        
        console.log(`Executing arbitrage with flash loan: ${inputAmount} ${startToken.symbol}`);
        
        try {
            const walletPubkey = this.wallet.publicKey;
            
            // Get the Solend reserve address for the token
            const reserveAddress = this.getReserveAddressForToken(startToken);
            if (!reserveAddress) {
                throw new Error(`No Solend reserve found for token: ${startToken.symbol}`);
            }
            
            // Check if flash loan is viable (fee not too high)
            const isViable = await this.solendClient.checkFlashLoanViability(
                inputAmount, 
                startToken.price || 1
            );
            
            if (!isViable) {
                throw new Error(`Flash loan not viable: fee too high for ${inputAmount} ${startToken.symbol}`);
            }
            
            // Create token accounts
            const tokenAccount = walletPubkey; // Simplified; would need to get or create ATA in real implementation
            
            // Create the flash loan transaction
            const flashLoanTransaction = await this.solendClient.executeFlashLoan(
                inputAmount,
                new PublicKey(startToken.address),
                new PublicKey(reserveAddress),
                tokenAccount,
                async () => {
                    // This function runs during the flash loan
                    // Create first swap instruction
                    const firstSwapIx = await this.raydiumSwap.createSwapInstruction(
                        walletPubkey,
                        startToken,
                        midToken,
                        inputAmount,
                        0, // Will calculate below
                        new PublicKey(firstPair.poolAddress)
                    );
                    
                    // Get the expected output from first swap (input for second swap)
                    const midTokenAmount = await this.raydiumSwap.getSwapQuote(
                        startToken,
                        midToken,
                        inputAmount,
                        new PublicKey(firstPair.poolAddress)
                    );
                    
                    // Create second swap instruction
                    const secondSwapIx = await this.raydiumSwap.createSwapInstruction(
                        walletPubkey,
                        midToken,
                        endToken,
                        midTokenAmount,
                        0, // Will calculate properly in full implementation
                        new PublicKey(secondPair.poolAddress)
                    );
                    
                    // Combine both swaps into a single instruction
                    const combinedIx = new TransactionInstruction({
                        keys: [...firstSwapIx.keys, ...secondSwapIx.keys],
                        programId: firstSwapIx.programId,
                        data: Buffer.concat([firstSwapIx.data, secondSwapIx.data])
                    });
                    
                    return combinedIx;
                }
            );
            
            // Send and confirm transaction
            const { blockhash } = await this.connection.getLatestBlockhash();
            flashLoanTransaction.recentBlockhash = blockhash;
            flashLoanTransaction.feePayer = walletPubkey;
            
            // Sign the transaction
            flashLoanTransaction.sign(this.wallet);
            
            // Send the transaction
            const signature = await this.connection.sendRawTransaction(
                flashLoanTransaction.serialize()
            );
            
            // Wait for confirmation
            await this.connection.confirmTransaction(signature);
            
            console.log(`Flash loan arbitrage executed successfully: ${signature}`);
            return signature;
        } catch (error) {
            console.error(`Failed to execute flash loan arbitrage: ${error}`);
            throw new Error(`Failed to execute flash loan arbitrage: ${error}`);
        }
    }
    
    /**
     * Check if wallet has enough balance or if a flash loan is needed
     */
    private async shouldUseFlashLoan(token: Token, amount: number): Promise<boolean> {
        try {
            // This is a simplified check that would need to be expanded
            // in a real implementation to actually check token account balances
            
            // For demo purposes, assume we need a flash loan for amounts over 100
            const useFlashLoan = amount > 100;
            
            console.log(`Should use flash loan for ${amount} ${token.symbol}? ${useFlashLoan}`);
            
            return useFlashLoan;
        } catch (error) {
            console.error(`Error checking if flash loan is needed: ${error}`);
            // Default to using flash loan if there's an error checking balance
            return true;
        }
    }
    
    /**
     * Get the Solend reserve address for a token
     */
    private getReserveAddressForToken(token: Token): string | null {
        const symbol = token.symbol.toUpperCase();
        
        if (SOLEND_RESERVES[symbol]) {
            return SOLEND_RESERVES[symbol];
        }
        
        console.warn(`No Solend reserve found for token: ${symbol}`);
        return null;
    }
}