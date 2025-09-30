import { Connection, Keypair, LAMPORTS_PER_SOL, PublicKey } from '@solana/web3.js';
import { EventEmitter } from 'events';
import * as fs from 'fs';

interface WalletBalanceSnapshot {
    timestamp: number;
    balance: number;
}

export interface WalletConfig {
    keyPath: string;          // Path to wallet keypair file
    rpcEndpoint: string;      // Solana RPC endpoint
    autoTrackBalance: boolean; // Whether to automatically track balance changes
    trackingInterval: number; // Interval for balance tracking in ms
}

export interface WalletState {
    publicKey: string;
    currentBalance: number;
    startingBalance: number;
    closingBalance?: number;
    lastUpdate: number;
    balanceHistory: WalletBalanceSnapshot[];
}

export class WalletManager extends EventEmitter {
    private connection: Connection;
    private keypair: Keypair | null = null;
    private config: WalletConfig;
    private state: WalletState;
    private trackingInterval: NodeJS.Timeout | null = null;

    constructor(config: Partial<WalletConfig> = {}) {
        super();
        
        // Default configuration
        this.config = {
            keyPath: './keys/wallet-keypair.json',
            rpcEndpoint: 'https://api.mainnet-beta.solana.com',
            autoTrackBalance: true,
            trackingInterval: 60000, // 1 minute
            ...config
        };

        this.connection = new Connection(this.config.rpcEndpoint, 'confirmed');
        this.state = {
            publicKey: '',
            currentBalance: 0,
            startingBalance: 0,
            lastUpdate: 0,
            balanceHistory: []
        };
    }

    /**
     * Initialize wallet from keypair file
     */
    public async initialize(): Promise<boolean> {
        try {
            // Load keypair
            const keypairData = JSON.parse(fs.readFileSync(this.config.keyPath, 'utf-8'));
            this.keypair = Keypair.fromSecretKey(Uint8Array.from(keypairData));
            
            // Set public key in state
            this.state.publicKey = this.keypair.publicKey.toString();
            
            // Get initial balance
            const balance = await this.fetchBalance();
            this.state.startingBalance = balance;
            this.state.currentBalance = balance;
            this.state.lastUpdate = Date.now();
            
            // Start balance tracking if enabled
            if (this.config.autoTrackBalance) {
                this.startBalanceTracking();
            }

            this.emit('initialized', {
                publicKey: this.state.publicKey,
                balance: this.state.currentBalance
            });

            return true;
        } catch (error) {
            console.error('Failed to initialize wallet:', error);
            return false;
        }
    }

    /**
     * Get current wallet state
     */
    public getState(): WalletState {
        return { ...this.state };
    }

    /**
     * Get wallet public key
     */
    public getPublicKey(): PublicKey | null {
        return this.keypair?.publicKey || null;
    }

    /**
     * Get current balance in SOL
     */
    public getCurrentBalance(): number {
        return this.state.currentBalance;
    }

    /**
     * Get profit/loss since start
     */
    public getProfitLoss(): number {
        return this.state.currentBalance - this.state.startingBalance;
    }

    /**
     * Get balance history
     */
    public getBalanceHistory(): WalletBalanceSnapshot[] {
        return [...this.state.balanceHistory];
    }

    /**
     * Manually update balance
     */
    public async updateBalance(): Promise<number> {
        const balance = await this.fetchBalance();
        this.updateState(balance);
        return balance;
    }

    /**
     * Set closing balance and stop tracking
     */
    public async close(): Promise<void> {
        const finalBalance = await this.fetchBalance();
        this.state.closingBalance = finalBalance;
        this.stopBalanceTracking();
        
        // Calculate final stats
        const stats = {
            startingBalance: this.state.startingBalance,
            closingBalance: finalBalance,
            profitLoss: finalBalance - this.state.startingBalance,
            profitLossPercent: ((finalBalance - this.state.startingBalance) / this.state.startingBalance) * 100
        };

        this.emit('closed', stats);
    }

    private async fetchBalance(): Promise<number> {
        if (!this.keypair) {
            throw new Error('Wallet not initialized');
        }
        const balance = await this.connection.getBalance(this.keypair.publicKey);
        return balance / LAMPORTS_PER_SOL;
    }

    private updateState(balance: number): void {
        this.state.currentBalance = balance;
        this.state.lastUpdate = Date.now();
        
        // Add to history
        this.state.balanceHistory.push({
            timestamp: this.state.lastUpdate,
            balance
        });

        // Emit update event
        this.emit('balance_update', {
            balance,
            timestamp: this.state.lastUpdate,
            profitLoss: this.getProfitLoss()
        });
    }

    private startBalanceTracking(): void {
        if (this.trackingInterval) return;

        this.trackingInterval = setInterval(async () => {
            try {
                await this.updateBalance();
            } catch (error) {
                console.error('Error updating balance:', error);
            }
        }, this.config.trackingInterval);
    }

    private stopBalanceTracking(): void {
        if (this.trackingInterval) {
            clearInterval(this.trackingInterval);
            this.trackingInterval = null;
        }
    }
}