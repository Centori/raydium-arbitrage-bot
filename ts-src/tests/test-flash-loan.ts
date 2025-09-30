import { expect } from 'chai';
import { Connection, Keypair, PublicKey } from '@solana/web3.js';
import { FlashLoanExecutor } from '../blockchain/solend/FlashLoanExecutor';
import { ArbitrageOpportunity } from '../models/ArbitrageModels';

describe('FlashLoanExecutor', () => {
    let connection: Connection;
    let walletKeypair: Keypair;
    let flashLoanExecutor: FlashLoanExecutor;

    beforeEach(() => {
        connection = new Connection('https://api.mainnet-beta.solana.com');
        walletKeypair = Keypair.generate();
        flashLoanExecutor = new FlashLoanExecutor(connection, walletKeypair);
    });

    describe('executeArbitrageWithFlashLoan', () => {
        it('should execute a profitable flash loan arbitrage', async () => {
            // Mock profitable opportunity
            const mockOpportunity: ArbitrageOpportunity = {
                token: {
                    symbol: 'USDC',
                    address: new PublicKey('EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v'),
                    decimals: 6
                },
                route: {
                    entryPool: new PublicKey('58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2'),
                    exitPool: new PublicKey('7quYw4Yo45Ksvhy8perfPoVx3eiLKgHeBKqnk5RhVHtF'),
                    walletTokenAccount: new PublicKey('3uetDDizgTtadDHZzyy9BqxrjQcozMEkxdHPn8T6Jt5P')
                },
                initialAmount: 1000000, // 1 USDC
                finalAmount: 1010000,   // 1.01 USDC
                expectedProfit: 10000,  // 0.01 USDC
                profitPercentage: 0.01  // 1%
            };

            const bundleId = await flashLoanExecutor.executeArbitrageWithFlashLoan(mockOpportunity);
            expect(bundleId).to.be.a('string');
            expect(bundleId).to.include('bundle_');
        });

        it('should reject unprofitable opportunities', async () => {
            // Mock unprofitable opportunity
            const mockOpportunity: ArbitrageOpportunity = {
                token: {
                    symbol: 'USDC',
                    address: new PublicKey('EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v'),
                    decimals: 6
                },
                route: {
                    entryPool: new PublicKey('58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2'),
                    exitPool: new PublicKey('7quYw4Yo45Ksvhy8perfPoVx3eiLKgHeBKqnk5RhVHtF'),
                    walletTokenAccount: new PublicKey('3uetDDizgTtadDHZzyy9BqxrjQcozMEkxdHPn8T6Jt5P')
                },
                initialAmount: 1000000, // 1 USDC
                finalAmount: 1001000,   // 1.001 USDC (less than flash loan fee)
                expectedProfit: 1000,   // 0.001 USDC
                profitPercentage: 0.001 // 0.1%
            };

            try {
                await flashLoanExecutor.executeArbitrageWithFlashLoan(mockOpportunity);
                expect.fail('Should have thrown an error');
            } catch (error) {
                expect(error).to.be.instanceOf(Error);
                expect((error as Error).message).to.include('not profitable');
            }
        });
    });
});