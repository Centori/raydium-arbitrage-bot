import { PerformanceMetrics, MetricType } from '../utils/PerformanceMetrics';
import { MetricsDashboard } from '../utils/MetricsDashboard';
import chalk from 'chalk';

/**
 * This script tests the metrics dashboard and performance metrics system
 * by generating sample data and displaying it in the dashboard.
 */

async function generateSampleData(metrics: PerformanceMetrics): Promise<void> {
  console.log('Generating sample metrics data...');
  
  // Generate API latency metrics
  const apiLatencies = [120, 150, 180, 220, 140, 130, 250, 200, 190];
  apiLatencies.forEach(latency => {
    metrics.recordMetric(MetricType.API_LATENCY, latency, { endpoint: 'raydium/ammPools' });
  });
  
  // Generate analysis time metrics
  const analysisTimes = [15, 18, 22, 19, 17, 20, 25, 18, 16];
  analysisTimes.forEach(time => {
    metrics.recordMetric(MetricType.ANALYSIS_TIME, time);
  });
  
  // Generate pattern detection metrics
  const patternTimes = [35, 38, 42, 39, 40, 45, 38, 36, 41];
  patternTimes.forEach(time => {
    metrics.recordMetric(MetricType.PATTERN_DETECTION, time);
  });
  
  // Generate data processing metrics
  const processingTimes = [80, 85, 90, 95, 82, 88, 92, 89, 86];
  processingTimes.forEach(time => {
    metrics.recordMetric(MetricType.DATA_PROCESSING, time);
  });
  
  // Record pools analyzed
  metrics.recordMetric(MetricType.POOLS_ANALYZED, 1000);
  metrics.recordMetric(MetricType.POOLS_ANALYZED, 1050);
  metrics.recordMetric(MetricType.POOLS_ANALYZED, 980);
  
  // Record opportunities found
  metrics.recordMetric(MetricType.OPPORTUNITIES_FOUND, 12);
  metrics.recordMetric(MetricType.OPPORTUNITIES_FOUND, 8);
  metrics.recordMetric(MetricType.OPPORTUNITIES_FOUND, 15);
  
  // Record accumulation patterns
  metrics.recordMetric(MetricType.ACCUMULATION_DETECTED, 30);
  metrics.recordMetric(MetricType.ACCUMULATION_DETECTED, 25);
  metrics.recordMetric(MetricType.ACCUMULATION_DETECTED, 35);
  
  // Record strong signals
  metrics.recordMetric(MetricType.STRONG_SIGNALS, 5);
  metrics.recordMetric(MetricType.STRONG_SIGNALS, 4);
  metrics.recordMetric(MetricType.STRONG_SIGNALS, 6);
  
  // Record alerts
  metrics.recordMetric(MetricType.ALERT_COUNT, 3);
  metrics.recordMetric(MetricType.ALERT_COUNT, 2);
  metrics.recordMetric(MetricType.ALERT_COUNT, 4);
  
  // Record signal accuracy
  metrics.recordMetric(MetricType.SIGNAL_ACCURACY, 78);
  metrics.recordMetric(MetricType.SIGNAL_ACCURACY, 82);
  metrics.recordMetric(MetricType.SIGNAL_ACCURACY, 75);
  
  console.log('Sample data generation complete.');
}

async function testMetricsDashboard() {
  console.log(chalk.blue.bold('=== Testing Metrics Dashboard ==='));
  
  // Create metrics instance
  const metrics = new PerformanceMetrics({
    enableFileLogging: true,
    logDirectory: './data/metrics'
  });
  
  // Generate sample data
  await generateSampleData(metrics);
  
  // Create and start dashboard
  const dashboard = new MetricsDashboard(metrics, {
    refreshIntervalMs: 5000,
    colorized: true,
    showAllMetrics: true
  });
  
  // Start dashboard
  dashboard.start();
  
  console.log('Dashboard started. Press Ctrl+C to exit.');
  
  // Keep generating new data periodically to simulate a live system
  setInterval(async () => {
    // Add API latency
    metrics.recordMetric(
      MetricType.API_LATENCY, 
      150 + Math.random() * 100
    );
    
    // Add analysis time
    metrics.recordMetric(
      MetricType.ANALYSIS_TIME, 
      15 + Math.random() * 15
    );
    
    // Record pools analyzed (random between 950-1050)
    metrics.recordMetric(
      MetricType.POOLS_ANALYZED, 
      950 + Math.floor(Math.random() * 100)
    );
    
    // Record opportunities (random between 5-20)
    const opps = 5 + Math.floor(Math.random() * 15);
    metrics.recordMetric(MetricType.OPPORTUNITIES_FOUND, opps);
    
    // Record accumulation patterns (random between 20-40)
    const patterns = 20 + Math.floor(Math.random() * 20);
    metrics.recordMetric(MetricType.ACCUMULATION_DETECTED, patterns);
    
    // Record strong signals (random between 3-8)
    const signals = 3 + Math.floor(Math.random() * 5);
    metrics.recordMetric(MetricType.STRONG_SIGNALS, signals);
    
    // Record alerts (random between 1-5)
    const alerts = 1 + Math.floor(Math.random() * 4);
    metrics.recordMetric(MetricType.ALERT_COUNT, alerts);
    
    // Record signal accuracy (random between 70-90)
    metrics.recordMetric(
      MetricType.SIGNAL_ACCURACY, 
      70 + Math.random() * 20
    );
  }, 3000); // Update every 3 seconds
}

// Run the test if this file is executed directly
if (require.main === module) {
  testMetricsDashboard().catch(console.error);
  
  // Handle graceful shutdown
  process.on('SIGINT', () => {
    console.log('\nExiting...');
    process.exit(0);
  });
}