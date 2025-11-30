from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from dataclasses import dataclass # Keep for now, might be used elsewhere, but not for new models

class Adjustment(BaseModel):
    original_recommendation: Any
    intelligence_recommendation: Any
    applied_value: Any
    confidence: float
    evidence_source: str
    rationale: str = ""
    expected_improvement: str = ""
    evidence_details: Optional[Dict[str, Any]] = None # New field for proposed adjustments

class TaskAdjustment(Adjustment):
    pass

class DurationAdjustment(Adjustment):
    pass

class ProjectData(BaseModel):
    project_id: str
    backlog_tasks: int
    unassigned_tasks: int
    active_sprints: int
    team_size: int
    team_availability: Dict[str, Any]
    current_active_sprint: Optional[Dict[str, Any]] = None
    sprint_tasks_summary: Optional[Dict[str, Any]] = None
    # New fields for pattern recognition
    avg_task_complexity: float = 0.0
    domain_category: str = "general"
    project_duration: float = 0.0

class Decision(BaseModel):
    create_new_sprint: bool
    tasks_to_assign: int
    cronjob_created: bool
    reasoning: str
    warnings: List[str] = Field(default_factory=list)
    sprint_closure_triggered: bool = False
    cronjob_deleted: bool = False
    sprint_name: Optional[str] = None
    sprint_id_to_close: Optional[str] = None
    sprint_id: Optional[str] = None
    sprint_duration_weeks: int = 2 # Default to 2 weeks

class RuleBasedDecision(BaseModel):
    tasks_to_assign: int
    sprint_duration_weeks: int
    reasoning: str

class IntelligenceAdjustmentDetail(BaseModel):
    original_recommendation: Any
    intelligence_recommendation: Any
    applied_value: Any
    confidence: float
    evidence_source: str
    rationale: str = ""
    expected_improvement: str = ""
    evidence_details: Optional[Dict[str, Any]] = None # New field

class ConfidenceScores(BaseModel):
    overall_decision_confidence: float
    intelligence_threshold_met: bool
    minimum_threshold: float

class EnhancedDecision(Decision):
    sprint_duration_weeks: int = 2 # Default to 2 weeks
    decision_source: str = "rule_based_only"
    rule_based_decision: Optional[RuleBasedDecision] = None
    intelligence_adjustments: Dict[str, IntelligenceAdjustmentDetail] = Field(default_factory=dict)
    confidence_scores: Optional[ConfidenceScores] = None
    intelligence_metadata: Dict[str, Any] = Field(default_factory=dict)

    def __init__(self, **data: Any):
        super().__init__(**data)
        import structlog
        logger = structlog.get_logger()
        logger.debug("EnhancedDecision constructor received sprint_id_to_close", sprint_id_to_close=self.sprint_id_to_close)

class AnalysisResult(BaseModel):
    backlog_tasks: int
    unassigned_tasks: int
    active_sprints: int
    team_size: int
    team_availability: Dict[str, Any]
    historical_context: Dict[str, Any] = Field(default_factory=dict)

class RiskAssessment(BaseModel):
    overall_risk: float = 0.0
    sprint_failure_probability: float = 0.0
    capacity_overload_risk: float = 0.18
    confidence: float = 0.0

class SprintPrediction(BaseModel):
    predicted_completion_rate: float = 0.0
    predicted_duration_weeks: float = 0.0
    confidence: float = 0.0

# New models for pattern recognition
class ProjectCharacteristics(BaseModel):
    project_id: str
    team_size: int
    avg_task_complexity: float
    domain_category: str
    project_duration: float

class SimilarProject(BaseModel):
    project_id: str
    similarity_score: float
    team_size: int
    completion_rate: float
    avg_sprint_duration: float
    optimal_task_count: Optional[int] = None # Added optimal_task_count
    key_success_factors: List[str] = Field(default_factory=list)

class VelocityTrends(BaseModel):
    current_team_velocity: float
    historical_range: List[float]
    trend_direction: str
    confidence: float
    pattern_note: str

class SuccessIndicators(BaseModel):
    optimal_tasks_per_sprint: int
    recommended_sprint_duration: int
    success_probability: float
    risk_factors: List[str] = Field(default_factory=list)

class PatternAnalysis(BaseModel):
    similar_projects: List[SimilarProject] = Field(default_factory=list)
    velocity_trends: Optional[VelocityTrends] = None
    success_indicators: Optional[SuccessIndicators] = None
    performance_metrics: Dict[str, Any] = Field(default_factory=dict) # New field

class ConfidenceScore(BaseModel):
    score: float
    reasoning: str

class SprintConfiguration(BaseModel):
    optimal_tasks_per_sprint: int
    recommended_sprint_duration: int

class CompletionPatterns(BaseModel):
    avg_completion_rate: float
    trend: str
    factors: List[str] = Field(default_factory=list)

class Anomaly(BaseModel):
    type: str
    description: str
    sprint_id: Optional[str] = None
    date: Optional[str] = None

class TrendDirection(BaseModel):
    direction: str # e.g., "increasing", "decreasing", "stable"
    slope: float

class VelocityComparison(BaseModel):
    comparison_to_similar_projects: str # e.g., "above_average", "average", "below_average"
    percentage_difference: float