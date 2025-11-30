"""
Enhanced Decision Engine v2 with Episode Storage & Retrieval Integration

This version integrates the episode logging and retrieval capabilities from CR_Agent_04_02
to provide learning-based decision making for the project orchestrator.
"""

from typing import List, Dict, Any, Optional, Callable
import structlog
import time
from datetime import datetime
from uuid import uuid4

from intelligence.chronicle_analytics_client import ChronicleAnalyticsClient
from intelligence.cache_manager import CacheManager
from intelligence.data_quality_validator import DataQualityValidator
from intelligence.historical_logger import HistoricalLogger
from intelligence.pattern_engine import PatternEngine
from intelligence.performance_monitor import PerformanceMonitor, PerformanceMetrics
from intelligence.resource_monitor import ResourceMonitor
from intelligence.decision_modifier import DecisionModifier, Adjustment, TaskAdjustment, DurationAdjustment, SimilarProject, VelocityTrends
from intelligence.confidence_gate import ConfidenceGate
from intelligence.decision_auditor import DecisionAuditor, AuditRecord
from config_loader import get_config
from models import ProjectData, Decision, EnhancedDecision, AnalysisResult, RiskAssessment, SprintPrediction, PatternAnalysis, ConfidenceScore, RuleBasedDecision, ConfidenceScores, IntelligenceAdjustmentDetail
from intelligence.decision_config import DecisionConfig
from k8s_client import KubernetesClient

# New imports for episode integration
from memory.models import Episode
from services.episode_logger import EpisodeLogger
from services.episode_retriever import EpisodeRetriever
from services.memory_bridge import MemoryBridge
from memory.agent_memory_store import AgentMemoryStore
from memory.embedding_client import EmbeddingClient
from validators.episode_validator import EpisodeValidator
from config.feature_flags import FeatureFlags
from model_package.decision_context import EpisodeBasedDecisionContext
from intelligence.pattern_combiner import PatternCombinationResult

# AI Agent Advisory import
from services.ollama_advisor import OllamaAdvisor

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
        elif current_active_sprint_data and hasattr(current_active_sprint_data, 'sprint_id'):
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
        sprint_id: Optional[str] = None
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
                    sprint_id = active_sprint_id
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
            sprint_id=sprint_id
        )

class EnhancedDecisionEngineV2(DecisionEngine):
    """
    Enhanced Decision Engine with Episode Storage & Retrieval Integration.
    
    This version extends the original decision engine with learning capabilities:
    - Episodes are logged for every orchestration decision
    - Historical episodes inform future decisions
    - Learning mode can override rule-based decisions
    """
    
    def __init__(
        self, 
        chronicle_analytics_client: ChronicleAnalyticsClient, 
        k8s_client: KubernetesClient, 
        full_config: Dict[str, Any], 
        performance_monitor: PerformanceMonitor, 
        decision_auditor: DecisionAuditor,
        memory_store: Optional[AgentMemoryStore] = None,
        embedding_client: Optional[EmbeddingClient] = None,
        knowledge_store=None
    ):
        super().__init__(k8s_client=k8s_client)
        self.total_performance_monitor = performance_monitor
        self.decision_config = DecisionConfig(**full_config.get("intelligence", {}).get("decision_enhancement", {}))
        
        # Initialize Strategy Repository for Strategy Evolution Layer
        self.strategy_repository = None
        if knowledge_store:
            from services.strategy.strategy_repository import StrategyRepository
            self.strategy_repository = StrategyRepository(knowledge_store)
        
        self.pattern_engine = PatternEngine(
            chronicle_analytics_client, 
            self.decision_config, 
            performance_monitor=self.total_performance_monitor,
            strategy_repository=self.strategy_repository
        )
        self.data_quality_validator = DataQualityValidator()
        self.historical_logger = HistoricalLogger()
        self.chronicle_analytics_client = chronicle_analytics_client
        self.resource_monitor = ResourceMonitor()
        self.decision_modifier = DecisionModifier(self.decision_config)
        self.confidence_gate = ConfidenceGate(performance_monitor=self.total_performance_monitor)
        self.decision_auditor = decision_auditor
        
        # Episode integration components
        self.memory_store = memory_store
        self.embedding_client = embedding_client
        self.feature_flags = FeatureFlags()
        
        # AI Agent Advisor initialization
        self.full_config = full_config
        ai_advisor_config = full_config.get("intelligence", {}).get("ai_agent_advisor", {})
        self.ai_advisor: Optional[OllamaAdvisor] = None
        
        if ai_advisor_config.get("enable_ai_advisor", False):
            try:
                self.ai_advisor = OllamaAdvisor(
                    service_url=ai_advisor_config.get("ollama_service_url", "http://ollama-server.dsm.svc.cluster.local:11434"),
                    model=ai_advisor_config.get("ollama_model", "llama3.2:latest"),
                    timeout=ai_advisor_config.get("ollama_timeout", 5.0)
                )
                logger.info("AI Agent Advisor initialized successfully")
            except Exception as e:
                logger.error("Failed to initialize AI Agent Advisor", error=str(e))
                self.ai_advisor = None
        else:
            logger.info("AI Agent Advisor disabled via configuration")
        
        # Initialize episode services if memory components are available
        self.episode_logger: Optional[EpisodeLogger] = None
        self.episode_retriever: Optional[EpisodeRetriever] = None
        self.episode_validator: Optional[EpisodeValidator] = None
        self.memory_bridge: Optional[MemoryBridge] = None
        
        if self.memory_store and self.embedding_client:
            self.episode_validator = EpisodeValidator(quality_threshold=0.7)
            self.episode_logger = EpisodeLogger(
                memory_store=self.memory_store,
                embedding_client=self.embedding_client,
                validator=self.episode_validator,
                enable_validation=True
            )
            self.episode_retriever = EpisodeRetriever(
                memory_store=self.memory_store,
                embedding_client=self.embedding_client,
                cache_size=100,
                default_timeout=3.0,
                min_similarity=0.7
            )
            
            # Initialize Memory Bridge for episode context translation
            self.memory_bridge = MemoryBridge(
                min_episodes_for_patterns=2,
                min_similarity_threshold=0.6,
                quality_weight=0.3
            )
            
            logger.info("Episode learning system with Memory Bridge initialized successfully")
        else:
            logger.warning("Episode learning system not available - memory components not provided")

    async def make_orchestration_decision(self, project_data: ProjectData, options: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enhanced orchestration decision making with episode learning integration.
        """
        logger.debug("Entering make_orchestration_decision with episode learning", project_id=project_data.project_id)
        
        with self.total_performance_monitor.time_operation("enhanced_orchestration_v2"):
            # Step 1: Gather perception data (context for the episode)
            perception_data = self._gather_perception_data(project_data, options)
            
            # Step 2: Retrieve similar episodes and translate to decision context
            similar_episodes = []
            episode_context: Optional[EpisodeBasedDecisionContext] = None
            
            if self._is_learning_enabled() and self.episode_retriever and self.memory_bridge:
                try:
                    with self.total_performance_monitor.time_operation("episode_retrieval"):
                        similar_episodes = await self.episode_retriever.find_similar_episodes(
                            query_context=perception_data,
                            project_id=project_data.project_id,
                            limit=5,
                            min_quality=0.7
                        )
                    self.total_performance_monitor.increment_episode_retrieval()
                    logger.info(f"Retrieved {len(similar_episodes)} similar episodes for learning", 
                              project_id=project_data.project_id)
                    
                    # Translate episodes to structured decision context using Memory Bridge
                    if similar_episodes:
                        with self.total_performance_monitor.time_operation("memory_bridge_translation"):
                            current_project_context = {
                                "project_id": project_data.project_id,
                                "team_size": project_data.team_size,
                                "backlog_tasks": project_data.backlog_tasks,
                                "unassigned_tasks": project_data.unassigned_tasks
                            }
                            episode_context = await self.memory_bridge.translate_episodes_to_context(
                                episodes=similar_episodes,
                                current_project_context=current_project_context
                            )
                            logger.info(f"Translated episodes to decision context: {episode_context.episodes_used_for_context} relevant episodes", 
                                      project_id=project_data.project_id)
                            
                except Exception as e:
                    logger.error(f"Failed to retrieve and translate episodes: {e}", project_id=project_data.project_id)
            
            # Step 3: Generate base decision using existing logic
            base_decision = await super().make_decision(project_data, options)
            
            # Step 4: Apply learning-based modifications if available
            learning_adjustments = {}
            reasoning_parts = [base_decision.reasoning]
            
            if similar_episodes and self._is_learning_mode_active():
                learning_adjustments = self._apply_episode_learning(
                    base_decision, similar_episodes, reasoning_parts
                )
            
            # Step 5: Perform hybrid pattern analysis (Chronicle + Episodes)
            pattern_analysis = PatternAnalysis()
            pattern_combination_result: Optional[PatternCombinationResult] = None
            intelligence_warnings = []
            historical_data_for_logging = {}
            insights_summary = ""
            confidence_score = 0.0

            try:
                # Initialize strategy recommendations variable
                strategy_recommendations = {}
                
                # Use strategy-enhanced pattern analysis if strategy repository is available
                if self.strategy_repository:
                    with self.total_performance_monitor.time_operation("strategy_enhanced_pattern_analysis"):
                        pattern_analysis, pattern_combination_result, strategy_recommendations = await self.pattern_engine.analyze_strategy_enhanced_patterns(
                            project_id=project_data.project_id, 
                            project_data=project_data,
                            episode_context=episode_context
                        )
                    self.total_performance_monitor.increment_intelligence_invocations()
                    
                    # Generate strategy-enhanced insights summary
                    insights_summary = self.pattern_engine.generate_strategy_enhanced_insights_summary(
                        enhanced_analysis=pattern_analysis,
                        combination_result=pattern_combination_result,
                        strategy_recommendations=strategy_recommendations,
                        episode_context=episode_context
                    )
                    
                    # Validate hybrid pattern confidence (strategies enhance confidence)
                    confidence_score_obj = self.pattern_engine.validate_hybrid_pattern_confidence(
                        enhanced_analysis=pattern_analysis,
                        combination_result=pattern_combination_result
                    )
                    confidence_score = confidence_score_obj.score
                    
                    logger.info(f"Strategy-enhanced pattern analysis complete: {confidence_score:.2f} confidence, "
                              f"{len(strategy_recommendations.get('applicable_strategies', []))} strategies", 
                              project_id=project_data.project_id)
                    
                # Use hybrid pattern analysis if episode context available, otherwise Chronicle-only
                elif episode_context:
                    with self.total_performance_monitor.time_operation("hybrid_pattern_analysis"):
                        pattern_analysis, pattern_combination_result = await self.pattern_engine.analyze_hybrid_patterns(
                            project_id=project_data.project_id, 
                            project_data=project_data,
                            episode_context=episode_context
                        )
                    self.total_performance_monitor.increment_intelligence_invocations()
                    self.total_performance_monitor.increment_hybrid_analysis()
                    
                    # Generate hybrid insights summary
                    insights_summary = self.pattern_engine.generate_hybrid_insights_summary(
                        enhanced_analysis=pattern_analysis,
                        combination_result=pattern_combination_result,
                        episode_context=episode_context
                    )
                    
                    # Validate hybrid pattern confidence  
                    confidence_score_obj = self.pattern_engine.validate_hybrid_pattern_confidence(
                        enhanced_analysis=pattern_analysis,
                        combination_result=pattern_combination_result
                    )
                    confidence_score = confidence_score_obj.score
                    
                    logger.info(f"Hybrid pattern analysis complete: {confidence_score:.2f} confidence", 
                              project_id=project_data.project_id)
                else:
                    # Fallback to Chronicle-only analysis
                    with self.total_performance_monitor.time_operation("pattern_analysis"):
                        pattern_analysis = await self.pattern_engine.analyze_project_patterns(project_data.project_id, project_data)
                    self.total_performance_monitor.increment_intelligence_invocations()
                    insights_summary = self.pattern_engine.generate_insights_summary(pattern_analysis)
                    confidence_score_obj = self.pattern_engine.validate_pattern_confidence(pattern_analysis)
                    confidence_score = confidence_score_obj.score
                    
                    logger.info(f"Chronicle-only pattern analysis complete: {confidence_score:.2f} confidence", 
                              project_id=project_data.project_id)

                # Prepare historical data for logging
                historical_data_for_logging = {"pattern_analysis": pattern_analysis.dict()}
                if pattern_combination_result:
                    historical_data_for_logging["pattern_combination"] = {
                        "combined_patterns_count": len(pattern_combination_result.combined_patterns),
                        "overall_confidence": pattern_combination_result.overall_confidence,
                        "pattern_source_influence": pattern_combination_result.pattern_source_influence
                    }
                if episode_context:
                    historical_data_for_logging["episode_context"] = {
                        "episodes_analyzed": episode_context.similar_episodes_analyzed,
                        "episodes_used": episode_context.episodes_used_for_context,
                        "average_similarity": episode_context.average_episode_similarity
                    }
                
                data_quality_report = await self.chronicle_analytics_client.validate_data_availability(project_data.project_id)
                historical_data_for_logging["data_quality_report"] = data_quality_report.dict()

                self.historical_logger.log_decision_with_historical_context(
                    project_data.project_id, base_decision.model_dump(exclude_none=False), historical_data_for_logging
                )

            except Exception as e:
                logger.error("Failed to retrieve historical intelligence or perform hybrid pattern analysis", 
                           project_id=project_data.project_id, error=str(e), exc_info=True)
                intelligence_warnings.append(f"Hybrid intelligence unavailable: {e}")

            # Step 6: Apply hybrid intelligence adjustments (prioritize hybrid over traditional)
            proposed_adjustments: List[Adjustment] = []
            validated_adjustments: List[Adjustment] = []
            final_tasks_to_assign = learning_adjustments.get('tasks_to_assign', base_decision.tasks_to_assign)
            final_sprint_duration_weeks = learning_adjustments.get('sprint_duration_weeks', base_decision.sprint_duration_weeks)

            evidence_details_for_audit = None

            with self.total_performance_monitor.time_operation("hybrid_adjustment_generation"):
                # Priority 1: Use hybrid pattern recommendations if available
                if pattern_combination_result and pattern_combination_result.combined_patterns:
                    hybrid_recommendations = self.pattern_engine.pattern_combiner.get_recommended_values(pattern_combination_result)
                    
                    # Generate hybrid task count adjustment
                    if ("recommended_task_count" in hybrid_recommendations and 
                        abs(hybrid_recommendations["recommended_task_count"] - base_decision.tasks_to_assign) > 1):
                        
                        # Create evidence details for hybrid adjustment
                        hybrid_evidence = {
                            "hybrid_intelligence": True,
                            "episode_influence": pattern_combination_result.pattern_source_influence.get("episode", 0.0),
                            "chronicle_influence": pattern_combination_result.pattern_source_influence.get("chronicle", 0.0),
                            "combined_patterns_count": len(pattern_combination_result.combined_patterns),
                            "overall_confidence": pattern_combination_result.overall_confidence
                        }
                        
                        task_pattern = next((p for p in pattern_combination_result.combined_patterns 
                                           if p.pattern_type == "task_count"), None)
                        
                        if task_pattern:
                            hybrid_task_adj = TaskAdjustment(
                                original_recommendation=base_decision.tasks_to_assign,
                                intelligence_recommendation=hybrid_recommendations["recommended_task_count"],
                                applied_value=hybrid_recommendations["recommended_task_count"],
                                confidence=task_pattern.confidence,
                                evidence_source=f"Hybrid intelligence: {task_pattern.total_evidence_count} combined evidence sources",
                                rationale=(
                                    f"Hybrid analysis combining episode memory and Chronicle data recommends "
                                    f"{hybrid_recommendations['recommended_task_count']} tasks "
                                    f"(success rate: {task_pattern.success_rate:.1%}, confidence: {task_pattern.confidence:.1%})"
                                ),
                                expected_improvement=f"Expected success rate improvement based on hybrid evidence",
                                evidence_details=hybrid_evidence
                            )
                            proposed_adjustments.append(hybrid_task_adj)
                    
                    # Generate hybrid sprint duration adjustment
                    if ("recommended_sprint_duration_weeks" in hybrid_recommendations and 
                        hybrid_recommendations["recommended_sprint_duration_weeks"] != base_decision.sprint_duration_weeks):
                        
                        duration_pattern = next((p for p in pattern_combination_result.combined_patterns 
                                               if p.pattern_type == "sprint_duration"), None)
                        
                        if duration_pattern:
                            hybrid_duration_adj = DurationAdjustment(
                                original_recommendation=base_decision.sprint_duration_weeks,
                                intelligence_recommendation=hybrid_recommendations["recommended_sprint_duration_weeks"],
                                applied_value=hybrid_recommendations["recommended_sprint_duration_weeks"],
                                confidence=duration_pattern.confidence,
                                evidence_source=f"Hybrid intelligence: {duration_pattern.total_evidence_count} combined evidence sources",
                                rationale=(
                                    f"Hybrid analysis recommends {hybrid_recommendations['recommended_sprint_duration_weeks']}-week sprint "
                                    f"(success rate: {duration_pattern.success_rate:.1%}, confidence: {duration_pattern.confidence:.1%})"
                                ),
                                evidence_details=hybrid_evidence
                            )
                            proposed_adjustments.append(hybrid_duration_adj)
                
                # Priority 2: Fallback to traditional Chronicle-only adjustments if no hybrid recommendations
                if not proposed_adjustments:
                    if pattern_analysis.similar_projects:
                        task_adj = self.decision_modifier.generate_task_count_adjustment(
                            base_task_count=base_decision.tasks_to_assign,
                            similar_projects=pattern_analysis.similar_projects,
                            evidence_details=evidence_details_for_audit
                        )
                        if task_adj:
                            proposed_adjustments.append(task_adj)

                    if pattern_analysis.velocity_trends:
                        duration_adj = self.decision_modifier.generate_sprint_duration_adjustment(
                            base_duration=base_decision.sprint_duration_weeks,
                            velocity_trends=pattern_analysis.velocity_trends,
                            evidence_details=evidence_details_for_audit
                        )
                        if duration_adj:
                            proposed_adjustments.append(duration_adj)

            with self.total_performance_monitor.time_operation("intelligence_confidence_gating"):
                validated_adjustments = self.confidence_gate.filter_low_confidence_adjustments(
                    proposed_adjustments,
                    confidence_threshold=self.decision_config.confidence_threshold,
                    min_projects_for_task_adjustment=self.decision_config.min_similar_projects,
                    max_adjustment_percent=self.decision_config.max_task_adjustment_percent
                )

            # Step 7: Finalize decision with all adjustments
            intelligence_adjustments_detail = {}
            modifications_applied_count = 0
            decision_mode = self._get_decision_mode()

            if decision_mode in ["intelligence_enhanced", "learning_enhanced"] and (validated_adjustments or learning_adjustments):
                # Apply traditional intelligence adjustments
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
                            evidence_details=adj.evidence_details
                        )
                        reasoning_parts.append(f"Intelligence override: {adj.rationale} Applied intelligence adjustment for task count.")
                        modifications_applied_count += 1
                        self.total_performance_monitor.increment_adjustments_applied()
                    elif isinstance(adj, DurationAdjustment) and self.decision_config.enable_sprint_duration_adjustment:
                        final_sprint_duration_weeks = adj.intelligence_recommendation
                        intelligence_adjustments_detail["sprint_duration_modification"] = IntelligenceAdjustmentDetail(
                            original_recommendation=adj.original_recommendation,
                            intelligence_recommendation=adj.intelligence_recommendation,
                            applied_value=adj.applied_value,
                            confidence=adj.confidence,
                            evidence_source=adj.evidence_source,
                            rationale=adj.rationale,
                            evidence_details=adj.evidence_details
                        )
                        reasoning_parts.append(f"Intelligence override: {adj.rationale} Applied intelligence adjustment for sprint duration.")
                        modifications_applied_count += 1
                        self.total_performance_monitor.increment_adjustments_applied()

                # Add learning-based adjustments to reasoning
                if learning_adjustments:
                    if 'learning_rationale' in learning_adjustments:
                        reasoning_parts.append(f"Learning-based adjustment: {learning_adjustments['learning_rationale']}")
                    modifications_applied_count += len([k for k in learning_adjustments.keys() if k.endswith('_to_assign') or k.endswith('_weeks')])

                enhanced_reasoning = "; ".join(reasoning_parts)
                decision_source = decision_mode
            else:
                enhanced_reasoning = base_decision.reasoning
                if insights_summary:
                    enhanced_reasoning += f" Historical insights: {insights_summary}."
                decision_source = "rule_based_only"

            # Step 8: Create final decision object
            final_enhanced_decision_obj = self._create_enhanced_decision(
                base_decision, final_tasks_to_assign, final_sprint_duration_weeks,
                enhanced_reasoning, intelligence_warnings, decision_source,
                intelligence_adjustments_detail, confidence_score
            )

            # Step 9: Log episode for future learning and strategy performance
            if self._is_episode_logging_enabled() and self.episode_logger:
                episode_id = await self._log_decision_episode(
                    project_data, perception_data, reasoning_parts, 
                    final_enhanced_decision_obj, similar_episodes
                )
                
                # Log strategy performance if strategies were applied
                if self.strategy_repository and strategy_recommendations.get('applicable_strategies'):
                    await self._log_strategy_performance(
                        project_data.project_id,
                        episode_id,
                        strategy_recommendations,
                        final_enhanced_decision_obj
                    )

            # Step 10: Continue with existing audit and response logic
            # Extract similar_projects_used before pattern_analysis is converted to dict
            evidence_details_for_audit = None
            if pattern_analysis.similar_projects:
                similar_projects_used = [p.project_id for p in pattern_analysis.similar_projects]
                if similar_projects_used:
                    evidence_details_for_audit = {"similar_projects_used": similar_projects_used}

            await self._perform_decision_audit(
                project_data, base_decision, proposed_adjustments,
                intelligence_adjustments_detail, final_enhanced_decision_obj,
                pattern_analysis, evidence_details_for_audit # Pass evidence_details_for_audit
            )

            # Step 11: Generate AI Agent Advisory (non-blocking)
            ai_advisory = None
            if self.ai_advisor:
                try:
                    with self.total_performance_monitor.time_operation("ai_advisory_generation"):
                        decision_dict = final_enhanced_decision_obj.model_dump(exclude_none=False)
                        analysis_dict = {
                            "team_members_count": project_data.team_size,
                            "unassigned_tasks": project_data.unassigned_tasks,
                            "active_sprints_count": project_data.active_sprints,
                            "backlog_tasks": project_data.backlog_tasks
                        }
                        ai_advisory = await self.ai_advisor.review_decision(
                            project_id=project_data.project_id,
                            decision=decision_dict,
                            analysis=analysis_dict
                        )
                        logger.info("AI advisory generated", 
                                   project_id=project_data.project_id,
                                   generation_time_ms=ai_advisory.generation_time_ms)
                except Exception as e:
                    logger.error("AI advisory generation failed, continuing without advisory",
                               project_id=project_data.project_id,
                               error=str(e))
                    ai_advisory = None

            # Step 12: Build final response
            response = self._build_orchestration_response(
                project_data, final_enhanced_decision_obj, pattern_analysis,
                insights_summary, historical_data_for_logging, modifications_applied_count,
                similar_episodes, episode_context, pattern_combination_result, 
                evidence_details_for_audit, ai_advisory # Pass AI advisory
            )

            logger.debug("Exiting make_orchestration_decision with episode learning", project_id=project_data.project_id)
            return response

    def _gather_perception_data(self, project_data: ProjectData, options: Dict[str, Any]) -> Dict[str, Any]:
        """Gather context data for episode perception."""
        return {
            'project_data': {
                'project_id': project_data.project_id,
                'backlog_tasks': project_data.backlog_tasks,
                'unassigned_tasks': project_data.unassigned_tasks,
                'active_sprints': project_data.active_sprints,
                'team_size': project_data.team_size
            },
            'team_availability': project_data.team_availability,
            'current_sprint_status': project_data.current_active_sprint,
            'backlog_summary': {
                'total_tasks': project_data.backlog_tasks,
                'unassigned': project_data.unassigned_tasks
            },
            'options': options
        }

    def _is_learning_enabled(self) -> bool:
        """Check if episode learning is enabled."""
        return (
            self.feature_flags.ENABLE_ASYNC_LEARNING and 
            self.episode_retriever is not None
        )

    def _is_learning_mode_active(self) -> bool:
        """Check if learning mode should override rule-based decisions."""
        return (
            self.feature_flags.ENABLE_STRATEGY_EVOLUTION and
            self.decision_config.mode in ["learning_enhanced", "intelligence_enhanced"]
        )

    def _is_episode_logging_enabled(self) -> bool:
        """Check if episode logging is enabled."""
        return (
            self.feature_flags.ENABLE_ASYNC_LEARNING and
            self.episode_logger is not None
        )

    def _get_decision_mode(self) -> str:
        """Determine current decision mode based on configuration and learning status."""
        if self._is_learning_mode_active():
            return "learning_enhanced"
        elif self.decision_config.mode == "intelligence_enhanced":
            return "intelligence_enhanced"
        else:
            return "rule_based_only"

    def _apply_episode_learning(
        self, 
        base_decision: Decision, 
        similar_episodes: List[Episode],
        reasoning_parts: List[str]
    ) -> Dict[str, Any]:
        """Apply learning from similar episodes to adjust the base decision."""
        learning_adjustments = {}
        
        if not similar_episodes:
            return learning_adjustments

        # Analyze successful episodes for patterns
        successful_episodes = [ep for ep in similar_episodes if ep.outcome and ep.outcome.get('success', False)]
        
        if successful_episodes:
            # Calculate average task assignment from successful similar episodes
            successful_task_counts = []
            for episode in successful_episodes:
                if episode.action and 'tasks_assigned' in episode.action:
                    task_data = episode.action['tasks_assigned']
                    if isinstance(task_data, int):
                        successful_task_counts.append(task_data)
                    elif isinstance(task_data, dict) and 'count' in task_data:
                        successful_task_counts.append(task_data['count'])

            if successful_task_counts:
                avg_successful_tasks = sum(successful_task_counts) / len(successful_task_counts)
                
                # Apply learning if the average is significantly different
                if abs(avg_successful_tasks - base_decision.tasks_to_assign) > 2:
                    learning_adjustments['tasks_to_assign'] = int(avg_successful_tasks)
                    learning_adjustments['learning_rationale'] = (
                        f"Based on {len(successful_episodes)} similar successful episodes, "
                        f"adjusting task count from {base_decision.tasks_to_assign} to {int(avg_successful_tasks)}"
                    )
                    logger.info(
                        f"Applied learning-based task adjustment: {base_decision.tasks_to_assign} -> {int(avg_successful_tasks)}",
                        project_id=base_decision.project_id if hasattr(base_decision, 'project_id') else 'unknown'
                    )

        return learning_adjustments

    async def _log_decision_episode(
        self,
        project_data: ProjectData,
        perception_data: Dict[str, Any],
        reasoning_parts: List[str],
        final_decision: EnhancedDecision,
        similar_episodes: List[Episode]
    ) -> str:
        """Log the current decision as an episode for future learning."""
        try:
            # Create episode from decision
            episode = Episode(
                episode_id=uuid4(),
                project_id=project_data.project_id,
                timestamp=datetime.utcnow(),
                perception=perception_data,
                reasoning={
                    'analysis_performed': True,
                    'decision_rationale': "; ".join(reasoning_parts),
                    'confidence_scores': {
                        'overall': final_decision.confidence_scores.overall_decision_confidence if final_decision.confidence_scores else 0.5
                    },
                    'patterns_identified': {
                        'similar_episodes_count': len(similar_episodes),
                        'learning_applied': bool(similar_episodes)
                    }
                },
                action={
                    'sprint_created': final_decision.create_new_sprint,
                    'tasks_assigned': final_decision.tasks_to_assign,
                    'cronjob_created': final_decision.cronjob_created,
                    'adjustments_made': final_decision.intelligence_adjustments or {},
                    'success': True  # Initially assume success, will be updated with outcome
                },
                agent_version="2.0.0",  # v2 for episode-enabled version
                control_mode=final_decision.decision_source,
                decision_source=final_decision.decision_source,
                sprint_id=final_decision.sprint_name
            )

            # Log episode asynchronously
            await self.episode_logger.log_episode_async(episode)
            logger.info(f"Decision episode logged successfully", project_id=project_data.project_id, episode_id=str(episode.episode_id))
            
            return str(episode.episode_id)

        except Exception as e:
            logger.error(f"Failed to log decision episode: {e}", project_id=project_data.project_id, exc_info=True)
            return None

    async def _log_strategy_performance(
        self,
        project_id: str,
        episode_id: str,
        strategy_recommendations: Dict[str, Any],
        final_decision: EnhancedDecision
    ) -> None:
        """Log strategy performance for learning optimization."""
        try:
            applicable_strategies = strategy_recommendations.get('applicable_strategies', [])
            
            for strategy_info in applicable_strategies:
                # Build predicted outcome based on strategy
                predicted_outcome = {
                    'expected_quality': strategy_info.get('confidence', 0.5),
                    'expected_success_rate': strategy_info.get('success_rate', 0.5),
                    'strategy_application': True,
                    'decision_adjustments': {
                        'tasks_to_assign': final_decision.tasks_to_assign,
                        'sprint_duration_weeks': getattr(final_decision, 'sprint_duration_weeks', 2),
                        'create_new_sprint': final_decision.create_new_sprint
                    }
                }
                
                # Build actual outcome (will be updated later with real outcomes)
                actual_outcome = {
                    'decision_implemented': True,
                    'tasks_assigned': final_decision.tasks_to_assign,
                    'sprint_created': final_decision.create_new_sprint,
                    'intelligence_adjustments': final_decision.intelligence_adjustments or {},
                    'confidence_scores': final_decision.confidence_scores.dict() if final_decision.confidence_scores else {}
                }
                
                # Log strategy performance
                await self.strategy_repository.log_strategy_performance(
                    strategy_id=strategy_info['strategy_id'],
                    episode_id=episode_id,
                    project_id=project_id,
                    predicted_outcome=predicted_outcome,
                    actual_outcome=actual_outcome,
                    outcome_quality=None,  # Will be updated when actual outcomes are available
                    strategy_confidence=strategy_info['confidence'],
                    context_similarity=strategy_info.get('applicability_score', 0.5)
                )
                
                logger.debug(f"Logged strategy performance for strategy {strategy_info['strategy_id']}", 
                           project_id=project_id, episode_id=episode_id)
                
            logger.info(f"Logged performance for {len(applicable_strategies)} strategies", 
                       project_id=project_id, episode_id=episode_id)
                       
        except Exception as e:
            logger.error(f"Failed to log strategy performance: {e}", 
                        project_id=project_id, episode_id=episode_id, exc_info=True)

    def _create_enhanced_decision(
        self,
        base_decision: Decision,
        final_tasks_to_assign: int,
        final_sprint_duration_weeks: int,
        enhanced_reasoning: str,
        intelligence_warnings: List[str],
        decision_source: str,
        intelligence_adjustments_detail: Dict[str, Any],
        confidence_score: float
    ) -> EnhancedDecision:
        """Create enhanced decision object."""
        rule_based_decision_obj = RuleBasedDecision(
            tasks_to_assign=base_decision.tasks_to_assign,
            sprint_duration_weeks=base_decision.sprint_duration_weeks,
            reasoning=base_decision.reasoning
        )

        confidence_scores_obj = ConfidenceScores(
            overall_decision_confidence=confidence_score,
            intelligence_threshold_met=bool(intelligence_adjustments_detail),
            minimum_threshold=self.decision_config.confidence_threshold
        )

        return EnhancedDecision(
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
            intelligence_metadata={
                "decision_mode": decision_source,
                "learning_enabled": self._is_learning_enabled(),
                "episode_logging_enabled": self._is_episode_logging_enabled()
            },
            sprint_name=base_decision.sprint_name,
            sprint_id=base_decision.sprint_id
        )

    async def _perform_decision_audit(
        self,
        project_data: ProjectData,
        base_decision: Decision,
        proposed_adjustments: List[Adjustment],
        intelligence_adjustments_detail: Dict[str, Any],
        final_enhanced_decision_obj: EnhancedDecision,
        pattern_analysis: PatternAnalysis,
        evidence_details_for_audit: Optional[Dict[str, Any]] = None # New argument
    ) -> None:
        """Perform decision audit logging."""
        rule_based_decision_obj = RuleBasedDecision(
            tasks_to_assign=base_decision.tasks_to_assign,
            sprint_duration_weeks=base_decision.sprint_duration_weeks,
            reasoning=base_decision.reasoning
        )

        audit_record = self.decision_auditor.create_audit_record(
            project_id=project_data.project_id,
            base_decision=rule_based_decision_obj,
            intelligence_recommendations=proposed_adjustments,
            applied_adjustments=intelligence_adjustments_detail,
            final_decision=final_enhanced_decision_obj,
            evidence_details=evidence_details_for_audit
        )
        await self.decision_auditor.log_decision_to_chronicle(audit_record, sprint_id=final_enhanced_decision_obj.sprint_id)

    def _build_orchestration_response(
        self,
        project_data: ProjectData,
        final_enhanced_decision_obj: EnhancedDecision,
        pattern_analysis: PatternAnalysis,
        insights_summary: str,
        historical_data_for_logging: Dict[str, Any],
        modifications_applied_count: int,
        similar_episodes: List[Episode],
        episode_context: Optional[EpisodeBasedDecisionContext] = None,
        pattern_combination_result: Optional[PatternCombinationResult] = None,
        evidence_details_for_audit: Optional[Dict[str, Any]] = None,
        ai_advisory = None # AI advisory response
    ) -> Dict[str, Any]:
        """Build final orchestration response."""
        # Enhanced intelligence metadata with hybrid capabilities
        intelligence_metadata = {
            "decision_mode": final_enhanced_decision_obj.decision_source,
            "modifications_applied": modifications_applied_count,
            "fallback_available": True,
            "similar_projects_analyzed": len(pattern_analysis.similar_projects),
            "historical_data_quality": historical_data_for_logging.get("data_quality_report", {}).get("overall_quality", "unknown"),
            "prediction_confidence": final_enhanced_decision_obj.confidence_scores.overall_decision_confidence if final_enhanced_decision_obj.confidence_scores else 0.0,
            "intelligence_threshold_met": bool(final_enhanced_decision_obj.intelligence_adjustments),
            "minimum_threshold": self.decision_config.confidence_threshold,
            
            # Hybrid intelligence capabilities
            "hybrid_analysis": {
                "enabled": episode_context is not None,
                "pattern_combination_used": pattern_combination_result is not None,
                "episode_context_available": episode_context is not None,
                "memory_bridge_available": self.memory_bridge is not None
            },
            
            # Episode learning metadata
            "episode_learning": {
                "episodes_retrieved": len(similar_episodes),
                "learning_enabled": self._is_learning_enabled(),
                "episode_logging_enabled": self._is_episode_logging_enabled(),
                "decision_mode": self._get_decision_mode(),
                "episodes_used_for_context": episode_context.episodes_used_for_context if episode_context else 0,
                "average_episode_similarity": episode_context.average_episode_similarity if episode_context else 0.0
            },
            
            # Pattern combination details
            "pattern_combination": {
                "hybrid_patterns_generated": len(pattern_combination_result.combined_patterns) if pattern_combination_result else 0,
                "overall_confidence": pattern_combination_result.overall_confidence if pattern_combination_result else 0.0,
                "episode_influence": pattern_combination_result.pattern_source_influence.get("episode", 0.0) if pattern_combination_result else 0.0,
                "chronicle_influence": pattern_combination_result.pattern_source_influence.get("chronicle", 0.0) if pattern_combination_result else 0.0,
                "combined_pattern_types": [p.pattern_type for p in pattern_combination_result.combined_patterns] if pattern_combination_result else []
            },
            
            # System capabilities
            "system_capabilities": {
                "hybrid_intelligence": self.memory_bridge is not None,
                "episode_memory": self.episode_retriever is not None,
                "chronicle_analytics": True,
                "pattern_combination": self.pattern_engine.pattern_combiner is not None,
                "confidence_gating": True
            }
        }

        return {
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
                    "data_quality_report": historical_data_for_logging.get("data_quality_report"),
                    "episode_learning": {
                        "similar_episodes_found": len(similar_episodes),
                        "learning_applied": len(similar_episodes) > 0
                    }
                }
            ).dict(),
            "decisions": final_enhanced_decision_obj.model_dump(exclude_none=False),
            "actions_taken": [],
            "cronjob_name": None,
            "sprint_id": final_enhanced_decision_obj.sprint_id,
            "performance_metrics": {
                "pattern_analysis": pattern_analysis.performance_metrics,
                "total_orchestration": self.total_performance_monitor.get_summary("enhanced_orchestration_v2"),
                "resource_usage": self.resource_monitor.get_resource_usage(),
                "performance_threshold_met": self._check_performance_thresholds(),
                "ai_advisory": self.total_performance_monitor.get_summary("ai_advisory_generation") if ai_advisory else None
            },
            "intelligence_metadata": intelligence_metadata,
            "ai_agent_advisory": ai_advisory.to_dict() if ai_advisory else None
        }

    def _check_performance_thresholds(self) -> Dict:
        """Check performance thresholds for decision engine."""
        orchestration_summary = self.total_performance_monitor.get_summary("enhanced_orchestration_v2")
        pattern_summary = self.pattern_engine.get_performance_summary("full_pattern_analysis")
        resource_usage = self.resource_monitor.get_resource_usage()
        
        memory_threshold_met = self.resource_monitor.check_memory_threshold(max_increase_mb=100)

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
        """Get project intelligence including episode-based insights."""
        pattern_analysis = PatternAnalysis()
        insights_summary = ""
        confidence_score = 0.0

        try:
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

        # Add episode-based insights if available
        episode_insights = {}
        if self.episode_retriever:
            try:
                recent_episodes = await self.episode_retriever.get_episodes_by_project(
                    project_id=project_id, limit=10, min_quality=0.5
                )
                episode_insights = {
                    "total_episodes": len(recent_episodes),
                    "recent_decisions": [
                        {
                            "timestamp": ep.timestamp.isoformat(),
                            "decision_source": ep.decision_source,
                            "has_outcome": ep.outcome is not None
                        }
                        for ep in recent_episodes[:5]
                    ]
                }
            except Exception as e:
                logger.error(f"Failed to retrieve episode insights: {e}", project_id=project_id)
                episode_insights = {"error": str(e)}

        data_quality_report = await self.chronicle_analytics_client.validate_data_availability(project_id)

        return {
            "project_id": project_id,
            "historical_context": {
                "pattern_analysis": pattern_analysis.dict(),
                "insights_summary": insights_summary,
                "data_quality_report": data_quality_report.dict(),
                "episode_insights": episode_insights
            },
            "intelligence_metadata": {
                "similar_projects_analyzed": len(pattern_analysis.similar_projects),
                "prediction_confidence": confidence_score,
                "data_freshness_hours": 0,
                "learning_enabled": self._is_learning_enabled(),
                "episode_logging_enabled": self._is_episode_logging_enabled()
            }
        }