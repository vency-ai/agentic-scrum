from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import UUID

class Episode(BaseModel):
    """Represents an orchestration episode"""
    episode_id: Optional[UUID] = None
    project_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    perception: Dict[str, Any]
    reasoning: Dict[str, Any]
    action: Dict[str, Any]
    
    outcome: Optional[Dict[str, Any]] = None
    outcome_quality: Optional[float] = None
    outcome_recorded_at: Optional[datetime] = None
    
    agent_version: str = "1.0.0"
    control_mode: str = "rule_based_only"
    decision_source: str = "rule_based_only"
    
    sprint_id: Optional[str] = None
    chronicle_note_id: Optional[UUID] = None
    
    similarity: Optional[float] = None  # For search results
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }
    
    def get_summary(self) -> str:
        """Generate human-readable summary of episode"""
        action_type = "sprint_created" if self.action.get("sprint_created") else "tasks_assigned"
        return f"Episode {self.project_id}: {action_type} at {self.timestamp.isoformat()}"
    
    @classmethod
    def from_db_row(cls, row: Dict[str, Any]) -> "Episode":
        """Create Episode from database row"""
        import json
        
        # Parse JSON fields if they are strings
        def parse_json_field(field_value):
            if isinstance(field_value, str):
                return json.loads(field_value)
            return field_value
        
        return cls(
            episode_id=row["episode_id"],
            project_id=row["project_id"],
            timestamp=row["timestamp"],
            perception=parse_json_field(row["perception"]),
            reasoning=parse_json_field(row["reasoning"]),
            action=parse_json_field(row["action"]),
            outcome=parse_json_field(row.get("outcome")) if row.get("outcome") else None,
            outcome_quality=row.get("outcome_quality"),
            outcome_recorded_at=row.get("outcome_recorded_at"),
            agent_version=row["agent_version"],
            control_mode=row["control_mode"],
            decision_source=row["decision_source"],
            sprint_id=row.get("sprint_id"),
            chronicle_note_id=row.get("chronicle_note_id"),
            similarity=row.get("similarity")
        )

class Strategy(BaseModel):
    """Represents a learned strategy"""
    knowledge_id: Optional[UUID] = None
    knowledge_type: str = "strategy"
    
    content: Dict[str, Any]
    description: str
    
    confidence: float = 0.5
    supporting_episodes: List[UUID] = Field(default_factory=list)
    contradicting_episodes: List[UUID] = Field(default_factory=list)
    
    times_applied: int = 0
    success_count: int = 0
    failure_count: int = 0
    success_rate: Optional[float] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_validated: Optional[datetime] = None
    last_applied: Optional[datetime] = None
    
    created_by: str = "system"
    is_active: bool = True
    
    def applies_to(self, decision: Any) -> bool:
        """Check if strategy applies to given decision context"""
        # Placeholder - implement actual logic based on content
        return True
    
    @classmethod
    def from_db_row(cls, row: Dict[str, Any]) -> "Strategy":
        import json
        
        # Parse JSON fields if they are strings
        def parse_json_field(field_value):
            if isinstance(field_value, str):
                return json.loads(field_value)
            return field_value
        
        return cls(
            knowledge_id=row["knowledge_id"],
            knowledge_type=row["knowledge_type"],
            content=parse_json_field(row["content"]),
            description=row["description"],
            confidence=row["confidence"],
            supporting_episodes=row["supporting_episodes"] or [],
            contradicting_episodes=row.get("contradicting_episodes", []) or [],
            times_applied=row["times_applied"],
            success_count=row["success_count"],
            failure_count=row["failure_count"],
            success_rate=row.get("success_rate"),
            created_at=row["created_at"],
            last_validated=row.get("last_validated"),
            last_applied=row.get("last_applied"),
            created_by=row["created_by"],
            is_active=row["is_active"]
        )

class WorkingMemorySession(BaseModel):
    """Represents a working memory session"""
    session_id: Optional[UUID] = None
    project_id: str
    user_id: Optional[str] = None
    current_goal: Optional[str] = None
    
    active_context: Optional[Dict[str, Any]] = None
    thought_history: List[Dict[str, Any]] = Field(default_factory=list)
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    
    is_active: bool = True
    related_episodes: List[UUID] = Field(default_factory=list)
    
    @classmethod
    def from_db_row(cls, row: Dict[str, Any]) -> "WorkingMemorySession":
        import json
        
        # Parse JSON fields if they are strings
        def parse_json_field(field_value):
            if isinstance(field_value, str):
                return json.loads(field_value)
            return field_value
        
        return cls(
            session_id=row["session_id"],
            project_id=row["project_id"],
            user_id=row.get("user_id"),
            current_goal=row.get("current_goal"),
            active_context=parse_json_field(row["active_context"]) if row.get("active_context") else None,
            thought_history=[parse_json_field(th) for th in (row.get("thought_history") or [])],
            created_at=row["created_at"],
            last_updated=row["last_updated"],
            expires_at=row.get("expires_at"),
            is_active=row["is_active"],
            related_episodes=row.get("related_episodes", []) or []
        )