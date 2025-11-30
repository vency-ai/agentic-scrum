from typing import List, Dict, Any, Optional
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import structlog
from pydantic import BaseModel, Field

from intelligence.chronicle_analytics_client import ChronicleAnalyticsClient # Assuming this client exists
from models import EnhancedDecision, RuleBasedDecision, IntelligenceAdjustmentDetail # For type hinting

logger = structlog.get_logger()

class ProjectOutcome(BaseModel):
    project_id: str
    sprint_id: str
    completion_rate: float
    actual_duration_weeks: int
    actual_task_count: int
    resource_utilization: float
    success: bool
    notes: str = ""

class TimeRange(BaseModel):
    start_date: datetime
    end_date: datetime

class EffectivenessReport(BaseModel):
    time_period: TimeRange
    total_decisions_analyzed: int
    intelligence_enhanced_decisions: int
    rule_based_decisions: int
    intelligence_completion_rate_avg: float
    rule_based_completion_rate_avg: float
    completion_rate_improvement_percent: float
    task_efficiency_improvement_percent: float
    resource_utilization_improvement_percent: float
    details: List[Dict[str, Any]] = Field(default_factory=list)

class ImprovementMetrics(BaseModel):
    completion_rate_delta: float
    task_efficiency_delta: float
    resource_utilization_delta: float
    statistical_significance: Dict[str, Any] = Field(default_factory=dict)


class DecisionTracker:
    def __init__(self, chronicle_analytics_client: ChronicleAnalyticsClient, project_id: str):
        self.chronicle_analytics_client = chronicle_analytics_client
        self.project_id = project_id

    async def track_decision_outcome(self, decision_id: str, project_outcome: ProjectOutcome) -> None:
        """
        Logs the outcome of a project/sprint associated with a decision to Chronicle.
        This would typically be called by a separate process or a post-sprint hook.
        """
        try:
            outcome_data = {
                "decision_id": decision_id,
                "project_id": project_outcome.project_id,
                "sprint_id": project_outcome.sprint_id,
                "completion_rate": project_outcome.completion_rate,
                "actual_duration_weeks": project_outcome.actual_duration_weeks,
                "actual_task_count": project_outcome.actual_task_count,
                "resource_utilization": project_outcome.resource_utilization,
                "success": project_outcome.success,
                "notes": project_outcome.notes,
                "timestamp": datetime.utcnow().isoformat(),
                "event_type": "orchestration_outcome_tracking"
            }
            response = await self.chronicle_analytics_client.log_event(
                project_id=project_outcome.project_id,
                event_type="orchestration_outcome_tracking",
                event_data=outcome_data
            )
            logger.info("Project outcome logged to Chronicle", decision_id=decision_id, project_id=project_outcome.project_id, response=response)
        except Exception as e:
            logger.error("Failed to log project outcome to Chronicle", decision_id=decision_id, error=str(e), exc_info=True)

    async def _fetch_decisions_and_outcomes(self, project_id: str, time_period: TimeRange) -> List[Dict[str, Any]]:
        """
        Fetches historical decision audit records and their associated outcomes from Chronicle
        using the dedicated analytics endpoint.
        """
        logger.info("Fetching decisions and outcomes from Chronicle for analysis", project_id=project_id, time_period=time_period)

        report = await self.chronicle_analytics_client.get_decision_impact_report(
            project_id=project_id,
            start_date=time_period.start_date,
            end_date=time_period.end_date
        )

        if not report or not report.details:
            return []

        # Transform the report details into the format expected by compare_decision_effectiveness
        transformed_data = []
        for detail in report.details:
            transformed_data.append({
                "audit_id": detail.audit_id,
                "project_id": detail.project_id,
                "timestamp": detail.timestamp.isoformat(),
                "final_decision": {"decision_source": detail.decision_source},
                "outcome": {
                    "completion_rate": detail.completion_rate,
                    "success": detail.success
                }
            })
        return transformed_data


    async def compare_decision_effectiveness(self, project_id: str, time_period: TimeRange) -> EffectivenessReport:
        """
        Compares the effectiveness of intelligence-enhanced decisions vs. rule-based decisions.
        """
        decisions_and_outcomes = await self._fetch_decisions_and_outcomes(project_id, time_period)

        intelligence_decisions = []
        rule_based_decisions = []

        for record in decisions_and_outcomes:
            if record["final_decision"]["decision_source"] == "intelligence_enhanced":
                intelligence_decisions.append(record)
            else:
                rule_based_decisions.append(record)

        total_decisions_analyzed = len(decisions_and_outcomes)
        intelligence_enhanced_count = len(intelligence_decisions)
        rule_based_count = len(rule_based_decisions)

        intelligence_completion_rates = [d["outcome"]["completion_rate"] for d in intelligence_decisions if "outcome" in d]
        rule_based_completion_rates = [d["outcome"]["completion_rate"] for d in rule_based_decisions if "outcome" in d]

        intelligence_completion_rate_avg = sum(intelligence_completion_rates) / len(intelligence_completion_rates) if intelligence_completion_rates else 0.0
        rule_based_completion_rate_avg = sum(rule_based_completion_rates) / len(rule_based_completion_rates) if rule_based_completion_rates else 0.0

        completion_rate_improvement_percent = 0.0
        if rule_based_completion_rate_avg > 0:
            completion_rate_improvement_percent = ((intelligence_completion_rate_avg - rule_based_completion_rate_avg) / rule_based_completion_rate_avg) * 100

        # Placeholder for task efficiency and resource utilization improvements
        task_efficiency_improvement_percent = 0.0
        resource_utilization_improvement_percent = 0.0

        details = []
        for d in decisions_and_outcomes:
            details.append({
                "project_id": d["project_id"],
                "decision_source": d["final_decision"]["decision_source"],
                "completion_rate": d["outcome"]["completion_rate"] if "outcome" in d else None,
                "success": d["outcome"]["success"] if "outcome" in d else None
            })

        return EffectivenessReport(
            time_period=time_period,
            total_decisions_analyzed=total_decisions_analyzed,
            intelligence_enhanced_decisions=intelligence_enhanced_count,
            rule_based_decisions=rule_based_count,
            intelligence_completion_rate_avg=intelligence_completion_rate_avg,
            rule_based_completion_rate_avg=rule_based_completion_rate_avg,
            completion_rate_improvement_percent=completion_rate_improvement_percent,
            task_efficiency_improvement_percent=task_efficiency_improvement_percent,
            resource_utilization_improvement_percent=resource_utilization_improvement_percent,
            details=details
        )

    def generate_improvement_metrics(self, intelligence_decisions: List[Dict[str, Any]], rule_based_decisions: List[Dict[str, Any]]) -> ImprovementMetrics:
        """
        Generates detailed improvement metrics based on two lists of decision outcomes.
        This is a placeholder for more sophisticated statistical analysis.
        """
        # Simplified calculation for demonstration
        intel_completion_rates = [d["outcome"]["completion_rate"] for d in intelligence_decisions if "outcome" in d]
        rule_completion_rates = [d["outcome"]["completion_rate"] for d in rule_based_decisions if "outcome" in d]

        intel_avg_completion = sum(intel_completion_rates) / len(intel_completion_rates) if intel_completion_rates else 0.0
        rule_avg_completion = sum(rule_completion_rates) / len(rule_completion_rates) if rule_completion_rates else 0.0

        completion_rate_delta = intel_avg_completion - rule_avg_completion

        # Placeholders for other deltas
        task_efficiency_delta = 0.0
        resource_utilization_delta = 0.0

        return ImprovementMetrics(
            completion_rate_delta=completion_rate_delta,
            task_efficiency_delta=task_efficiency_delta,
            resource_utilization_delta=resource_utilization_delta,
            statistical_significance={"note": "Statistical analysis not yet implemented."}
        )
