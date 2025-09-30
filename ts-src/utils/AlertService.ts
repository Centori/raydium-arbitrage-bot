import chalk from 'chalk';
import * as fs from 'fs';
import * as path from 'path';

export interface AlertConfig {
    // Alert thresholds
    minLiquidityRate: number;        // Minimum liquidity rate for notification (units/sec)
    maxPoolAge: number;              // Maximum age in seconds (45 min = 2700s)
    minTotalLiquidity: number;       // Minimum total liquidity to trigger alert
    
    // Alert destinations
    enableConsoleAlerts: boolean;    // Print to console
    enableFileLogging: boolean;      // Log to file
    logFilePath: string;             // Path to log file
    enableTelegramAlerts?: boolean;  // Enable Telegram notifications
}

export interface AlertData {
    poolId: string;
    baseToken: string;
    quoteToken: string;
    pattern: string;
    rate: number;
    age: number;
    timestamp: number;
    totalLiquidity?: number;
}

export class AlertService {
    private config: AlertConfig;
    private alertHistory: Map<string, number> = new Map(); // poolId -> last alert timestamp

    constructor(config?: Partial<AlertConfig>) {
        // Default configuration
        this.config = {
            minLiquidityRate: 100,       // Units/second
            maxPoolAge: 2700,            // 45 minutes
            minTotalLiquidity: 1000,     // Minimum liquidity value
            enableConsoleAlerts: true,
            enableFileLogging: true,
            logFilePath: path.join(process.cwd(), 'liquidity-alerts.log'),
            ...config
        };
        
        // Ensure log directory exists
        if (this.config.enableFileLogging) {
            const logDir = path.dirname(this.config.logFilePath);
            if (!fs.existsSync(logDir)) {
                fs.mkdirSync(logDir, { recursive: true });
            }
        }
    }
    
    public shouldAlert(data: AlertData): boolean {
        // Check if this pool meets alert criteria
        if (data.age > this.config.maxPoolAge) return false;
        if (data.rate < this.config.minLiquidityRate) return false;
        if (data.totalLiquidity && data.totalLiquidity < this.config.minTotalLiquidity) return false;
        
        // Don't alert too frequently for the same pool
        const lastAlertTime = this.alertHistory.get(data.poolId) || 0;
        const now = Date.now();
        if (now - lastAlertTime < 60000) return false; // Once per minute max
        
        return true;
    }
    
    public alert(data: AlertData): void {
        if (!this.shouldAlert(data)) return;
        
        // Update alert history
        this.alertHistory.set(data.poolId, Date.now());
        
        // Format the alert message
        const message = this.formatAlertMessage(data);
        
        // Send to enabled destinations
        if (this.config.enableConsoleAlerts) {
            this.alertToConsole(message, data);
        }
        
        if (this.config.enableFileLogging) {
            this.alertToFile(message, data);
        }
    }
    
    private formatAlertMessage(data: AlertData): string {
        const ageMinutes = Math.floor(data.age / 60);
        const ageSeconds = Math.floor(data.age % 60);
        
        return `
[${new Date(data.timestamp).toISOString()}] ${data.pattern} DETECTED
Pool: ${data.baseToken}/${data.quoteToken}
ID: ${data.poolId}
Age: ${ageMinutes}m ${ageSeconds}s
Rate: ${data.rate.toFixed(2)} units/sec
${'-'.repeat(50)}`;
    }
    
    private alertToConsole(message: string, data: AlertData): void {
        const patternColor = 
            data.pattern === 'STRONG_ACCUMULATION' ? chalk.green.bold :
            data.pattern === 'ACCELERATING' ? chalk.yellow.bold :
            data.pattern === 'STEADY' ? chalk.blue.bold :
            chalk.gray.bold;
            
        console.log(message.replace(data.pattern, patternColor(data.pattern)));
    }
    
    private alertToFile(message: string, data: AlertData): void {
        try {
            fs.appendFileSync(this.config.logFilePath, message + '\n');
        } catch (error) {
            console.error('Failed to write to alert log:', error);
        }
    }
}