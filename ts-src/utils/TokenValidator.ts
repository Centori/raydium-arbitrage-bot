import { Connection, PublicKey } from '@solana/web3.js';
import axios from 'axios';

export interface TokenRiskProfile {
    address: string;
    symbol: string;
    isVerified: boolean;
    riskScore: number;       // 0-100, higher is riskier
    rugPullRisk: number;     // 0-100, higher is riskier
    warnings: string[];
    verificationSource?: string;
}

export interface TokenValidationOptions {
    rugPullDetection: boolean;
    tokenVerification: boolean;
    rpcEndpoint: string;
}

export class TokenValidator {
    private connection: Connection;
    private options: TokenValidationOptions;
    private verifiedTokenCache: Map<string, boolean> = new Map();
    private riskScoreCache: Map<string, TokenRiskProfile> = new Map();
    private tokenListUrl = 'https://cdn.jsdelivr.net/gh/solana-labs/token-list@main/src/tokens/solana.tokenlist.json';
    
    constructor(options?: Partial<TokenValidationOptions>) {
        this.options = {
            rugPullDetection: true,
            tokenVerification: true,
            rpcEndpoint: 'https://api.mainnet-beta.solana.com',
            ...options
        };
        
        this.connection = new Connection(this.options.rpcEndpoint, 'confirmed');
    }
    
    public async loadVerifiedTokens(): Promise<void> {
        try {
            // Fetch from Solana token list
            const response = await axios.get(this.tokenListUrl);
            const tokens = response.data.tokens;
            
            tokens.forEach((token: any) => {
                this.verifiedTokenCache.set(token.address, true);
            });
            
            console.log(`Loaded ${this.verifiedTokenCache.size} verified tokens`);
        } catch (error) {
            console.error('Failed to load verified tokens:', error);
        }
    }
    
    public async validateToken(tokenAddress: string, poolId: string, liquidityUSD: number): Promise<TokenRiskProfile> {
        // Return cached result if available
        if (this.riskScoreCache.has(tokenAddress)) {
            return this.riskScoreCache.get(tokenAddress)!;
        }
        
        // Start with basic profile
        const profile: TokenRiskProfile = {
            address: tokenAddress,
            symbol: 'UNKNOWN',
            isVerified: false,
            riskScore: 50, // Default medium risk
            rugPullRisk: 50,
            warnings: []
        };
        
        try {
            // Check if this is a verified token
            if (this.options.tokenVerification) {
                profile.isVerified = this.verifiedTokenCache.has(tokenAddress);
                if (profile.isVerified) {
                    profile.verificationSource = 'Solana Token List';
                    profile.riskScore -= 30; // Lower risk for verified tokens
                } else {
                    profile.warnings.push('Token not found in verified token list');
                    profile.riskScore += 20;
                }
            }
            
            // Check for rug pull risk indicators
            if (this.options.rugPullDetection) {
                // Assess liquidity - very low liquidity is suspicious for new tokens
                if (liquidityUSD < 5000) {
                    profile.warnings.push('Very low initial liquidity');
                    profile.rugPullRisk += 25;
                }
                
                // More sophisticated checks can be added here:
                // - Check token program for suspicious code
                // - Check if the token has locked liquidity
                // - Check ownership concentration
            }
            
            // Calculate final risk scores
            profile.riskScore = Math.min(100, Math.max(0, profile.riskScore));
            profile.rugPullRisk = Math.min(100, Math.max(0, profile.rugPullRisk));
            
            // Cache the result
            this.riskScoreCache.set(tokenAddress, profile);
            return profile;
            
        } catch (error) {
            console.error(`Error validating token ${tokenAddress}:`, error);
            profile.warnings.push('Error during validation');
            profile.riskScore = 75; // Higher risk due to validation failure
            return profile;
        }
    }
    
    public async detectRugPullPattern(
        poolId: string, 
        previousLiquidity: number, 
        currentLiquidity: number,
        timeframeSec: number
    ): Promise<{isRugPull: boolean, confidence: number, reason: string}> {
        // Calculate liquidity change rate
        const liquidityChange = currentLiquidity - previousLiquidity;
        const changePercent = (liquidityChange / previousLiquidity) * 100;
        const changeRate = changePercent / timeframeSec;
        
        // Detect sudden liquidity drain
        if (changeRate < -5 && changePercent < -50) {
            // Massive liquidity removal detected
            return {
                isRugPull: true,
                confidence: 90,
                reason: `Detected ${Math.abs(changePercent).toFixed(2)}% liquidity decrease in ${timeframeSec}s`
            };
        }
        
        // No rug pull pattern detected
        return {
            isRugPull: false,
            confidence: 0,
            reason: 'No suspicious activity detected'
        };
    }
}