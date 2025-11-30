from typing import List, Dict, Any, Optional
from collections import Counter
from models import SimilarProject, SuccessIndicators, ProjectData # Absolute import
import structlog

logger = structlog.get_logger()

def extract_lessons_learned(project_retrospectives: List[Dict[str, Any]]) -> List[str]:
    """Extracts lessons learned (action items) from project retrospectives."""
    lessons = []
    for retro in project_retrospectives:
        action_items = retro.get("action_items", [])
        for item in action_items:
            if item.get("status") == "closed": # Assuming closed action items are lessons learned
                lessons.append(item.get("description"))
    return lessons

def identify_success_patterns(similar_projects: List[SimilarProject]) -> SuccessIndicators:
    """Identifies common success patterns from a list of similar projects."""
    if not similar_projects:
        return SuccessIndicators(
            optimal_tasks_per_sprint=0,
            recommended_sprint_duration=0,
            success_probability=0.0,
            risk_factors=[]
        )

    total_completion_rate = 0.0
    total_sprint_duration = 0.0
    total_tasks_per_sprint = 0
    success_count = 0
    all_success_factors = []
    all_risk_factors = [] # Placeholder for now, would need to be extracted from retrospectives

    for project in similar_projects:
        total_completion_rate += project.completion_rate
        total_sprint_duration += project.avg_sprint_duration
        # Assuming optimal_tasks_per_sprint can be derived or is part of SimilarProject
        # For now, using a simple average or a placeholder
        total_tasks_per_sprint += 6 # Placeholder for average tasks per sprint in similar projects
        all_success_factors.extend(project.key_success_factors)

        if project.completion_rate > 0.8: # Simple heuristic for 'successful' project
            success_count += 1

    avg_completion_rate = total_completion_rate / len(similar_projects)
    avg_sprint_duration = round(total_sprint_duration / len(similar_projects))
    avg_tasks_per_sprint = round(total_tasks_per_sprint / len(similar_projects))

    success_probability = success_count / len(similar_projects)

    # Identify most common success factors
    common_success_factors = [item for item, count in Counter(all_success_factors).most_common(3)]

    logger.info("Identified success patterns", avg_completion_rate=avg_completion_rate, success_probability=success_probability)

    return SuccessIndicators(
        optimal_tasks_per_sprint=avg_tasks_per_sprint,
        recommended_sprint_duration=avg_sprint_duration,
        success_probability=round(success_probability, 2),
        risk_factors=all_risk_factors # This needs actual extraction logic
    )

def calculate_success_probability(patterns: SuccessIndicators, current_project: ProjectData) -> float:
    """Calculates the success probability for the current project based on identified patterns."""
    # This is a highly simplified calculation. A real implementation would involve more complex
    # matching of current project characteristics against success patterns.
    logger.debug("Calculating success probability", project_id=current_project.project_id, patterns=patterns.dict())
    return patterns.success_probability
