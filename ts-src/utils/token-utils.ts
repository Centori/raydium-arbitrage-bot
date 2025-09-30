import { Connection, PublicKey, Transaction, TransactionInstruction } from '@solana/web3.js';
import { 
    getAssociatedTokenAddress, 
    createAssociatedTokenAccountInstruction, 
    getAccount, 
    TokenAccountNotFoundError 
} from '@solana/spl-token';

/**
 * Find the associated token address for a wallet and token
 * @param walletAddress Wallet public key
 * @param tokenMint Token mint public key
 * @returns Associated token account public key
 */
export async function findAssociatedTokenAddress(
    walletAddress: PublicKey,
    tokenMint: PublicKey
): Promise<PublicKey> {
    return await getAssociatedTokenAddress(
        tokenMint,
        walletAddress,
        false // allowOwnerOffCurve
    );
}

/**
 * Create instructions to create associated token accounts if they don't exist
 * @param connection Solana connection
 * @param payer Payer public key
 * @param tokenMints Array of token mint public keys
 * @returns Array of instructions to create token accounts if needed
 */
export async function createATAInstructionsIfNeeded(
    connection: Connection,
    payer: PublicKey,
    tokenMints: PublicKey[]
): Promise<TransactionInstruction[]> {
    const instructions: TransactionInstruction[] = [];
    
    for (const mint of tokenMints) {
        const associatedTokenAddress = await findAssociatedTokenAddress(payer, mint);
        
        try {
            // Check if the token account already exists
            await getAccount(connection, associatedTokenAddress);
            console.log(`Token account for mint ${mint.toString()} already exists`);
        } catch (error) {
            if (error instanceof TokenAccountNotFoundError) {
                // Create the token account if it doesn't exist
                console.log(`Creating token account for mint ${mint.toString()}`);
                const createInstruction = createAssociatedTokenAccountInstruction(
                    payer,
                    associatedTokenAddress,
                    payer,
                    mint
                );
                instructions.push(createInstruction);
            } else {
                throw error;
            }
        }
    }
    
    return instructions;
}

/**
 * Get the token balance for a token account
 * @param connection Solana connection
 * @param tokenAccount Token account public key
 * @returns Token balance as a number
 */
export async function getTokenBalance(
    connection: Connection,
    tokenAccount: PublicKey
): Promise<number> {
    try {
        const account = await getAccount(connection, tokenAccount);
        return Number(account.amount);
    } catch (error) {
        if (error instanceof TokenAccountNotFoundError) {
            return 0;
        }
        throw error;
    }
}

/**
 * Convert an amount to a decimal value based on token decimals
 * @param amount Raw token amount (as a BN or number)
 * @param decimals Number of token decimals
 * @returns Decimal value
 */
export function toDecimal(amount: any, decimals: number): number {
    return Number(amount) / Math.pow(10, decimals);
}

/**
 * Convert a decimal value to a raw token amount based on token decimals
 * @param decimal Decimal value
 * @param decimals Number of token decimals
 * @returns Raw token amount as a number
 */
export function fromDecimal(decimal: number, decimals: number): number {
    return Math.floor(decimal * Math.pow(10, decimals));
}