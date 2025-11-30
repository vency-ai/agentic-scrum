"""
Decision Context Models

Data structures for episode-based decision context used by the
Memory Bridge to translate episode data into actionable insights
for the Enhanced Decision Engine.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID

class EpisodeInsight(BaseModel):
    """Insight extracted from a single episode"""
    episode_id: UUID
    project_id: str
    similarity_score: float = Field(ge=0.0, le=1.0)
    outcome_quality: Optional[float] = Field(None, ge=0.0, le=1.0)
    decision_summary: str
    key_learning: str
    confidence: float = Field(ge=0.0, le=1.0)

class DecisionPattern(BaseModel):
    """Pattern identified across multiple episodes"""
    pattern_type: str  # e.g., "task_count", "sprint_duration", "team_assignment"
    pattern_value: Any  # The recommended value based on episodes
    success_rate: float = Field(ge=0.0, le=1.0)  # Success rate for this pattern
    episode_count: int = Field(ge=0)  # Number of episodes supporting this pattern
    confidence: float = Field(ge=0.0, le=1.0)  # Confidence in this pattern
    
class EpisodeBasedDecisionContext(BaseModel):
    """Complete decision context derived from episodes"""
    
    # Episode Analysis Summary
    similar_episodes_analyzed: int = Field(ge=0)
    episodes_used_for_context: int = Field(ge=0)
    average_episode_similarity: float = Field(ge=0.0, le=1.0)
    context_quality_score: float = Field(ge=0.0, le=1.0)
    
    # Success Metrics
    average_success_rate: Optional[float] = Field(None, ge=0.0, le=1.0)
    success_rate_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    
    # Decision Patterns
    identified_patterns: List[DecisionPattern] = Field(default_factory=list)
    
    # Specific Recommendations
    recommended_task_count: Optional[int] = Field(None, ge=1)
    recommended_sprint_duration_weeks: Optional[int] = Field(None, ge=1, le=8)
    recommended_team_assignments: Optional[Dict[str, Any]] = None
    
    # Confidence Scoring
    overall_recommendation_confidence: float = Field(ge=0.0, le=1.0)
    pattern_confidence_weight: float = Field(ge=0.0, le=1.0)  # Weight vs Chronicle patterns
    
    # Key Insights (Human Readable)
    key_insights: List[str] = Field(default_factory=list)
    success_factors: List[str] = Field(default_factory=list)
    risk_factors: List[str] = Field(default_factory=list)
    
    # Episode References
    contributing_episodes: List[EpisodeInsight] = Field(default_factory=list)
    
    # Metadata
    context_generated_at: datetime = Field(default_factory=datetime.utcnow)
    processing_duration_ms: Optional[float] = None

class EpisodeInfluenceMetadata(BaseModel):
    """Metadata about how episodes influenced final decision"""
    
    episodes_retrieved: int = Field(ge=0)
    episodes_used_for_decision: int = Field(ge=0)
    average_episode_similarity: float = Field(ge=0.0, le=1.0)
    episode_influence_score: float = Field(ge=0.0, le=1.0)  # Overall influence on decision
    
    # Insights derived from episodes
    key_episode_insights: List[str] = Field(default_factory=list)
    
    # Detailed episode references
    episodes_contributing: List[EpisodeInsight] = Field(default_factory=list)
    
    # Performance metrics
    retrieval_duration_ms: Optional[float] = None
    bridge_translation_duration_ms: Optional[float] = None
    
class CombinedPatternContext(BaseModel):
    """Combined context from episodes and Chronicle Service"""
    
    # Episode-based context
    episode_context: Optional[EpisodeBasedDecisionContext] = None
    
    # Chronicle-based context (existing)
    chronicle_patterns: Optional[Dict[str, Any]] = None
    
    # Combined recommendations
    combined_confidence: float = Field(ge=0.0, le=1.0)
    episode_weight: float = Field(ge=0.0, le=1.0)  # Weight given to episode patterns
    chronicle_weight: float = Field(ge=0.0, le=1.0)  # Weight given to Chronicle patterns
    
    # Final integrated insights
    integrated_recommendations: Dict[str, Any] = Field(default_factory=dict)
    evidence_summary: str = ""  # Human-readable summary of evidence