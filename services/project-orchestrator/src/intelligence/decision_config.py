from pydantic import BaseModel, Field
from typing import Optional

class DecisionConfig(BaseModel):
    mode: str = "intelligence_enhanced"  # options: "rule_based_only", "intelligence_enhanced", "hybrid"
    confidence_threshold: float = 0.50  # Lowered from 0.75 for easier intelligence triggering
    max_task_adjustment_percent: float = 0.5
    enable_task_count_adjustment: bool = True
    enable_sprint_duration_adjustment: bool = True
    enable_resource_allocation_adjustment: bool = False
    min_similar_projects: int = 3
    task_adjustment_difference_threshold: int = 1  # Lowered from 2 to trigger with smaller differences
    min_similarity_for_adjustment_proposal: float = 0.3  # Lowered from 0.5
    min_confidence_for_task_proposal: float = 0.3  # Lowered from 0.5
    min_velocity_confidence_for_scoring: float = 0.3  # Lowered from 0.5
    min_velocity_confidence_for_duration_adjustment: float = 0.5  # Lowered from 0.8 to enable duration adjustments
