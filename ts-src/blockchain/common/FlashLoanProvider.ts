import { Connection, PublicKey, Transaction, TransactionInstruction } from '@solana/web3.js';
import { SolendClient } from '../solend/SolendClient';
import { PortFinanceClient } from '../port/PortFinanceClient';
import { SOLEND_RESERVES } from '../solend/constants';
import { PORT_RESERVES } from '../port/constants';

// Type for flash loan provider comparison result
interface FlashLoanComparison {
    provider: 'solend' | 'port';
    fee: number;
    transaction: Transaction;
}

export class FlashLoanProvider {
    private solendClient: SolendClient;
    private portClient: PortFinanceClient;
    
    constructor(private connection: Connection) {
        this.solendClient = new SolendClient(connection);
        this.portClient = new PortFinanceClient(connection);
    }
    
    /**
     * Compares flash loan fees between Solend and Port Finance
     * and returns the more cost-effective option
     */
    async compareFlashLoanProviders(
        amount: number,
        tokenSymbol: string,
        tokenMint: PublicKey,
        tokenAccount: PublicKey,
        solPrice: number = 1,
        onFlashLoan: () => Promise<TransactionInstruction>
    ): Promise<FlashLoanComparison | null> {
        try {
            // Check if both lending protocols support this token
            const solendReserve = this.getSolendReserve(tokenSymbol);
            const portReserve = this.getPortReserve(tokenSymbol);
            
            // Track which providers are viable options
            const viableProviders: Array<{
                name: 'solend' | 'port',
                fee: number,
                transaction: Transaction
            }> = [];
            
            // Check Solend if reserve exists
            if (solendReserve) {
                const solendFee = await this.solendClient.getFlashLoanFee(amount);
                const isViable = await this.solendClient.checkFlashLoanViability(amount, solPrice);
                
                if (isViable) {
                    const transaction = await this.solendClient.executeFlashLoan(
                        amount,
                        tokenMint,
                        solendReserve,
                        tokenAccount,
                        onFlashLoan
                    );
                    
                    viableProviders.push({
                        name: 'solend',
                        fee: solendFee,
                        transaction
                    });
                }
            }
            
            // Check Port Finance if reserve exists
            if (portReserve) {
                const portFee = await this.portClient.getFlashLoanFee(amount);
                const isViable = await this.portClient.checkFlashLoanViability(amount, solPrice);
                
                if (isViable) {
                    const transaction = await this.portClient.executeFlashLoan(
                        amount,
                        tokenMint,
                        portReserve,
                        tokenAccount,
                        onFlashLoan
                    );
                    
                    viableProviders.push({
                        name: 'port',
                        fee: portFee,
                        transaction
                    });
                }
            }
            
            // If no viable providers, return null
            if (viableProviders.length === 0) {
                console.log(`No viable flash loan providers found for ${amount} ${tokenSymbol}`);
                return null;
            }
            
            // Sort by lowest fee
            viableProviders.sort((a, b) => a.fee - b.fee);
            
            // Return the provider with the lowest fee
            const bestProvider = viableProviders[0];
            console.log(`Selected flash loan provider: ${bestProvider.name} with fee ${bestProvider.fee}`);
            
            return {
                provider: bestProvider.name,
                fee: bestProvider.fee,
                transaction: bestProvider.transaction
            };
            
        } catch (error) {
            console.error(`Error comparing flash loan providers: ${error}`);
            return null;
        }
    }
    
    /**
     * Get Solend reserve address for a token if it exists
     */
    private getSolendReserve(tokenSymbol: string): PublicKey | null {
        const reserveAddress = SOLEND_RESERVES[tokenSymbol];
        if (!reserveAddress) {
            console.log(`No Solend reserve found for token ${tokenSymbol}`);
            return null;
        }
        
        return new PublicKey(reserveAddress);
    }
    
    /**
     * Get Port Finance reserve address for a token if it exists
     */
    private getPortReserve(tokenSymbol: string): PublicKey | null {
        const reserveAddress = PORT_RESERVES[tokenSymbol];
        if (!reserveAddress) {
            console.log(`No Port Finance reserve found for token ${tokenSymbol}`);
            return null;
        }
        
        return new PublicKey(reserveAddress);
    }
}