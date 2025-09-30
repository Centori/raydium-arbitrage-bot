import * as fs from 'fs';
import * as path from 'path';

/**
 * Types of metrics tracked by the performance monitoring system
 */
export enum MetricType {
  // Analysis performance metrics
  ANALYSIS_TIME = 'analysis_time',          // Time to analyze a single pool (ms)
  PATTERN_DETECTION = 'pattern_detection',  // Time to detect patterns across pools (ms)
  DATA_PROCESSING = 'data_processing',      // Time to process incoming data (ms)
  
  // Operational metrics
  API_LATENCY = 'api_latency',              // Raydium API call latency (ms)
  POOLS_ANALYZED = 'pools_analyzed',        // Number of pools analyzed
  OPPORTUNITIES_FOUND = 'opportunities_found', // Number of high-quality opportunities found
  
  // Results metrics
  ACCUMULATION_DETECTED = 'accumulation_detected', // Count of accumulation patterns detected
  STRONG_SIGNALS = 'strong_signals',        // Count of STRONG_ACCUMULATION signals
  ALERT_COUNT = 'alert_count',              // Number of alerts triggered
  SIGNAL_ACCURACY = 'signal_accuracy',      // Accuracy score of signals (0-100%)
}

/**
 * Data point for a performance metric
 */
export interface MetricDataPoint {
  timestamp: number;
  value: number;
  metadata?: Record<string, any>;
}

/**
 * Options for the metrics collection
 */
export interface MetricsOptions {
  enableFileLogging: boolean;
  logDirectory: string;
  flushIntervalMs: number;
  retentionPeriodDays: number;
}

/**
 * Performance metrics collector and analyzer for liquidity monitoring
 */
export class PerformanceMetrics {
  private metrics: Map<MetricType, MetricDataPoint[]> = new Map();
  private options: MetricsOptions;
  private flushTimer: NodeJS.Timeout | null = null;
  
  constructor(options?: Partial<MetricsOptions>) {
    // Default configuration
    this.options = {
      enableFileLogging: true,
      logDirectory: path.join(process.cwd(), 'data', 'metrics'),
      flushIntervalMs: 60000, // 1 minute
      retentionPeriodDays: 7,
      ...options
    };
    
    // Initialize metrics storage
    Object.values(MetricType).forEach(type => {
      this.metrics.set(type as MetricType, []);
    });
    
    // Create log directory if it doesn't exist
    if (this.options.enableFileLogging) {
      if (!fs.existsSync(this.options.logDirectory)) {
        fs.mkdirSync(this.options.logDirectory, { recursive: true });
      }
    }
    
    // Start periodic flushing if enabled
    if (this.options.enableFileLogging && this.options.flushIntervalMs > 0) {
      this.flushTimer = setInterval(() => this.flushMetrics(), this.options.flushIntervalMs);
    }
  }
  
  /**
   * Record a metric data point
   */
  public recordMetric(type: MetricType, value: number, metadata?: Record<string, any>): void {
    const dataPoint: MetricDataPoint = {
      timestamp: Date.now(),
      value,
      metadata
    };
    
    const metricArr = this.metrics.get(type) || [];
    metricArr.push(dataPoint);
    this.metrics.set(type, metricArr);
  }
  
  /**
   * Start timing a specific operation
   * @returns A function that stops timing and records the metric
   */
  public startTimer(type: MetricType, metadata?: Record<string, any>): () => number {
    const startTime = performance.now();
    
    return () => {
      const endTime = performance.now();
      const duration = endTime - startTime;
      this.recordMetric(type, duration, metadata);
      return duration;
    };
  }
  
  /**
   * Get average value for a metric over a time period
   */
  public getAverage(type: MetricType, timeWindowMs?: number): number {
    const metricArr = this.metrics.get(type) || [];
    if (metricArr.length === 0) return 0;
    
    let filteredMetrics = metricArr;
    
    // Filter by time window if specified
    if (timeWindowMs) {
      const cutoffTime = Date.now() - timeWindowMs;
      filteredMetrics = metricArr.filter(dp => dp.timestamp >= cutoffTime);
    }
    
    if (filteredMetrics.length === 0) return 0;
    
    // Calculate average
    const sum = filteredMetrics.reduce((acc, dp) => acc + dp.value, 0);
    return sum / filteredMetrics.length;
  }
  
  /**
   * Get performance summary for all metrics
   */
  public getSummary(timeWindowMs?: number): Record<string, any> {
    const summary: Record<string, any> = {};
    
    for (const type of Object.values(MetricType)) {
      const metricType = type as MetricType;
      const metricArr = this.metrics.get(metricType) || [];
      
      // Skip metrics with no data
      if (metricArr.length === 0) {
        summary[metricType] = { count: 0, avg: 0, min: 0, max: 0 };
        continue;
      }
      
      let filteredMetrics = metricArr;
      
      // Filter by time window if specified
      if (timeWindowMs) {
        const cutoffTime = Date.now() - timeWindowMs;
        filteredMetrics = metricArr.filter(dp => dp.timestamp >= cutoffTime);
      }
      
      if (filteredMetrics.length === 0) {
        summary[metricType] = { count: 0, avg: 0, min: 0, max: 0 };
        continue;
      }
      
      // Calculate stats
      const sum = filteredMetrics.reduce((acc, dp) => acc + dp.value, 0);
      const avg = sum / filteredMetrics.length;
      const min = Math.min(...filteredMetrics.map(dp => dp.value));
      const max = Math.max(...filteredMetrics.map(dp => dp.value));
      
      summary[metricType] = {
        count: filteredMetrics.length,
        avg,
        min,
        max,
        latest: filteredMetrics[filteredMetrics.length - 1].value
      };
    }
    
    // Add derived metrics
    
    // Signal Efficiency (opportunities per pool analyzed)
    const poolsAnalyzed = summary[MetricType.POOLS_ANALYZED]?.count || 0;
    const opportunitiesFound = summary[MetricType.OPPORTUNITIES_FOUND]?.count || 0;
    summary.signalEfficiency = poolsAnalyzed > 0 ? opportunitiesFound / poolsAnalyzed : 0;
    
    // Signal conversion rate (% of strong signals from all accumulation patterns)
    const accumPatterns = summary[MetricType.ACCUMULATION_DETECTED]?.count || 0;
    const strongSignals = summary[MetricType.STRONG_SIGNALS]?.count || 0;
    summary.signalConversionRate = accumPatterns > 0 ? strongSignals / accumPatterns : 0;
    
    return summary;
  }
  
  /**
   * Check if KPIs are within acceptable thresholds
   */
  public checkHealthStatus(): Record<string, boolean | number> {
    const summary = this.getSummary(300000); // Last 5 minutes
    
    return {
      apiLatencyOk: (summary[MetricType.API_LATENCY]?.avg || 0) < 1000, // API calls under 1s
      analysisPerformanceOk: (summary[MetricType.ANALYSIS_TIME]?.avg || 0) < 100, // Analysis under 100ms
      opportunityDetectionOk: (summary[MetricType.OPPORTUNITIES_FOUND]?.count || 0) > 0,
      signalQuality: summary.signalConversionRate || 0,
      overallHealth: this.calculateOverallHealth(summary)
    };
  }
  
  /**
   * Calculate overall system health (0-100%)
   */
  private calculateOverallHealth(summary: Record<string, any>): number {
    // Check key metrics with weights
    const metrics: Array<{metric: any, weight: number, threshold: number, isHigherBetter: boolean}> = [
      { 
        metric: summary[MetricType.API_LATENCY]?.avg || 1000,
        weight: 0.2,
        threshold: 1000, // 1000ms
        isHigherBetter: false
      },
      { 
        metric: summary[MetricType.ANALYSIS_TIME]?.avg || 100,
        weight: 0.2,
        threshold: 100, // 100ms
        isHigherBetter: false
      },
      { 
        metric: summary.signalEfficiency || 0,
        weight: 0.3,
        threshold: 0.01, // At least 1%
        isHigherBetter: true
      },
      { 
        metric: summary.signalConversionRate || 0,
        weight: 0.3,
        threshold: 0.1, // At least 10%
        isHigherBetter: true
      }
    ];
    
    // Calculate health score
    let healthScore = 0;
    let totalWeight = 0;
    
    for (const { metric, weight, threshold, isHigherBetter } of metrics) {
      let metricScore: number;
      
      if (isHigherBetter) {
        // Higher is better (e.g., efficiency)
        metricScore = Math.min(1, metric / threshold);
      } else {
        // Lower is better (e.g., latency)
        metricScore = metric > threshold ? 0 : 1 - (metric / threshold);
      }
      
      healthScore += metricScore * weight;
      totalWeight += weight;
    }
    
    return totalWeight > 0 ? (healthScore / totalWeight) * 100 : 0;
  }
  
  /**
   * Save metrics to disk
   */
  public flushMetrics(): void {
    if (!this.options.enableFileLogging) return;
    
    try {
      // Use date as part of filename
      const date = new Date().toISOString().split('T')[0];
      const fileName = `metrics_${date}.json`;
      const filePath = path.join(this.options.logDirectory, fileName);
      
      // Convert metrics to serializable format
      const serializableMetrics: Record<string, any> = {};
      this.metrics.forEach((dataPoints, key) => {
        serializableMetrics[key] = dataPoints;
      });
      
      // Write to file (append if exists)
      let existingData: Record<string, any> = {};
      if (fs.existsSync(filePath)) {
        const content = fs.readFileSync(filePath, 'utf-8');
        try {
          existingData = JSON.parse(content);
        } catch (err) {
          console.error(`Error parsing existing metrics file ${filePath}:`, err);
        }
      }
      
      // Merge existing data with new metrics
      Object.entries(serializableMetrics).forEach(([key, dataPoints]) => {
        if (!existingData[key]) existingData[key] = [];
        existingData[key] = [...existingData[key], ...dataPoints];
      });
      
      // Write merged data
      fs.writeFileSync(filePath, JSON.stringify(existingData, null, 2));
      
      // Clear in-memory metrics after flush
      Object.values(MetricType).forEach(type => {
        this.metrics.set(type as MetricType, []);
      });
      
      // Clean up old metric files
      this.cleanupOldMetrics();
    } catch (error) {
      console.error('Error flushing metrics to disk:', error);
    }
  }
  
  /**
   * Remove metrics files older than retention period
   */
  private cleanupOldMetrics(): void {
    if (!this.options.enableFileLogging) return;
    
    try {
      const files = fs.readdirSync(this.options.logDirectory);
      const now = Date.now();
      const cutoffTime = now - (this.options.retentionPeriodDays * 24 * 60 * 60 * 1000);
      
      for (const file of files) {
        if (!file.startsWith('metrics_') || !file.endsWith('.json')) continue;
        
        // Extract date from filename
        const dateStr = file.replace('metrics_', '').replace('.json', '');
        const fileDate = new Date(dateStr).getTime();
        
        // Remove if older than retention period
        if (fileDate < cutoffTime) {
          fs.unlinkSync(path.join(this.options.logDirectory, file));
        }
      }
    } catch (error) {
      console.error('Error cleaning up old metrics files:', error);
    }
  }
  
  /**
   * Cleanup resources and ensure metrics are saved
   */
  public shutdown(): void {
    // Flush metrics to disk
    this.flushMetrics();
    
    // Clear timer if running
    if (this.flushTimer) {
      clearInterval(this.flushTimer);
      this.flushTimer = null;
    }
  }
}