from typing import List, Dict, Any, Optional, Callable # Added Callable
import structlog

from intelligence.chronicle_analytics_client import ChronicleAnalyticsClient # Corrected imports
from intelligence.cache_manager import CacheManager
from intelligence.data_quality_validator import DataQualityValidator
from intelligence.historical_logger import HistoricalLogger
from intelligence.pattern_engine import PatternEngine # New import
from intelligence.performance_monitor import PerformanceMonitor, PerformanceMetrics # New import
from intelligence.resource_monitor import ResourceMonitor # New import
from intelligence.decision_modifier import DecisionModifier, Adjustment, TaskAdjustment, DurationAdjustment, SimilarProject, VelocityTrends
from intelligence.confidence_gate import ConfidenceGate
from intelligence.decision_auditor import DecisionAuditor, AuditRecord # New import
from config_loader import get_config # Updated import
from models import ProjectData, Decision, EnhancedDecision, AnalysisResult, RiskAssessment, SprintPrediction, PatternAnalysis, ConfidenceScore, RuleBasedDecision, ConfidenceScores, IntelligenceAdjustmentDetail # Updated models
from intelligence.decision_config import DecisionConfig # New import
import time # New import

from k8s_client import KubernetesClient # New import

logger = structlog.get_logger()

class DecisionEngine:
    """Base class for orchestration decision making."""
    def __init__(self, k8s_client: KubernetesClient):
        self.k8s_client = k8s_client

    async def make_decision(self, project_data: ProjectData, options: Dict[str, Any]) -> Decision:
        logger.info("Making orchestration decisions", project_id=project_data.project_id, options=options)

        project_id = project_data.project_id
        unassigned_tasks = project_data.unassigned_tasks
        has_active_sprint = project_data.active_sprints > 0
        current_active_sprint_data = project_data.current_active_sprint if hasattr(project_data, 'current_active_sprint') else None
        active_sprint_id = None
        if current_active_sprint_data and isinstance(current_active_sprint_data, dict) and "sprint_id" in current_active_sprint_data:
            active_sprint_id = current_active_sprint_data["sprint_id"]
        elif current_active_sprint_data and hasattr(current_active_sprint_data, 'sprint_id'): # For Pydantic models
            active_sprint_id = current_active_sprint_data.sprint_id
        team_size = project_data.team_size
        team_availability = project_data.team_availability
        sprint_tasks_summary = project_data.sprint_tasks_summary

        create_new_sprint = False
        tasks_to_assign = 0
        cronjob_created = False
        sprint_closure_triggered = False
        cronjob_deleted = False
        sprint_name = None
        sprint_id: Optional[str] = None # Initialize sprint_id
        sprint_id_to_close: Optional[str] = None
        reasoning = []
        warnings = []

        if team_availability.get("status") == "conflict":
            conflicts = team_availability.get("conflicts", [])
            if conflicts:
                reasoning.append(f"Note: Sprint timeline includes {len(conflicts)} holiday(s) or PTO day(s).")
                for conflict in conflicts:
                    warnings.append(
                        f"Sprint timeline includes upcoming holiday: {conflict.get('name')} on {conflict.get('date')}"
                    )

        is_sprint_active_after_current_decisions = has_active_sprint

        if has_active_sprint:
            logger.info("Active sprint found for project", project_id=project_id, sprint_id=active_sprint_id)
            cronjob_name = None
            if active_sprint_id:
                cronjob_name = f"run-dailyscrum-{project_id.lower()}-{active_sprint_id.lower()}"
            
            if cronjob_name:
                cronjob_exists = await self.k8s_client.check_cronjob_exists(namespace="dsm", name=cronjob_name)
            else:
                cronjob_exists = False

            logger.debug("DEBUG: sprint_tasks_summary type and content before condition", type=type(sprint_tasks_summary), content=sprint_tasks_summary)
            if sprint_tasks_summary and sprint_tasks_summary.get("pending_tasks") == 0:
                sprint_closure_triggered = True
                sprint_id_to_close = active_sprint_id
            else:
                if not cronjob_exists:
                    logger.warn("CronJob for active sprint is missing. Recreating.", project_id=project_id, sprint_id=active_sprint_id, cronjob_name=cronjob_name)
                    cronjob_created = True
                    sprint_name = active_sprint_id
                    sprint_id = active_sprint_id # Set sprint_id here
                    reasoning.append(f"Active sprint {active_sprint_id} found, but its corresponding CronJob was missing. Recreating the CronJob to ensure process continuity.")
                else:
                    logger.info("CronJob for active sprint already exists.", project_id=project_id, sprint_id=active_sprint_id, cronjob_name=cronjob_name)
                    reasoning.append(f"Active sprint {active_sprint_id} found with an existing CronJob. No action needed.")

        if not is_sprint_active_after_current_decisions and options.get("create_sprint_if_needed") and unassigned_tasks > 0:
            create_new_sprint = True
            reasoning.append("No active sprint found and unassigned tasks exist.")
            
            sprint_count = project_data.active_sprints
            next_sprint_number = sprint_count + 1
            sprint_name = f"{project_id}-S{next_sprint_number:02d}"
            reasoning.append(f"Proposing to create new sprint: {sprint_name}.")

            max_tasks_per_sprint = options.get("max_tasks_per_sprint", 10)
            tasks_to_assign = min(unassigned_tasks, max_tasks_per_sprint)
            reasoning.append(f"Proposing to assign {tasks_to_assign} tasks.")

            if options.get("create_cronjob"):
                cronjob_created = True
                reasoning.append("New sprint creation triggers CronJob generation.")

        return Decision(
            create_new_sprint=create_new_sprint,
            tasks_to_assign=tasks_to_assign,
            cronjob_created=cronjob_created,
            sprint_closure_triggered=sprint_closure_triggered,
            cronjob_deleted=cronjob_deleted,
            sprint_name=sprint_name,
            sprint_id_to_close=sprint_id_to_close,
            reasoning="; ".join(reasoning) if reasoning else "No specific actions required based on current state and options.",
            warnings=warnings,
            sprint_id=sprint_id # Pass the local sprint_id to the Decision object
        )

class EnhancedDecisionEngine(DecisionEngine):
    def __init__(self, chronicle_analytics_client: ChronicleAnalyticsClient, k8s_client: KubernetesClient, full_config: Dict[str, Any], performance_monitor: PerformanceMonitor, decision_auditor: DecisionAuditor):
        super().__init__(k8s_client=k8s_client)
        self.total_performance_monitor = performance_monitor # Use injected instance
        self.decision_config = DecisionConfig(**full_config.get("intelligence", {}).get("decision_enhancement", {})) # Initialize decision_config first
        self.pattern_engine = PatternEngine(chronicle_analytics_client, self.decision_config, performance_monitor=self.total_performance_monitor)
        self.data_quality_validator = DataQualityValidator()
        self.historical_logger = HistoricalLogger()
        self.chronicle_analytics_client = chronicle_analytics_client
        self.resource_monitor = ResourceMonitor()
        self.decision_modifier = DecisionModifier(self.decision_config)
        self.confidence_gate = ConfidenceGate(performance_monitor=self.total_performance_monitor)
        self.decision_auditor = decision_auditor # Use injected instance

    async def make_orchestration_decision(self, project_data: ProjectData, options: Dict[str, Any]) -> Dict[str, Any]:
        logger.debug("Entering make_orchestration_decision", project_id=project_data.project_id)
        with self.total_performance_monitor.time_operation("enhanced_orchestration"):
            logger.debug("Inside enhanced_orchestration time_operation block", project_id=project_data.project_id)
            base_decision = await super().make_decision(project_data, options)

            pattern_analysis = PatternAnalysis() # Initialize with default empty object
            intelligence_warnings = []
            historical_data_for_logging = {}
            insights_summary = ""
            confidence_score = 0.0

            try:
                # Perform pattern analysis
                with self.total_performance_monitor.time_operation("pattern_analysis"):
                    pattern_analysis = await self.pattern_engine.analyze_project_patterns(project_data.project_id, project_data)
                self.total_performance_monitor.increment_intelligence_invocations() # Increment after intelligence pipeline invoked
                insights_summary = self.pattern_engine.generate_insights_summary(pattern_analysis)
                confidence_score_obj = self.pattern_engine.validate_pattern_confidence(pattern_analysis)
                confidence_score = confidence_score_obj.score

                # Collect historical data for logging and quality assessment
                historical_data_for_logging = {
                    "pattern_analysis": pattern_analysis.dict(),
                }
                
                # Assess data quality
                data_quality_report = await self.chronicle_analytics_client.validate_data_availability(project_data.project_id)
                historical_data_for_logging["data_quality_report"] = data_quality_report.dict()

                # Log decision with historical context
                self.historical_logger.log_decision_with_historical_context(
                    project_data.project_id, base_decision.model_dump(exclude_none=False), historical_data_for_logging
                )

            except Exception as e:
                logger.error("Failed to retrieve historical intelligence or perform pattern analysis", project_id=project_data.project_id, error=str(e), exc_info=True)
                intelligence_warnings.append(f"Historical intelligence unavailable: {e}")

            # Initialize for intelligence-driven adjustments
            proposed_adjustments: List[Adjustment] = []
            validated_adjustments: List[Adjustment] = []
            final_tasks_to_assign = base_decision.tasks_to_assign
            final_sprint_duration_weeks = base_decision.sprint_duration_weeks

            evidence_details_for_audit = None # Initialize here

            logger.debug("Base decision tasks to assign", tasks=base_decision.tasks_to_assign)
            logger.debug("Pattern analysis similar projects", similar_projects=pattern_analysis.similar_projects)

            with self.total_performance_monitor.time_operation("intelligence_adjustment_generation"):
                # Attempt to generate task count adjustment
                if pattern_analysis.similar_projects:
                    task_adj = self.decision_modifier.generate_task_count_adjustment(
                        base_task_count=base_decision.tasks_to_assign,
                        similar_projects=pattern_analysis.similar_projects,
                        evidence_details=evidence_details_for_audit
                    )
                    if task_adj:
                        proposed_adjustments.append(task_adj)

                # Attempt to generate sprint duration adjustment
                if pattern_analysis.velocity_trends:
                    duration_adj = self.decision_modifier.generate_sprint_duration_adjustment(
                        base_duration=base_decision.sprint_duration_weeks,
                        velocity_trends=pattern_analysis.velocity_trends,
                        evidence_details=evidence_details_for_audit
                    )
                    if duration_adj:
                        proposed_adjustments.append(duration_adj)
            logger.debug("Proposed adjustments", adjustments=proposed_adjustments)

            with self.total_performance_monitor.time_operation("intelligence_confidence_gating"):
                # Apply confidence gating to proposed adjustments
                validated_adjustments = self.confidence_gate.filter_low_confidence_adjustments(
                    proposed_adjustments,
                    confidence_threshold=self.decision_config.confidence_threshold,
                    min_projects_for_task_adjustment=self.decision_config.min_similar_projects,
                    max_adjustment_percent=self.decision_config.max_task_adjustment_percent
                )
            logger.debug("Validated adjustments", adjustments=validated_adjustments)

            # Apply approved adjustments to the final decision
            intelligence_adjustments_detail = {}
            modifications_applied_count = 0
            decision_mode = self.decision_config.mode
            
            final_decision_reasoning_parts = [base_decision.reasoning]

            if decision_mode == "intelligence_enhanced" and validated_adjustments:
                for adj in validated_adjustments:
                    if isinstance(adj, TaskAdjustment) and self.decision_config.enable_task_count_adjustment:
                        final_tasks_to_assign = adj.intelligence_recommendation
                        intelligence_adjustments_detail["task_count_modification"] = IntelligenceAdjustmentDetail(
                            original_recommendation=adj.original_recommendation,
                            intelligence_recommendation=adj.intelligence_recommendation,
                            applied_value=adj.applied_value,
                            confidence=adj.confidence,
                            evidence_source=adj.evidence_source,
                            expected_improvement=adj.expected_improvement,
                            rationale=adj.rationale,
                            evidence_details=adj.evidence_details # Pass evidence_details
                        )
                        final_decision_reasoning_parts.append(
                            f"Intelligence override: {adj.rationale} Applied intelligence adjustment for task count."
                        )
                        modifications_applied_count += 1
                        self.total_performance_monitor.increment_adjustments_applied() # Increment if adjustment applied
                    elif isinstance(adj, DurationAdjustment) and self.decision_config.enable_sprint_duration_adjustment:
                        final_sprint_duration_weeks = adj.intelligence_recommendation
                        intelligence_adjustments_detail["sprint_duration_modification"] = IntelligenceAdjustmentDetail(
                            original_recommendation=adj.original_recommendation,
                            intelligence_recommendation=adj.intelligence_recommendation,
                            applied_value=adj.applied_value,
                            confidence=adj.confidence,
                            evidence_source=adj.evidence_source,
                            rationale=adj.rationale,
                            evidence_details=adj.evidence_details # Pass evidence_details
                        )
                        final_decision_reasoning_parts.append(
                            f"Intelligence override: {adj.rationale} Applied intelligence adjustment for sprint duration."
                        )
                        modifications_applied_count += 1
                        self.total_performance_monitor.increment_adjustments_applied() # Increment if adjustment applied
                
                enhanced_reasoning = "; ".join(final_decision_reasoning_parts)
                decision_source = "intelligence_enhanced"
            else:
                enhanced_reasoning = base_decision.reasoning
                if insights_summary:
                    enhanced_reasoning += f" Historical insights: {insights_summary}."
                decision_source = "rule_based_only"

            # Record adjustment application rate
            self.total_performance_monitor.record_metric(
                PerformanceMetrics(
                    operation_name="adjustment_application_rate",
                    start_time=time.time(),
                    end_time=time.time(),
                    duration_ms=0.0,
                    success=True,
                    error_message=None,
                    metadata={"modifications_applied": modifications_applied_count}
                )
            )


            intelligence_metadata = {
                "decision_mode": decision_mode,
                "modifications_applied": modifications_applied_count,
                "fallback_available": True, # Always true as rule-based is the fallback
                "similar_projects_analyzed": len(pattern_analysis.similar_projects),
                "historical_data_quality": historical_data_for_logging.get("data_quality_report", {}).get("overall_quality", "unknown"),
                "prediction_confidence": confidence_score,
                "intelligence_threshold_met": bool(validated_adjustments),
                "minimum_threshold": self.decision_config.confidence_threshold
            }

            # Create RuleBasedDecision object for audit
            rule_based_decision_obj = RuleBasedDecision(
                tasks_to_assign=base_decision.tasks_to_assign,
                sprint_duration_weeks=base_decision.sprint_duration_weeks,
                reasoning=base_decision.reasoning
            )

            # Create ConfidenceScores object for audit
            confidence_scores_obj = ConfidenceScores(
                overall_decision_confidence=confidence_score,
                intelligence_threshold_met=intelligence_metadata["intelligence_threshold_met"],
                minimum_threshold=intelligence_metadata["minimum_threshold"]
            )

            # Create EnhancedDecision object for audit
            final_enhanced_decision_obj = EnhancedDecision(
                create_new_sprint=base_decision.create_new_sprint,
                tasks_to_assign=final_tasks_to_assign,
                sprint_duration_weeks=final_sprint_duration_weeks,
                cronjob_created=base_decision.cronjob_created,
                sprint_closure_triggered=base_decision.sprint_closure_triggered,
                sprint_id_to_close=base_decision.sprint_id_to_close,
                reasoning=enhanced_reasoning,
                warnings=base_decision.warnings + intelligence_warnings,
                decision_source=decision_source,
                rule_based_decision=rule_based_decision_obj,
                intelligence_adjustments=intelligence_adjustments_detail,
                confidence_scores=confidence_scores_obj,
                intelligence_metadata=intelligence_metadata,
                sprint_name=base_decision.sprint_name,
                sprint_id=base_decision.sprint_id
            )

            # Log decision to Chronicle
            evidence_details_for_audit = None
            if pattern_analysis.similar_projects:
                similar_projects_used = [p.project_id for p in pattern_analysis.similar_projects]
                if similar_projects_used:
                    evidence_details_for_audit = {"similar_projects_used": similar_projects_used}

            audit_record = self.decision_auditor.create_audit_record(
                project_id=project_data.project_id,
                base_decision=rule_based_decision_obj,
                intelligence_recommendations=proposed_adjustments, # Log all proposed, not just validated
                applied_adjustments=intelligence_adjustments_detail,
                final_decision=final_enhanced_decision_obj,
                evidence_details=evidence_details_for_audit
            )
            await self.decision_auditor.log_decision_to_chronicle(audit_record, sprint_id=final_enhanced_decision_obj.sprint_id)

            full_orchestration_response = {
                "project_id": project_data.project_id,
                "analysis": AnalysisResult(
                    backlog_tasks=project_data.backlog_tasks,
                    unassigned_tasks=project_data.unassigned_tasks,
                    active_sprints=project_data.active_sprints,
                    team_size=project_data.team_size,
                    team_availability=project_data.team_availability,
                    historical_context={
                        "pattern_analysis": pattern_analysis.dict(),
                        "insights_summary": insights_summary,
                        "data_quality_report": historical_data_for_logging.get("data_quality_report")
                    }
                ).dict(),
                "decisions": final_enhanced_decision_obj.model_dump(exclude_none=False),
                "actions_taken": base_decision.actions_taken if hasattr(base_decision, 'actions_taken') else [],
                "cronjob_name": base_decision.cronjob_name if hasattr(base_decision, 'cronjob_name') else None,
                "sprint_id": base_decision.sprint_id if hasattr(base_decision, 'sprint_id') else None,
                "performance_metrics": {
                    "pattern_analysis": pattern_analysis.performance_metrics,
                    "total_orchestration": self.total_performance_monitor.get_summary("enhanced_orchestration"),
                    "resource_usage": self.resource_monitor.get_resource_usage(),
                    "performance_threshold_met": self._check_performance_thresholds()
                },
                "intelligence_metadata": intelligence_metadata
            }
            logger.debug("EnhancedDecisionEngine: Full orchestration response before return", response=full_orchestration_response)
            if base_decision.sprint_closure_triggered and base_decision.sprint_id_to_close:
                full_orchestration_response["decisions"]["sprint_id_to_close"] = base_decision.sprint_id_to_close
            logger.debug("Exiting make_orchestration_decision", project_id=project_data.project_id)
            return full_orchestration_response

    def _check_performance_thresholds(self) -> Dict:
        orchestration_summary = self.total_performance_monitor.get_summary("enhanced_orchestration")
        pattern_summary = self.pattern_engine.get_performance_summary("full_pattern_analysis")
        resource_usage = self.resource_monitor.get_resource_usage()
        
        memory_threshold_met = self.resource_monitor.check_memory_threshold(max_increase_mb=100) # Assuming 100MB as threshold

        return {
            "total_under_2000ms": orchestration_summary.get("avg_duration_ms", 0) < 2000,
            "pattern_analysis_under_1000ms": pattern_summary.get("avg_duration_ms", 0) < 1000,
            "memory_increase_under_100mb": memory_threshold_met,
            "thresholds_met": (
                orchestration_summary.get("avg_duration_ms", 0) < 2000 and
                pattern_summary.get("avg_duration_ms", 0) < 1000 and
                memory_threshold_met
            )
        }

    async def get_project_intelligence(self, project_id: str) -> Dict[str, Any]:
        pattern_analysis = PatternAnalysis()
        insights_summary = ""
        confidence_score = 0.0

        try:
            # Perform pattern analysis
            dummy_project_data = ProjectData(
                project_id=project_id,
                backlog_tasks=0, unassigned_tasks=0, active_sprints=0, team_size=0, team_availability={}
            )
            pattern_analysis = await self.pattern_engine.analyze_project_patterns(project_id, dummy_project_data)
            insights_summary = self.pattern_engine.generate_insights_summary(pattern_analysis)
            confidence_score_obj = self.pattern_engine.validate_pattern_confidence(pattern_analysis)
            confidence_score = confidence_score_obj.score
        except Exception as e:
            logger.error("Failed to retrieve historical intelligence for insights endpoint", project_id=project_id, error=str(e), exc_info=True)
            insights_summary = f"Historical intelligence unavailable: {e}"

        data_quality_report = await self.chronicle_analytics_client.validate_data_availability(project_id)

        return {
            "project_id": project_id,
            "historical_context": {
                "pattern_analysis": pattern_analysis.dict(),
                "insights_summary": insights_summary,
                "data_quality_report": data_quality_report.dict()
            },
            "intelligence_metadata": {
                "similar_projects_analyzed": len(pattern_analysis.similar_projects),
                "prediction_confidence": confidence_score,
                "data_freshness_hours": 0
            }
        }
