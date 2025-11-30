from typing import List, Dict, Any, Optional
import structlog
from models import SimilarProject, VelocityTrends, Adjustment, TaskAdjustment, DurationAdjustment
from intelligence.decision_config import DecisionConfig

logger = structlog.get_logger()


class DecisionModifier:
    def __init__(self, config: DecisionConfig):
        self.config = config

    def generate_task_count_adjustment(self, base_task_count: int, similar_projects: List[SimilarProject], evidence_details: Optional[Dict[str, Any]] = None) -> Optional[TaskAdjustment]:
        """
        Generates a task count adjustment based on similar projects.
        If similar projects (similarity >0.7) show optimal task count different from
        rule-based recommendation by >2 tasks AND confidence >0.75, suggest adjustment.
        """
        logger.debug("[DECISION_MODIFIER] Starting task count adjustment generation", 
                    base_task_count=base_task_count, 
                    similar_projects_count=len(similar_projects) if similar_projects else 0)
        
        if not similar_projects:
            logger.debug("[DECISION_MODIFIER] No similar projects provided - returning None")
            return None

        # Filter similar projects based on similarity score
        relevant_projects = [p for p in similar_projects if p.similarity_score > self.config.min_similarity_for_adjustment_proposal]
        
        logger.debug("[DECISION_MODIFIER] Filtered relevant projects", 
                    relevant_projects_count=len(relevant_projects),
                    similarity_scores=[p.similarity_score for p in relevant_projects[:3]])  # Show first 3

        if not relevant_projects:
            logger.debug("[DECISION_MODIFIER] No relevant projects after filtering - returning None")
            return None

        # Calculate average optimal task count and confidence from relevant projects
        total_optimal_task_count = 0
        total_confidence = 0.0
        num_projects_for_task_count = 0

        for project in relevant_projects:
            if project.optimal_task_count is not None:
                total_optimal_task_count += project.optimal_task_count
                # Assuming project.completion_rate can serve as a proxy for confidence in its optimal_task_count
                total_confidence += project.completion_rate # This might need refinement based on actual CR 2 output
                num_projects_for_task_count += 1

        if num_projects_for_task_count == 0:
            return None

        avg_optimal_task_count = round(total_optimal_task_count / num_projects_for_task_count)
        avg_confidence = total_confidence / num_projects_for_task_count

        logger.debug("[DECISION_MODIFIER] Calculated averages", 
                    avg_optimal_task_count=avg_optimal_task_count, 
                    avg_confidence=avg_confidence,
                    num_projects=num_projects_for_task_count,
                    task_count_difference=abs(base_task_count - avg_optimal_task_count))

        # Check if adjustment is needed based on criteria
        if abs(base_task_count - avg_optimal_task_count) > self.config.task_adjustment_difference_threshold and avg_confidence > self.config.min_confidence_for_task_proposal:
            reasoning = (
                f"Historical analysis of {num_projects_for_task_count} similar projects "
                f"(avg similarity >0.7, avg confidence {avg_confidence:.2f}) suggests "
                f"an optimal task count of {avg_optimal_task_count} compared to the rule-based {base_task_count}."
            )
            # Placeholder for expected improvement - this would come from more detailed analysis
            expected_improvement = f"Potentially higher completion rate based on historical data."

            logger.debug("[DECISION_MODIFIER] Generating task adjustment", 
                        original=base_task_count, 
                        intelligence_recommendation=avg_optimal_task_count,
                        confidence=avg_confidence)
            
            return TaskAdjustment(
                original_recommendation=base_task_count,
                intelligence_recommendation=avg_optimal_task_count,
                applied_value=avg_optimal_task_count, # This will be set by ConfidenceGate
                confidence=avg_confidence,
                evidence_source=f"{num_projects_for_task_count} similar projects analysis",
                rationale=reasoning,
                expected_improvement=expected_improvement,
                evidence_details=evidence_details
            )
        
        logger.debug("[DECISION_MODIFIER] No adjustment needed", 
                    criteria_met=f"diff > 2: {abs(base_task_count - avg_optimal_task_count) > 2}, confidence > 0.5: {avg_confidence > 0.5}")
        return None

    def generate_sprint_duration_adjustment(self, base_duration: int, velocity_trends: VelocityTrends, evidence_details: Optional[Dict[str, Any]] = None) -> Optional[DurationAdjustment]:
        """
        Generates a sprint duration adjustment based on velocity trends.
        If velocity trends indicate team can handle different duration with sufficient confidence, suggest modification.
        """
        if not velocity_trends or velocity_trends.confidence < self.config.min_velocity_confidence_for_duration_adjustment:
            return None

        # This logic is simplified. A real implementation would compare current velocity
        # with historical optimal velocities for different durations.
        # For now, let's assume 'trend_direction' can imply a duration change.
        # This part needs more concrete logic from CR 2 or further definition.
        # For demonstration, if velocity is 'increasing' and base duration is high, suggest reduction.
        # If velocity is 'decreasing' and base duration is low, suggest increase.

        intelligence_recommendation = base_duration
        rationale = f"Current team velocity is {velocity_trends.trend_direction} with {velocity_trends.confidence:.2f} confidence."

        # Example simplified logic:
        if velocity_trends.trend_direction == "increasing" and base_duration > 1:
            intelligence_recommendation = max(1, base_duration - 1) # Suggest reducing duration
            rationale += f" Suggesting a shorter duration of {intelligence_recommendation} weeks."
        elif velocity_trends.trend_direction == "decreasing" and base_duration < 4: # Assuming max 4 weeks
            intelligence_recommendation = min(4, base_duration + 1) # Suggest increasing duration
            rationale += f" Suggesting a longer duration of {intelligence_recommendation} weeks."
        else:
            return None # No significant adjustment based on this simplified logic

        if intelligence_recommendation != base_duration:
            return DurationAdjustment(
                original_recommendation=base_duration,
                intelligence_recommendation=intelligence_recommendation,
                applied_value=intelligence_recommendation, # This will be set by ConfidenceGate
                confidence=velocity_trends.confidence,
                evidence_source="velocity trend analysis",
                rationale=rationale,
                evidence_details=evidence_details
            )
        return None

    def calculate_adjustment_confidence(self, adjustment: Adjustment, supporting_data: Dict[str, Any]) -> float:
        """
        Calculates the confidence score for a given adjustment.
        This is a placeholder; actual confidence calculation would be more complex.
        """
        # For now, return the confidence already present in the adjustment
        # or a default if not explicitly set.
        return adjustment.confidence if adjustment.confidence is not None else 0.0

    def generate_adjustment_reasoning(self, adjustment: Adjustment) -> str:
        """
        Generates a human-readable reasoning string for an adjustment.
        """
        return adjustment.rationale
