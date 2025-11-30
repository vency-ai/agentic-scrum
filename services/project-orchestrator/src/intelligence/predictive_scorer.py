from typing import Dict, Any
import structlog

from intelligence.historical_analyzer import ProjectPatterns
from models import ProjectData, RiskAssessment, SprintPrediction # Import models from models.py

logger = structlog.get_logger()

class PredictiveScorer:
    def __init__(self):
        pass

    async def calculate_risk_score(self, historical_patterns: ProjectPatterns, current_project_data: ProjectData) -> RiskAssessment:
        """Calculates a risk score based on historical patterns and current project data."""
        overall_risk = 0.0
        sprint_failure_probability = 0.0
        capacity_overload_risk = 0.0
        confidence = 0.7 # Base confidence

        try:
            # Example: Simple heuristic-based risk calculation
            # Sprint failure probability: inversely proportional to historical completion rate
            if historical_patterns.completion_rate > 0:
                sprint_failure_probability = 1.0 - historical_patterns.completion_rate
            else:
                sprint_failure_probability = 0.5 # Default if no historical data

            # Capacity overload risk: based on unassigned tasks vs. team size
            if current_project_data.team_size > 0:
                # If many unassigned tasks relative to team size, higher risk
                capacity_overload_risk = min(1.0, current_project_data.unassigned_tasks / (current_project_data.team_size * 5)) # Assuming 5 tasks/person capacity
            else:
                capacity_overload_risk = 0.3 # Default if no team size

            # Overall risk is an average of contributing factors
            overall_risk = (sprint_failure_probability + capacity_overload_risk) / 2.0

            # Adjust confidence based on data availability and consistency
            if historical_patterns.avg_sprint_duration == 0.0 or historical_patterns.completion_rate == 0.0:
                confidence *= 0.5 # Reduce confidence if historical data is sparse

        except Exception as e:
            logger.error("Error calculating risk score", project_id=current_project_data.project_id, error=str(e))
            return RiskAssessment() # Return default on error

        return RiskAssessment(
            overall_risk=overall_risk,
            sprint_failure_probability=sprint_failure_probability,
            capacity_overload_risk=capacity_overload_risk,
            confidence=confidence
        )

    async def predict_sprint_outcome(self, historical_patterns: ProjectPatterns, current_project_data: ProjectData) -> SprintPrediction:
        """Predicts sprint outcome based on historical patterns and current project data."""
        predicted_completion_rate = 0.0
        predicted_duration_weeks = 0.0
        confidence = 0.7 # Base confidence

        try:
            # Example: Simple prediction based on historical averages
            predicted_completion_rate = historical_patterns.completion_rate
            predicted_duration_weeks = historical_patterns.avg_sprint_duration

            # Adjust confidence based on data availability
            if historical_patterns.avg_sprint_duration == 0.0 or historical_patterns.completion_rate == 0.0:
                confidence *= 0.5

        except Exception as e:
            logger.error("Error predicting sprint outcome", project_id=current_project_data.project_id, error=str(e))
            return SprintPrediction() # Return default on error

        return SprintPrediction(
            predicted_completion_rate=predicted_completion_rate,
            predicted_duration_weeks=predicted_duration_weeks,
            confidence=confidence
        )