import time
import asyncio
from typing import Dict, List, Optional, Any
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger(__name__)

class PerformanceMetrics(BaseModel):
    operation_name: str
    start_time: float
    end_time: float
    duration_ms: float
    success: bool
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class PerformanceMonitor:
    def __init__(self):
        self.metrics: List[PerformanceMetrics] = []
        self.intelligence_invocations: int = 0
        self.recommendations_generated: int = 0
        self.adjustments_applied: int = 0
        
        # Hybrid intelligence specific metrics
        self.hybrid_analysis_count: int = 0
        self.episode_retrieval_count: int = 0
        self.pattern_combination_count: int = 0
        self.cache_hits: int = 0
        self.cache_misses: int = 0
        
    def time_operation(self, operation_name: str):
        """Context manager to time operations"""
        return TimedOperation(operation_name, self)
    
    def record_metric(self, metric: PerformanceMetrics):
        self.metrics.append(metric)
        logger.info("Performance metric recorded", 
                   operation=metric.operation_name,
                   duration_ms=metric.duration_ms,
                   success=metric.success)

    def increment_intelligence_invocations(self):
        self.intelligence_invocations += 1
        logger.debug("Intelligence invocations incremented", count=self.intelligence_invocations)

    def increment_recommendations_generated(self):
        self.recommendations_generated += 1
        logger.debug("Recommendations generated incremented", count=self.recommendations_generated)

    def increment_adjustments_applied(self):
        self.adjustments_applied += 1
        logger.debug("Adjustments applied incremented", count=self.adjustments_applied)
    
    def increment_hybrid_analysis(self):
        """Track hybrid analysis operations."""
        self.hybrid_analysis_count += 1
        logger.debug("Hybrid analysis incremented", count=self.hybrid_analysis_count)
    
    def increment_episode_retrieval(self):
        """Track episode retrieval operations."""
        self.episode_retrieval_count += 1
        logger.debug("Episode retrieval incremented", count=self.episode_retrieval_count)
    
    def increment_pattern_combination(self):
        """Track pattern combination operations."""
        self.pattern_combination_count += 1
        logger.debug("Pattern combination incremented", count=self.pattern_combination_count)
    
    def record_cache_hit(self):
        """Record cache hit for performance tracking."""
        self.cache_hits += 1
        logger.debug("Cache hit recorded", hits=self.cache_hits, total=self.cache_hits + self.cache_misses)
    
    def record_cache_miss(self):
        """Record cache miss for performance tracking."""
        self.cache_misses += 1
        logger.debug("Cache miss recorded", misses=self.cache_misses, total=self.cache_hits + self.cache_misses)
    
    def get_cache_hit_rate(self) -> float:
        """Calculate cache hit rate percentage."""
        total_requests = self.cache_hits + self.cache_misses
        return (self.cache_hits / total_requests * 100) if total_requests > 0 else 0.0
    
    def get_summary(self, operation_name: Optional[str] = None) -> Dict:
        filtered_metrics = [m for m in self.metrics 
                          if not operation_name or m.operation_name == operation_name]
        
        if not filtered_metrics:
            return {"error": "No metrics found"}
            
        durations = [m.duration_ms for m in filtered_metrics if m.success]
        
        return {
            "operation": operation_name or "all",
            "total_calls": len(filtered_metrics),
            "successful_calls": len(durations),
            "avg_duration_ms": sum(durations) / len(durations) if durations else 0,
            "max_duration_ms": max(durations) if durations else 0,
            "min_duration_ms": min(durations) if durations else 0,
            "success_rate": len(durations) / len(filtered_metrics) * 100 if filtered_metrics else 0
        }

class TimedOperation:
    def __init__(self, operation_name: str, monitor: PerformanceMonitor):
        self.operation_name = operation_name
        self.monitor = monitor
        self.start_time = None
        
    def __enter__(self):
        self.start_time = time.time()
        return self
        
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any):
        end_time = time.time()
        duration_ms = (end_time - self.start_time) * 1000
        
        metric = PerformanceMetrics(
            operation_name=self.operation_name,
            start_time=self.start_time,
            end_time=end_time,
            duration_ms=duration_ms,
            success=exc_type is None,
            error_message=str(exc_val) if exc_val else None
        )
        
        self.monitor.record_metric(metric)
