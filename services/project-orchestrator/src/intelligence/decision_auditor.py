from typing import List, Dict, Any, Optional
from datetime import datetime, date
import uuid
import structlog
from pydantic import BaseModel, Field

# Define minimal Pydantic models to avoid circular dependency with app.py
class TaskReport(BaseModel):
    id: str
    yesterday_work: Optional[str] = None
    today_work: Optional[str] = None
    impediments: Optional[str] = None
    created_at: datetime

class EmployeeReport(BaseModel):
    employee_id: Optional[str] = Field(None, alias='assigned_to')
    tasks: List[TaskReport]

    class Config:
        populate_by_name = True

class SummaryMetrics(BaseModel):
    total_team_members: int
    total_tasks: int
    completed_tasks: int
    pending_tasks: int

class DailyScrumReportNote(BaseModel):
    project_id: str
    sprint_id: Optional[str] = None
    report_date: Optional[date] = None
    summary: Optional[str] = None
    summary_metrics: Optional[SummaryMetrics] = None
    reports: Dict[str, List[EmployeeReport]]
    orchestration_decision_details: Optional[Dict[str, Any]] = None

    class Config:
        arbitrary_types_allowed = True


from models import Decision, EnhancedDecision, RuleBasedDecision, IntelligenceAdjustmentDetail, ConfidenceScores
from .decision_modifier import Adjustment
from service_clients import ChronicleServiceClient

logger = structlog.get_logger()

class AuditRecord(BaseModel):
    audit_id: str
    project_id: str
    timestamp: str
    base_decision: RuleBasedDecision
    final_decision: EnhancedDecision
    combined_reasoning: str
    intelligence_recommendations: List[Adjustment] = Field(default_factory=list)
    applied_adjustments: Dict[str, IntelligenceAdjustmentDetail] = Field(default_factory=dict)
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

class DecisionAuditor:
    def __init__(self, chronicle_service_client: ChronicleServiceClient):
        self.chronicle_service_client = chronicle_service_client

    def create_audit_record(self,
                            project_id: str,
                            base_decision: RuleBasedDecision,
                            intelligence_recommendations: List[Adjustment],
                            applied_adjustments: Dict[str, IntelligenceAdjustmentDetail],
                            final_decision: EnhancedDecision,
                            evidence_details: Optional[Dict[str, Any]] = None) -> AuditRecord:
        """
        Creates a comprehensive audit record for an orchestration decision.
        """
        # Update applied_adjustments with evidence_details if provided
        if evidence_details:
            for adj_type, adj_detail in applied_adjustments.items():
                adj_detail.evidence_details = evidence_details

        combined_reasoning = self.generate_decision_reasoning(
            base_decision, intelligence_recommendations, applied_adjustments, final_decision
        )

        return AuditRecord(
            audit_id=str(uuid.uuid4()),
            project_id=project_id,
            timestamp=datetime.utcnow().isoformat(),
            base_decision=base_decision,
            intelligence_recommendations=intelligence_recommendations,
            applied_adjustments=applied_adjustments,
            final_decision=final_decision,
            combined_reasoning=combined_reasoning
        )

    async def log_decision_to_chronicle(self, audit_record: AuditRecord, sprint_id: Optional[str] = None) -> str:
        """
        Logs the decision audit record to the Chronicle Service as part of a DailyScrumReportNote.
        Returns a confirmation message or ID from Chronicle.
        """
        try:
            # Prepare orchestration_decision_details for direct logging
            payload_dict = {
                "audit_id": audit_record.audit_id,
                "project_id": audit_record.project_id,
                "timestamp": audit_record.timestamp,
                "base_decision": audit_record.base_decision.model_dump(exclude_none=True),
                "intelligence_recommendations": [adj.model_dump(exclude_none=True) for adj in audit_record.intelligence_recommendations],
                "applied_adjustments": {k: v.model_dump(exclude_none=True) for k, v in audit_record.applied_adjustments.items()},
                "final_decision": audit_record.final_decision.model_dump(exclude_none=True),
                "combined_reasoning": audit_record.combined_reasoning,
                "correlation_id": audit_record.correlation_id,
                "sprint_id": sprint_id # Include sprint_id directly in the audit record
            }

            response = await self.chronicle_service_client.record_decision_audit(payload_dict)
            logger.info("Decision audit logged to Chronicle", audit_id=audit_record.audit_id, project_id=audit_record.project_id, response=response)
            return f"Audit record {audit_record.audit_id} logged to Chronicle."
        except Exception as e:
            logger.error("Failed to log decision audit to Chronicle", audit_id=audit_record.audit_id, error=str(e), exc_info=True)
            return f"Failed to log audit record {audit_record.audit_id} to Chronicle: {e}"

    def generate_decision_reasoning(self,
                                    base_decision: RuleBasedDecision,
                                    intelligence_recommendations: List[Adjustment],
                                    applied_adjustments: Dict[str, IntelligenceAdjustmentDetail],
                                    final_decision: EnhancedDecision) -> str:
        """
        Generates a comprehensive reasoning string for the final decision.
        """
        reasoning_parts = [f"Rule-based decision: {base_decision.reasoning}"]

        if intelligence_recommendations:
            for rec in intelligence_recommendations:
                reasoning_parts.append(f"Intelligence proposed: {rec.rationale} (Confidence: {rec.confidence:.2f})")

        if applied_adjustments:
            for adj_type, adj_detail in applied_adjustments.items():
                reasoning_parts.append(
                    f"Applied intelligence adjustment for {adj_type.replace('_modification', '').replace('_', ' ')}: "
                    f"Original: {adj_detail.original_recommendation}, "
                    f"Intelligent: {adj_detail.intelligence_recommendation}. "
                    f"Reason: {adj_detail.rationale} (Confidence: {adj_detail.confidence:.2f}). "
                    f"Expected improvement: {adj_detail.expected_improvement}"
                )

        reasoning_parts.append(f"Final decision: {final_decision.reasoning}")
        return " ".join(reasoning_parts)