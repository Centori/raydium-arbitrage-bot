import * as fs from 'fs';
import * as path from 'path';

export interface LiquidityRecord {
    poolId: string;
    baseToken: string;
    quoteToken: string;
    timestamp: number;
    liquidity: number;
    liquidityRate: number;
    pattern: string;
    age: number;
}

export interface StorageOptions {
    dataDir: string;
    maxRecordsPerFile: number;
    autoFlush: boolean;
    flushInterval: number; // ms
}

export class LiquidityDataStore {
    private options: StorageOptions;
    private currentRecords: Map<string, LiquidityRecord[]> = new Map(); // poolId -> records
    private flushTimer: NodeJS.Timeout | null = null;

    constructor(options?: Partial<StorageOptions>) {
        // Default configuration
        this.options = {
            dataDir: path.join(process.cwd(), 'data', 'liquidity'),
            maxRecordsPerFile: 1000,
            autoFlush: true,
            flushInterval: 60000, // 1 minute
            ...options
        };
        
        // Ensure data directory exists
        if (!fs.existsSync(this.options.dataDir)) {
            fs.mkdirSync(this.options.dataDir, { recursive: true });
        }
        
        // Start auto flush timer if enabled
        if (this.options.autoFlush) {
            this.flushTimer = setInterval(() => {
                this.flush();
            }, this.options.flushInterval);
        }
    }
    
    public addRecord(record: LiquidityRecord): void {
        // Get or create pool records array
        if (!this.currentRecords.has(record.poolId)) {
            this.currentRecords.set(record.poolId, []);
        }
        
        const poolRecords = this.currentRecords.get(record.poolId)!;
        poolRecords.push(record);
        
        // Flush if max records exceeded
        if (poolRecords.length >= this.options.maxRecordsPerFile) {
            this.flushPool(record.poolId);
        }
    }
    
    public flush(): void {
        // Flush all pools
        for (const poolId of this.currentRecords.keys()) {
            this.flushPool(poolId);
        }
    }
    
    private flushPool(poolId: string): void {
        const records = this.currentRecords.get(poolId);
        if (!records || records.length === 0) return;
        
        try {
            // Create filename based on pool ID and date
            const now = new Date();
            const dateStr = now.toISOString().split('T')[0]; // YYYY-MM-DD
            const filename = `${poolId.slice(0, 8)}_${dateStr}.json`;
            const filePath = path.join(this.options.dataDir, filename);
            
            // Load existing data if file exists
            let existingData: LiquidityRecord[] = [];
            if (fs.existsSync(filePath)) {
                const fileContent = fs.readFileSync(filePath, 'utf8');
                existingData = JSON.parse(fileContent);
            }
            
            // Combine existing and new data
            const combinedData = [...existingData, ...records];
            
            // Write data to file
            fs.writeFileSync(filePath, JSON.stringify(combinedData, null, 2));
            
            // Clear records after successful write
            this.currentRecords.set(poolId, []);
        } catch (error) {
            console.error(`Failed to flush data for pool ${poolId}:`, error);
        }
    }
    
    public getRecordsForPool(poolId: string, startTime?: number, endTime?: number): LiquidityRecord[] {
        // Find files for this pool
        const files = fs.readdirSync(this.options.dataDir)
            .filter(filename => filename.startsWith(`${poolId.slice(0, 8)}_`));
        
        let allRecords: LiquidityRecord[] = [];
        
        // Load data from each file
        for (const file of files) {
            try {
                const filePath = path.join(this.options.dataDir, file);
                const fileContent = fs.readFileSync(filePath, 'utf8');
                const records: LiquidityRecord[] = JSON.parse(fileContent);
                
                // Filter by time range if specified
                const filtered = records.filter(record => {
                    if (startTime && record.timestamp < startTime) return false;
                    if (endTime && record.timestamp > endTime) return false;
                    return true;
                });
                
                allRecords = [...allRecords, ...filtered];
            } catch (error) {
                console.error(`Error reading data file ${file}:`, error);
            }
        }
        
        // Add any in-memory records
        const currentPoolRecords = this.currentRecords.get(poolId) || [];
        allRecords = [...allRecords, ...currentPoolRecords];
        
        // Sort by timestamp
        return allRecords.sort((a, b) => a.timestamp - b.timestamp);
    }
    
    public cleanup(): void {
        // Flush any pending data
        this.flush();
        
        // Clear flush timer if active
        if (this.flushTimer) {
            clearInterval(this.flushTimer);
            this.flushTimer = null;
        }
    }
}