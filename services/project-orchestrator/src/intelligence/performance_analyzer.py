from typing import List, Dict, Any, Optional
from collections import Counter
from models import SimilarProject, SprintConfiguration, CompletionPatterns, Anomaly, VelocityTrends # Absolute import
import structlog

logger = structlog.get_logger()

def identify_optimal_sprint_configuration(similar_projects: List[SimilarProject]) -> SprintConfiguration:
    """Identifies optimal sprint configuration (tasks per sprint, duration) from similar projects."""
    if not similar_projects:
        return SprintConfiguration(optimal_tasks_per_sprint=0, recommended_sprint_duration=0)

    # For simplicity, average the values from similar successful projects
    # In a real scenario, this would involve more sophisticated analysis (e.g., clustering, regression)
    successful_projects = [p for p in similar_projects if p.completion_rate > 0.8] # Heuristic for success

    if not successful_projects:
        return SprintConfiguration(optimal_tasks_per_sprint=0, recommended_sprint_duration=0)

    avg_tasks = round(sum([p.team_size * 2 for p in successful_projects]) / len(successful_projects)) # Placeholder: assuming 2 tasks per team member
    avg_duration = round(sum([p.avg_sprint_duration for p in successful_projects]) / len(successful_projects))

    logger.info("Identified optimal sprint configuration", avg_tasks=avg_tasks, avg_duration=avg_duration)
    return SprintConfiguration(
        optimal_tasks_per_sprint=avg_tasks,
        recommended_sprint_duration=avg_duration
    )

def analyze_task_completion_patterns(retrospectives: List[Dict[str, Any]]) -> CompletionPatterns:
    """Analyzes task completion patterns from retrospectives."""
    if not retrospectives:
        return CompletionPatterns(avg_completion_rate=0.0, trend="unknown", factors=[])

    total_tasks = 0
    completed_tasks = 0
    common_factors = []

    for retro in retrospectives:
        tasks_summary = retro.get("tasks_summary", [])
        for task in tasks_summary:
            total_tasks += 1
            if task.get("status") == "close" or task.get("progress_percentage", 0) >= 100:
                completed_tasks += 1
        # Placeholder for extracting factors from what_went_well, what_could_be_improved
        common_factors.append(retro.get("what_went_well", ""))

    avg_completion_rate = (completed_tasks / total_tasks) if total_tasks > 0 else 0.0

    # Simple trend detection (e.g., if rate is increasing over last few retrospectives)
    trend = "stable" # Placeholder

    logger.info("Analyzed task completion patterns", avg_completion_rate=avg_completion_rate, trend=trend)
    return CompletionPatterns(
        avg_completion_rate=round(avg_completion_rate, 2),
        trend=trend,
        factors=[item for item, count in Counter(common_factors).most_common(3) if item]
    )

def detect_performance_anomalies(velocity_data: List[Dict[str, Any]]) -> List[Anomaly]:
    """Detects performance anomalies based on velocity data."""
    if len(velocity_data) < 3: # Need at least 3 data points to detect a trend/anomaly
        return []

    # Assuming velocity_data is a list of dicts, each with a 'completed_tasks'
    completed_tasks_per_sprint = [entry.get("completed_tasks", 0) for entry in velocity_data]

    anomalies: List[Anomaly] = []

    # Simple anomaly detection: sudden drops or spikes in velocity
    for i in range(1, len(completed_tasks_per_sprint)):
        current_velocity = completed_tasks_per_sprint[i]
        previous_velocity = completed_tasks_per_sprint[i-1]

        if previous_velocity > 0 and (current_velocity / previous_velocity) < 0.5: # More than 50% drop
            anomalies.append(Anomaly(
                type="velocity_drop",
                description=f"Significant velocity drop from {previous_velocity} to {current_velocity}.",
                sprint_id=velocity_data[i].get("sprint_id"),
                date=velocity_data[i].get("end_date")
            ))
        elif previous_velocity > 0 and (current_velocity / previous_velocity) > 1.5: # More than 50% spike
            anomalies.append(Anomaly(
                type="velocity_spike",
                description=f"Significant velocity spike from {previous_velocity} to {current_velocity}.",
                sprint_id=velocity_data[i].get("sprint_id"),
                date=velocity_data[i].get("end_date")
            ))

    logger.info("Detected performance anomalies", count=len(anomalies))
    return anomalies
