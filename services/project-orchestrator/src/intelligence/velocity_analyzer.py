from typing import List, Dict, Any, Optional
import numpy as np
from scipy.stats import linregress
from models import VelocityTrends, TrendDirection, VelocityComparison, SimilarProject # Absolute import
import structlog

logger = structlog.get_logger()

def detect_trend_direction(velocity_history: List[float]) -> TrendDirection:
    """Detects the trend direction of velocity history using linear regression."""
    if len(velocity_history) < 2:
        return TrendDirection(direction="stable", slope=0.0)

    x = np.arange(len(velocity_history))
    slope, intercept, r_value, p_value, std_err = linregress(x, velocity_history)

    if slope > 0.1: # Threshold for increasing trend
        direction = "increasing"
    elif slope < -0.1: # Threshold for decreasing trend
        direction = "decreasing"
    else:
        direction = "stable"

    logger.debug("Detected velocity trend", direction=direction, slope=slope)
    return TrendDirection(direction=direction, slope=round(slope, 4))

def analyze_velocity_trends(velocity_data: List[Dict[str, Any]]) -> VelocityTrends:
    """Analyzes team velocity trends from historical daily scrum data."""
    if not velocity_data:
        return VelocityTrends(
            current_team_velocity=0.0,
            historical_range=[0.0, 0.0],
            trend_direction="stable",
            confidence=0.0,
            pattern_note="No velocity data available."
        )

    # Assuming velocity_data is a list of dicts, each with a 'completed_tasks' or similar metric
    # For simplicity, let's assume each entry represents a sprint's completed tasks.
    completed_tasks_per_sprint = [entry.get("completed_tasks", 0) for entry in velocity_data]

    if not completed_tasks_per_sprint:
        return VelocityTrends(
            current_team_velocity=0.0,
            historical_range=[0.0, 0.0],
            trend_direction="stable",
            confidence=0.0,
            pattern_note="No completed tasks data available for velocity analysis."
        )

    current_velocity = completed_tasks_per_sprint[-1] if completed_tasks_per_sprint else 0.0
    historical_range = [min(completed_tasks_per_sprint), max(completed_tasks_per_sprint)]

    trend = detect_trend_direction(completed_tasks_per_sprint)

    # Simple confidence based on data points and trend strength
    confidence = min(len(completed_tasks_per_sprint) / 10.0, 1.0) * (1 - abs(trend.slope)) # Example

    pattern_note = f"Velocity trend is {trend.direction}."

    logger.info("Analyzed velocity trends", current_velocity=current_velocity, trend=trend.direction)

    return VelocityTrends(
        current_team_velocity=round(float(current_velocity), 2),
        historical_range=[round(float(r), 2) for r in historical_range],
        trend_direction=trend.direction,
        confidence=round(confidence, 2),
        pattern_note=pattern_note
    )

def compare_team_velocity(current_velocity: float, similar_projects: List[SimilarProject]) -> VelocityComparison:
    """Compares current team velocity to that of similar projects."""
    if not similar_projects:
        return VelocityComparison(
            comparison_to_similar_projects="no_similar_projects",
            percentage_difference=0.0
        )

    similar_velocities = [p.completion_rate for p in similar_projects if p.completion_rate is not None]
    if not similar_velocities:
        return VelocityComparison(
            comparison_to_similar_projects="no_similar_projects_velocity_data",
            percentage_difference=0.0
        )

    avg_similar_velocity = np.mean(similar_velocities)

    if avg_similar_velocity == 0:
        comparison = "no_comparison_possible"
        percentage_difference = 0.0
    else:
        percentage_difference = ((current_velocity - avg_similar_velocity) / avg_similar_velocity) * 100
        if percentage_difference > 10: # More than 10% higher
            comparison = "above_average"
        elif percentage_difference < -10: # More than 10% lower
            comparison = "below_average"
        else:
            comparison = "average"

    logger.debug("Compared team velocity", current_velocity=current_velocity, avg_similar_velocity=avg_similar_velocity, comparison=comparison)
    return VelocityComparison(
        comparison_to_similar_projects=comparison,
        percentage_difference=round(percentage_difference, 2)
    )
