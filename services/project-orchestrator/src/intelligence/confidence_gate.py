from typing import List
from .decision_modifier import Adjustment, TaskAdjustment, DurationAdjustment # Import necessary types
from intelligence.performance_monitor import PerformanceMonitor, PerformanceMetrics # New import
import time # New import

class ConfidenceGate:
    def __init__(self, performance_monitor: PerformanceMonitor):
        self.performance_monitor = performance_monitor

    def validate_adjustment_confidence(self, adjustment: Adjustment, threshold: float) -> bool:
        """
        Validates if the adjustment's confidence meets the specified threshold.
        """
        return adjustment.confidence >= threshold

    def validate_supporting_evidence(self, adjustment: Adjustment, min_projects: int = 3) -> bool:
        """
        Validates if the adjustment has sufficient supporting evidence.
        For TaskAdjustment, checks if 'evidence_source' indicates enough similar projects.
        For other adjustments, this might be a simpler check or always return True if not applicable.
        """
        if isinstance(adjustment, TaskAdjustment):
            # Example: "3 similar projects analysis"
            try:
                num_projects_str = adjustment.evidence_source.split(" ")[0]
                num_projects = int(num_projects_str)
                return num_projects >= min_projects
            except (ValueError, IndexError):
                return False
        # For other types of adjustments, if no specific evidence requirement, consider it valid
        return True

    def validate_max_adjustment_limit(self, adjustment: Adjustment, max_percent_change: float = 0.5) -> bool:
        """
        Validates if the proposed adjustment is within the maximum allowed percentage change
        from the original recommendation.
        """
        if adjustment.original_recommendation is None or adjustment.intelligence_recommendation is None:
            return True # Cannot validate if original or intelligence recommendation is missing

        try:
            original = float(adjustment.original_recommendation)
            intelligent = float(adjustment.intelligence_recommendation)

            if original == 0:
                # If original is 0, any non-zero intelligent recommendation is a 100% change.
                # This case needs careful handling, perhaps a fixed max value instead of percentage.
                # For now, if original is 0 and intelligent is also 0, it's valid.
                # If original is 0 and intelligent is not 0, it's an infinite percentage change,
                # so we might want to disallow it or apply a different rule.
                return intelligent == 0
            
            percent_change = abs((intelligent - original) / original)
            return percent_change <= max_percent_change
        except (ValueError, TypeError):
            # If conversion to float fails, cannot perform percentage check.
            # Assume valid or handle as an impediment.
            return True

    def filter_low_confidence_adjustments(self, adjustments: List[Adjustment], confidence_threshold: float = 0.75, min_projects_for_task_adjustment: int = 3, max_adjustment_percent: float = 0.5) -> List[Adjustment]:
        """
        Filters a list of adjustments, returning only those that meet all confidence and evidence thresholds.
        """
        validated_adjustments = []
        for adj in adjustments:
            is_valid = (self.validate_adjustment_confidence(adj, threshold=confidence_threshold) and
                        self.validate_supporting_evidence(adj, min_projects_for_task_adjustment) and
                        self.validate_max_adjustment_limit(adj, max_adjustment_percent))
            
            # Record metric for confidence gating
            self.performance_monitor.record_metric(
                PerformanceMetrics(
                    operation_name="confidence_gating_check",
                    start_time=time.time(), # Need to import time
                    end_time=time.time(),
                    duration_ms=0.0, # Instantaneous check
                    success=is_valid,
                    error_message=f"Failed confidence gate for {adj.original_recommendation}" if not is_valid else None
                )
            )

            if is_valid:
                validated_adjustments.append(adj)
        return validated_adjustments
