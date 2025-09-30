#!/usr/bin/env python3
"""
Jito Bundle Analyzer
Analyzes successful Jito bundles to optimize trading parameters and detect profitable patterns
"""

import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass
from config import DEX_CONFIG, PATTERN_CONFIG, MONITORED_PAIRS, TUNING_CONFIG

@dataclass
class BundleTransaction:
    signature: str
    dexes_used: List[str]
    token_path: List[str]
    profit: float
    pattern_type: str
    instructions: List[Dict]

@dataclass
class PatternStats:
    total_attempts: int = 0
    successful_attempts: int = 0
    total_profit: float = 0.0
    avg_profit: float = 0.0
    success_rate: float = 0.0
    optimal_size: float = 0.0

class JitoBundleAnalyzer:
    def __init__(self, data_dir: str = "data/bundles"):
        self.data_dir = data_dir
        self.pattern_stats: Dict[str, PatternStats] = {}
        self.successful_patterns: List[BundleTransaction] = []
        os.makedirs(data_dir, exist_ok=True)
        
    def analyze_bundles(self, days_back: int = 7) -> Dict:
        """Analyze recent bundles to identify successful patterns"""
        print(f"Analyzing bundles from the last {days_back} days...")
        
        cutoff_date = datetime.now() - timedelta(days=days_back)
        bundle_files = self._get_recent_bundle_files(cutoff_date)
        
        for bundle_file in bundle_files:
            bundle_data = self._load_bundle_data(bundle_file)
            if not bundle_data:
                continue
                
            tx = self._parse_bundle_transaction(bundle_data)
            if tx and tx.profit > 0:
                self._update_pattern_stats(tx)
                self.successful_patterns.append(tx)
        
        return self._generate_optimization_report()
    
    def _get_recent_bundle_files(self, cutoff_date: datetime) -> List[str]:
        """Get bundle files newer than cutoff date"""
        bundle_files = []
        for filename in os.listdir(self.data_dir):
            if not filename.startswith("profitable_bundle_"):
                continue
            
            try:
                # Parse date from filename format profitable_bundle_YYYYMMDD_HHMMSS.json
                date_str = filename.split("_")[2:4]
                file_date = datetime.strptime("_".join(date_str), "%Y%m%d_%H%M%S")
                
                if file_date >= cutoff_date:
                    bundle_files.append(os.path.join(self.data_dir, filename))
            except (IndexError, ValueError):
                continue
                
        return bundle_files
    
    def _load_bundle_data(self, filepath: str) -> Optional[Dict]:
        """Load and validate bundle data from file"""
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error loading bundle {filepath}: {str(e)}")
            return None
    
    def _parse_bundle_transaction(self, bundle_data: Dict) -> Optional[BundleTransaction]:
        """Parse bundle data into transaction object"""
        try:
            analysis = bundle_data.get("analysis", {})
            
            return BundleTransaction(
                signature=bundle_data.get("bundle", {}).get("signature", "unknown"),
                dexes_used=analysis.get("dexes_used", []),
                token_path=analysis.get("token_path", []),
                profit=analysis.get("profit", 0.0),
                pattern_type="_".join(analysis.get("pattern", ["UNKNOWN"])),
                instructions=analysis.get("instructions", [])
            )
        except KeyError:
            return None
    
    def _update_pattern_stats(self, tx: BundleTransaction):
        """Update statistics for a pattern"""
        if tx.pattern_type not in self.pattern_stats:
            self.pattern_stats[tx.pattern_type] = PatternStats()
            
        stats = self.pattern_stats[tx.pattern_type]
        stats.total_attempts += 1
        
        if tx.profit > 0:
            stats.successful_attempts += 1
            stats.total_profit += tx.profit
            
        # Update averages
        stats.success_rate = stats.successful_attempts / stats.total_attempts
        stats.avg_profit = stats.total_profit / stats.successful_attempts if stats.successful_attempts > 0 else 0
        
        # Calculate optimal size based on past successes
        if tx.profit > 0:
            # Use exponential moving average for optimal size
            alpha = 0.2  # Weight for new values
            new_optimal = tx.profit * 2  # Conservative estimate
            stats.optimal_size = (alpha * new_optimal + 
                                (1 - alpha) * stats.optimal_size if stats.optimal_size > 0 
                                else new_optimal)
    
    def _generate_optimization_report(self) -> Dict:
        """Generate optimization suggestions based on analysis"""
        report = {
            "pattern_performance": {},
            "dex_performance": self._analyze_dex_performance(),
            "token_opportunities": self._analyze_token_opportunities(),
            "optimization_suggestions": []
        }
        
        # Analyze each pattern
        for pattern, stats in self.pattern_stats.items():
            report["pattern_performance"][pattern] = {
                "success_rate": stats.success_rate,
                "avg_profit": stats.avg_profit,
                "total_profit": stats.total_profit,
                "optimal_size": stats.optimal_size,
                "confidence_score": self._calculate_confidence_score(stats)
            }
            
            # Generate suggestions
            if stats.success_rate >= TUNING_CONFIG["success_threshold"]:
                report["optimization_suggestions"].append({
                    "pattern": pattern,
                    "action": "INCREASE_ALLOCATION",
                    "reason": f"High success rate ({stats.success_rate:.1%})",
                    "suggestion": f"Consider increasing position size to {stats.optimal_size:.3f} SOL"
                })
            elif stats.success_rate < 0.5 and stats.total_attempts > 10:
                report["optimization_suggestions"].append({
                    "pattern": pattern,
                    "action": "DECREASE_ALLOCATION",
                    "reason": f"Low success rate ({stats.success_rate:.1%})",
                    "suggestion": "Consider reducing exposure or removing pattern"
                })
        
        return report
    
    def _analyze_dex_performance(self) -> Dict:
        """Analyze performance of different DEXes"""
        dex_stats = {}
        
        for tx in self.successful_patterns:
            for dex in tx.dexes_used:
                if dex not in dex_stats:
                    dex_stats[dex] = {"count": 0, "total_profit": 0.0}
                    
                dex_stats[dex]["count"] += 1
                dex_stats[dex]["total_profit"] += tx.profit
        
        # Calculate averages and success metrics
        for dex in dex_stats:
            stats = dex_stats[dex]
            stats["avg_profit"] = stats["total_profit"] / stats["count"]
            
        return dex_stats
    
    def _analyze_token_opportunities(self) -> Dict:
        """Analyze which tokens provide best opportunities"""
        token_stats = {}
        
        for tx in self.successful_patterns:
            for token in tx.token_path:
                if token not in token_stats:
                    token_stats[token] = {"count": 0, "total_profit": 0.0}
                    
                token_stats[token]["count"] += 1
                token_stats[token]["total_profit"] += tx.profit
        
        # Calculate averages and metrics
        for token in token_stats:
            stats = token_stats[token]
            stats["avg_profit"] = stats["total_profit"] / stats["count"]
            stats["opportunity_score"] = stats["avg_profit"] * stats["count"]
            
        return token_stats
    
    def _calculate_confidence_score(self, stats: PatternStats) -> float:
        """Calculate confidence score for a pattern"""
        if stats.total_attempts < 5:
            return 0.0
            
        # Weight different factors
        profit_score = min(1.0, stats.avg_profit / 0.1)  # Scale profit up to 0.1 SOL
        success_score = stats.success_rate
        volume_score = min(1.0, stats.total_attempts / 20)  # Scale up to 20 attempts
        
        # Combine scores with weights from config
        return (TUNING_CONFIG["profit_weight"] * profit_score +
                TUNING_CONFIG["success_rate_weight"] * success_score) * volume_score

def main():
    analyzer = JitoBundleAnalyzer()
    report = analyzer.analyze_bundles(days_back=7)
    
    print("\n=== Jito Bundle Analysis Report ===")
    print("\nPattern Performance:")
    for pattern, perf in report["pattern_performance"].items():
        print(f"\n{pattern}:")
        print(f"  Success Rate: {perf['success_rate']:.1%}")
        print(f"  Avg Profit: {perf['avg_profit']:.6f} SOL")
        print(f"  Confidence Score: {perf['confidence_score']:.2f}")
    
    print("\nOptimization Suggestions:")
    for sugg in report["optimization_suggestions"]:
        print(f"\n- {sugg['pattern']}:")
        print(f"  Action: {sugg['action']}")
        print(f"  Reason: {sugg['reason']}")
        print(f"  Suggestion: {sugg['suggestion']}")
    
    # Save updated configurations if needed
    if report["optimization_suggestions"]:
        from config import update_pattern_config
        update_pattern_config(report["pattern_performance"])
        print("\nUpdated pattern configurations based on analysis.")

if __name__ == "__main__":
    main()