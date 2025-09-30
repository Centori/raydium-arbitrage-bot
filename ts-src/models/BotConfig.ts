export interface BotConfig {
    enableNotifications: boolean;
    notificationLevel: 'all' | 'important' | 'minimal';
}

export interface TradeRecommendation {
    recommendation: 'BUY' | 'SELL' | 'HOLD';
    tokenSymbol: string;
    tokenName?: string;
    decision: 'YES' | 'NO';
    confidence: number;
    tradingAmount: number;
    expectedReturn: number;
    riskLevel: 'LOW' | 'MEDIUM' | 'HIGH';
    reasoning: string[];
}