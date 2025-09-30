import { Connection, PublicKey, Transaction, TransactionInstruction } from '@solana/web3.js';
import { 
    flashBorrowReserveLiquidityInstruction, 
    flashRepayReserveLiquidityInstruction,
    SOLEND_BETA_PROGRAM_ID
} from '@solendprotocol/solend-sdk';
import { BN } from 'bn.js';
import { SOLEND_RESERVES } from './constants';

export class SolendClient {
    constructor(private connection: Connection) {}

    async getFlashLoanFee(amount: number, isSOL: boolean = false): Promise<number> {
        // Solend charges 0.3% (30 basis points) for flash loans
        const feeRate = 0.003;
        const fee = amount * feeRate;
        
        // For SOL pairs, convert the fee to SOL terms
        if (isSOL) {
            console.log(`Flash loan fee calculation (in SOL): ${amount} × ${feeRate} = ${fee} SOL`);
        } else {
            console.log(`Flash loan fee calculation (in USDC/USDT): ${amount} × ${feeRate} = ${fee}`);
        }
        
        return fee;
    }
    
    async checkFlashLoanViability(amount: number, tokenSymbol: string = 'USDC'): Promise<boolean> {
        // Calculate the flash loan fee
        const isSOL = tokenSymbol === 'SOL';
        const fee = await this.getFlashLoanFee(amount, isSOL);
        
        // For SOL pairs, use SOL-specific thresholds
        const maxFee = isSOL ? 0.1 : 50; // 0.1 SOL or 50 USDC/USDT
        const isViable = fee <= maxFee;
        
        console.log(`Flash loan viability check for ${tokenSymbol}:`);
        console.log(`Amount=${amount}, Fee=${fee}, MaxFee=${maxFee} ${tokenSymbol}, Viable=${isViable}`);
        
        return isViable;
    }

    async executeFlashLoan(
        amount: number,
        tokenMint: PublicKey,
        reserveAccount: PublicKey,
        tokenAccount: PublicKey,
        onFlashLoan: () => Promise<TransactionInstruction>
    ): Promise<Transaction> {
        const liquidityAmount = new BN(amount);
        
        // Get reserve symbol for logging
        const reserveSymbol = Object.entries(SOLEND_RESERVES).find(
            ([_, address]) => address === reserveAccount.toString()
        )?.[0]?.split('_')[0] || 'Unknown';
        
        console.log(`Executing flash loan for ${amount} ${reserveSymbol}`);

        // Create flash loan begin instruction
        const flashLoanBeginIx = flashBorrowReserveLiquidityInstruction(
            liquidityAmount,
            reserveAccount, // sourceLiquidity
            tokenAccount,   // destinationLiquidity
            reserveAccount, // reserve
            new PublicKey(SOLEND_RESERVES.LENDING_MARKET), // lendingMarket
            SOLEND_BETA_PROGRAM_ID
        );

        // Get the instruction to execute during the flash loan
        const flashLoanActionIx = await onFlashLoan();

        // Create flash loan end instruction
        const flashLoanEndIx = flashRepayReserveLiquidityInstruction(
            liquidityAmount,
            0, // borrowInstructionIndex
            tokenAccount,   // sourceLiquidity
            reserveAccount, // destinationLiquidity
            reserveAccount, // reserveLiquidityFeeReceiver
            reserveAccount, // hostFeeReceiver
            reserveAccount, // reserve
            new PublicKey(SOLEND_RESERVES.LENDING_MARKET), // lendingMarket
            tokenAccount,   // userTransferAuthority
            SOLEND_BETA_PROGRAM_ID
        );

        // Combine all instructions into a single transaction
        const transaction = new Transaction();
        transaction.add(flashLoanBeginIx);
        transaction.add(flashLoanActionIx);
        transaction.add(flashLoanEndIx);

        return transaction;
    }
}