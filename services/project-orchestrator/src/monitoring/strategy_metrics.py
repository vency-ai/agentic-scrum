"""
Strategy Evolution Monitoring Metrics

Provides Prometheus metrics for monitoring the Strategy Evolution Layer performance.
"""

import logging
from typing import Dict, Any, Optional
from prometheus_client import Counter, Histogram, Gauge, Info
from datetime import datetime

logger = logging.getLogger(__name__)

# Strategy Evolution Metrics
STRATEGY_EVOLUTION_RUNS_TOTAL = Counter(
    'strategy_evolution_runs_total',
    'Total number of strategy evolution runs',
    ['status', 'mode']  # status: completed/failed/disabled, mode: daily/manual/project
)

STRATEGY_EVOLUTION_DURATION_SECONDS = Histogram(
    'strategy_evolution_duration_seconds',
    'Duration of strategy evolution runs in seconds',
    ['mode']  # mode: daily/manual/project
)

STRATEGIES_GENERATED_TOTAL = Counter(
    'strategies_generated_total',
    'Total number of strategies generated',
    ['evolution_mode']
)

STRATEGIES_OPTIMIZED_TOTAL = Counter(
    'strategies_optimized_total',
    'Total number of strategies optimized',
    ['optimization_action']  # action: confidence_adjusted/deactivated/no_action
)

STRATEGIES_DEACTIVATED_TOTAL = Counter(
    'strategies_deactivated_total',
    'Total number of strategies deactivated',
    ['reason']  # reason: underperforming/manual/cleanup
)

PATTERNS_EXTRACTED_TOTAL = Counter(
    'patterns_extracted_total',
    'Total number of patterns extracted from episodes',
    ['pattern_type']  # pattern_type: context/resource/task/timing
)

STRATEGY_APPLICATION_TOTAL = Counter(
    'strategy_application_total',
    'Total number of times strategies were applied to decisions',
    ['strategy_type']
)

STRATEGY_SUCCESS_TOTAL = Counter(
    'strategy_success_total',
    'Total number of successful strategy applications',
    ['strategy_type']
)

# Current state gauges
ACTIVE_STRATEGIES_COUNT = Gauge(
    'active_strategies_count',
    'Current number of active strategies'
)

STRATEGY_REPOSITORY_SIZE_BYTES = Gauge(
    'strategy_repository_size_bytes',
    'Approximate size of strategy repository in bytes'
)

AVERAGE_STRATEGY_CONFIDENCE = Gauge(
    'average_strategy_confidence',
    'Average confidence of all active strategies'
)

AVERAGE_STRATEGY_SUCCESS_RATE = Gauge(
    'average_strategy_success_rate',
    'Average success rate of all active strategies'
)

# Performance metrics
STRATEGY_PATTERN_ANALYSIS_DURATION_SECONDS = Histogram(
    'strategy_pattern_analysis_duration_seconds',
    'Duration of strategy-enhanced pattern analysis in seconds'
)

STRATEGY_QUERY_DURATION_SECONDS = Histogram(
    'strategy_query_duration_seconds',
    'Duration of strategy repository queries in seconds',
    ['query_type']  # query_type: find_applicable/get_analytics/get_performance
)

# System info
STRATEGY_EVOLUTION_INFO = Info(
    'strategy_evolution_info',
    'Information about the Strategy Evolution Layer'
)

class StrategyMetricsCollector:
    """Collector for strategy evolution metrics"""
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._update_system_info()
    
    def _update_system_info(self):
        """Update system information metrics"""
        try:
            STRATEGY_EVOLUTION_INFO.info({
                'version': '1.0.0',
                'component': 'strategy_evolution_layer',
                'last_updated': datetime.utcnow().isoformat()
            })
        except Exception as e:
            self.logger.error(f"Failed to update system info: {e}")
    
    def record_evolution_run(self, status: str, mode: str, duration_seconds: float):
        """Record a strategy evolution run"""
        try:
            STRATEGY_EVOLUTION_RUNS_TOTAL.labels(status=status, mode=mode).inc()
            STRATEGY_EVOLUTION_DURATION_SECONDS.labels(mode=mode).observe(duration_seconds)
            self.logger.debug(f"Recorded evolution run: status={status}, mode={mode}, duration={duration_seconds:.2f}s")
        except Exception as e:
            self.logger.error(f"Failed to record evolution run: {e}")
    
    def record_strategies_generated(self, count: int, evolution_mode: str):
        """Record strategies generated"""
        try:
            STRATEGIES_GENERATED_TOTAL.labels(evolution_mode=evolution_mode).inc(count)
            self.logger.debug(f"Recorded {count} strategies generated in {evolution_mode} mode")
        except Exception as e:
            self.logger.error(f"Failed to record strategies generated: {e}")
    
    def record_strategies_optimized(self, count: int, optimization_action: str):
        """Record strategies optimized"""
        try:
            STRATEGIES_OPTIMIZED_TOTAL.labels(optimization_action=optimization_action).inc(count)
            self.logger.debug(f"Recorded {count} strategies {optimization_action}")
        except Exception as e:
            self.logger.error(f"Failed to record strategies optimized: {e}")
    
    def record_strategies_deactivated(self, count: int, reason: str):
        """Record strategies deactivated"""
        try:
            STRATEGIES_DEACTIVATED_TOTAL.labels(reason=reason).inc(count)
            self.logger.debug(f"Recorded {count} strategies deactivated for {reason}")
        except Exception as e:
            self.logger.error(f"Failed to record strategies deactivated: {e}")
    
    def record_patterns_extracted(self, count: int, pattern_type: str):
        """Record patterns extracted"""
        try:
            PATTERNS_EXTRACTED_TOTAL.labels(pattern_type=pattern_type).inc(count)
            self.logger.debug(f"Recorded {count} {pattern_type} patterns extracted")
        except Exception as e:
            self.logger.error(f"Failed to record patterns extracted: {e}")
    
    def record_strategy_application(self, strategy_type: str, success: bool):
        """Record strategy application and its outcome"""
        try:
            STRATEGY_APPLICATION_TOTAL.labels(strategy_type=strategy_type).inc()
            if success:
                STRATEGY_SUCCESS_TOTAL.labels(strategy_type=strategy_type).inc()
            self.logger.debug(f"Recorded strategy application: type={strategy_type}, success={success}")
        except Exception as e:
            self.logger.error(f"Failed to record strategy application: {e}")
    
    def update_repository_metrics(self, analytics: Dict[str, Any]):
        """Update repository state metrics from analytics"""
        try:
            active_count = analytics.get('active_strategies', 0)
            ACTIVE_STRATEGIES_COUNT.set(active_count)
            
            # Update performance metrics if available
            perf_stats = analytics.get('performance_stats', {})
            if perf_stats:
                avg_confidence = perf_stats.get('avg_strategy_confidence', 0)
                if avg_confidence:
                    AVERAGE_STRATEGY_CONFIDENCE.set(avg_confidence)
            
            # Estimate repository size (rough approximation)
            total_strategies = analytics.get('total_strategies', 0)
            estimated_size = total_strategies * 1024  # Rough estimate of 1KB per strategy
            STRATEGY_REPOSITORY_SIZE_BYTES.set(estimated_size)
            
            self.logger.debug(f"Updated repository metrics: active={active_count}, total={total_strategies}")
            
        except Exception as e:
            self.logger.error(f"Failed to update repository metrics: {e}")
    
    def record_pattern_analysis_duration(self, duration_seconds: float):
        """Record strategy-enhanced pattern analysis duration"""
        try:
            STRATEGY_PATTERN_ANALYSIS_DURATION_SECONDS.observe(duration_seconds)
            self.logger.debug(f"Recorded pattern analysis duration: {duration_seconds:.3f}s")
        except Exception as e:
            self.logger.error(f"Failed to record pattern analysis duration: {e}")
    
    def record_strategy_query_duration(self, query_type: str, duration_seconds: float):
        """Record strategy repository query duration"""
        try:
            STRATEGY_QUERY_DURATION_SECONDS.labels(query_type=query_type).observe(duration_seconds)
            self.logger.debug(f"Recorded strategy query duration: type={query_type}, duration={duration_seconds:.3f}s")
        except Exception as e:
            self.logger.error(f"Failed to record strategy query duration: {e}")

# Global metrics collector instance
strategy_metrics_collector = StrategyMetricsCollector()