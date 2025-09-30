import chalk from 'chalk';
import { PerformanceMetrics, MetricType } from './PerformanceMetrics';

/**
 * Dashboard configuration options
 */
export interface DashboardOptions {
  refreshIntervalMs: number;
  colorized: boolean;
  showAllMetrics: boolean;
}

/**
 * Console-based dashboard for displaying performance metrics
 */
export class MetricsDashboard {
  private metrics: PerformanceMetrics;
  private options: DashboardOptions;
  private refreshTimer: NodeJS.Timeout | null = null;
  
  constructor(metrics: PerformanceMetrics, options?: Partial<DashboardOptions>) {
    this.metrics = metrics;
    
    // Default options
    this.options = {
      refreshIntervalMs: 5000, // 5 seconds
      colorized: true,
      showAllMetrics: false,
      ...options
    };
  }
  
  /**
   * Start the dashboard with periodic updates
   */
  public start(): void {
    // Clear screen and render initial dashboard
    this.render();
    
    // Set up periodic refresh
    this.refreshTimer = setInterval(() => {
      this.render();
    }, this.options.refreshIntervalMs);
  }
  
  /**
   * Stop dashboard updates
   */
  public stop(): void {
    if (this.refreshTimer) {
      clearInterval(this.refreshTimer);
      this.refreshTimer = null;
    }
  }
  
  /**
   * Render the dashboard to console
   */
  public render(): void {
    console.clear();
    const summary = this.metrics.getSummary(300000); // Last 5 minutes
    const health = this.metrics.checkHealthStatus();
    
    // Format header
    console.log(this.formatHeader('LIQUIDITY MONITORING SYSTEM - PERFORMANCE DASHBOARD'));
    console.log(`Timestamp: ${new Date().toISOString()}`);
    console.log('');
    
    // System health overview
    this.renderHealthStatus(health);
    console.log('');
    
    // Key metrics summary
    console.log(this.formatHeader('KEY PERFORMANCE INDICATORS'));
    this.renderKeyMetrics(summary);
    console.log('');
    
    // Performance metrics
    console.log(this.formatHeader('PERFORMANCE METRICS'));
    this.renderPerformanceMetrics(summary);
    console.log('');
    
    // Operational statistics
    console.log(this.formatHeader('OPERATIONAL STATISTICS'));
    this.renderOperationalStats(summary);
    console.log('');
    
    // Signal quality metrics
    console.log(this.formatHeader('SIGNAL QUALITY METRICS'));
    this.renderSignalQualityMetrics(summary);
    
    // Show all metrics if enabled
    if (this.options.showAllMetrics) {
      console.log('');
      console.log(this.formatHeader('ALL METRICS'));
      this.renderAllMetrics(summary);
    }
  }
  
  /**
   * Format a header with consistent styling
   */
  private formatHeader(text: string): string {
    const padding = '='.repeat(10);
    const header = `${padding} ${text} ${padding}`;
    return this.options.colorized ? chalk.blue.bold(header) : header;
  }
  
  /**
   * Render overall system health status
   */
  private renderHealthStatus(health: Record<string, boolean | number>): void {
    const healthScore = health.overallHealth as number;
    
    let healthColor: any;
    let statusText: string;
    
    // Determine health status color and text
    if (healthScore >= 90) {
      healthColor = this.options.colorized ? chalk.green.bold : (s: string) => s;
      statusText = 'EXCELLENT';
    } else if (healthScore >= 75) {
      healthColor = this.options.colorized ? chalk.green : (s: string) => s;
      statusText = 'GOOD';
    } else if (healthScore >= 50) {
      healthColor = this.options.colorized ? chalk.yellow : (s: string) => s;
      statusText = 'FAIR';
    } else if (healthScore >= 25) {
      healthColor = this.options.colorized ? chalk.yellowBright : (s: string) => s;
      statusText = 'NEEDS ATTENTION';
    } else {
      healthColor = this.options.colorized ? chalk.red.bold : (s: string) => s;
      statusText = 'CRITICAL';
    }
    
    console.log(`System Health: ${healthColor(statusText)} (${healthScore.toFixed(2)}%)`);
    
    // System status components
    console.log('');
    console.log('Component Status:');
    console.log(`  API Latency: ${this.formatStatusIndicator(health.apiLatencyOk as boolean)}`);
    console.log(`  Analysis Performance: ${this.formatStatusIndicator(health.analysisPerformanceOk as boolean)}`);
    console.log(`  Opportunity Detection: ${this.formatStatusIndicator(health.opportunityDetectionOk as boolean)}`);
    console.log(`  Signal Quality: ${(health.signalQuality as number * 100).toFixed(1)}%`);
  }
  
  /**
   * Format a status indicator (✓/✗)
   */
  private formatStatusIndicator(status: boolean): string {
    if (this.options.colorized) {
      return status ? chalk.green('✓') : chalk.red('✗');
    } else {
      return status ? '✓' : '✗';
    }
  }
  
  /**
   * Render key metrics summary
   */
  private renderKeyMetrics(summary: Record<string, any>): void {
    // Extract key metrics
    const poolsAnalyzed = summary[MetricType.POOLS_ANALYZED]?.count || 0;
    const opportunities = summary[MetricType.OPPORTUNITIES_FOUND]?.count || 0;
    const analysisTime = summary[MetricType.ANALYSIS_TIME]?.avg || 0;
    const apiLatency = summary[MetricType.API_LATENCY]?.avg || 0;
    
    const signalEfficiency = summary.signalEfficiency || 0;
    const signalConversionRate = summary.signalConversionRate || 0;
    
    // Render
    console.log(`Pools Analyzed: ${poolsAnalyzed}`);
    console.log(`Opportunities Found: ${opportunities}`);
    console.log(`Signal Efficiency: ${(signalEfficiency * 100).toFixed(2)}%`);
    console.log(`Signal Conversion: ${(signalConversionRate * 100).toFixed(2)}%`);
  }
  
  /**
   * Render performance metrics
   */
  private renderPerformanceMetrics(summary: Record<string, any>): void {
    const analysisTime = summary[MetricType.ANALYSIS_TIME];
    const patternDetection = summary[MetricType.PATTERN_DETECTION];
    const dataProcessing = summary[MetricType.DATA_PROCESSING];
    
    if (analysisTime) {
      console.log(`Analysis Time: ${analysisTime.avg.toFixed(2)}ms (min: ${analysisTime.min.toFixed(2)}ms, max: ${analysisTime.max.toFixed(2)}ms)`);
    }
    
    if (patternDetection) {
      console.log(`Pattern Detection: ${patternDetection.avg.toFixed(2)}ms`);
    }
    
    if (dataProcessing) {
      console.log(`Data Processing: ${dataProcessing.avg.toFixed(2)}ms`);
    }
  }
  
  /**
   * Render operational statistics
   */
  private renderOperationalStats(summary: Record<string, any>): void {
    const apiLatency = summary[MetricType.API_LATENCY];
    const poolsAnalyzed = summary[MetricType.POOLS_ANALYZED];
    const opportunitiesFound = summary[MetricType.OPPORTUNITIES_FOUND];
    
    if (apiLatency) {
      console.log(`API Latency: ${apiLatency.avg.toFixed(2)}ms`);
    }
    
    if (poolsAnalyzed) {
      console.log(`Pools Analyzed: ${poolsAnalyzed.count}`);
    }
    
    if (opportunitiesFound) {
      console.log(`Opportunities Found: ${opportunitiesFound.count}`);
    }
  }
  
  /**
   * Render signal quality metrics
   */
  private renderSignalQualityMetrics(summary: Record<string, any>): void {
    const accumulation = summary[MetricType.ACCUMULATION_DETECTED];
    const strongSignals = summary[MetricType.STRONG_SIGNALS];
    const alertCount = summary[MetricType.ALERT_COUNT];
    const signalAccuracy = summary[MetricType.SIGNAL_ACCURACY];
    
    if (accumulation) {
      console.log(`Accumulation Patterns: ${accumulation.count}`);
    }
    
    if (strongSignals) {
      console.log(`Strong Signals: ${strongSignals.count}`);
    }
    
    if (alertCount) {
      console.log(`Alerts Triggered: ${alertCount.count}`);
    }
    
    if (signalAccuracy) {
      console.log(`Signal Accuracy: ${signalAccuracy.avg.toFixed(2)}%`);
    }
    
    // Derived metrics
    console.log(`Signal Efficiency: ${(summary.signalEfficiency * 100).toFixed(2)}%`);
    console.log(`Signal Conversion Rate: ${(summary.signalConversionRate * 100).toFixed(2)}%`);
  }
  
  /**
   * Render all available metrics (for debugging)
   */
  private renderAllMetrics(summary: Record<string, any>): void {
    for (const [key, value] of Object.entries(summary)) {
      console.log(`${key}:`);
      
      if (typeof value === 'object') {
        for (const [subKey, subValue] of Object.entries(value)) {
          console.log(`  ${subKey}: ${JSON.stringify(subValue)}`);
        }
      } else {
        console.log(`  ${value}`);
      }
    }
  }
}