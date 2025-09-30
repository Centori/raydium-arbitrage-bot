/**
 * Simple logger utility for consistent log output
 */
export class Logger {
    private moduleName: string;
    
    constructor(moduleName: string) {
        this.moduleName = moduleName;
    }
    
    /**
     * Log informational message
     */
    info(message: string): void {
        console.log(`[INFO][${this.moduleName}] ${message}`);
    }
    
    /**
     * Log warning message
     */
    warn(message: string): void {
        console.warn(`[WARN][${this.moduleName}] ${message}`);
    }
    
    /**
     * Log error message
     */
    error(message: string, error?: any): void {
        console.error(`[ERROR][${this.moduleName}] ${message}`);
        if (error) {
            console.error(error);
        }
    }
    
    /**
     * Log debug message (only in development)
     */
    debug(message: string): void {
        if (process.env.NODE_ENV === 'development') {
            console.debug(`[DEBUG][${this.moduleName}] ${message}`);
        }
    }
}