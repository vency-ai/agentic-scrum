from fastapi import APIRouter, HTTPException, status, Depends # Import Depends
import structlog
from datetime import datetime, timedelta
import time # New import
from typing import Dict, List, Literal, Optional # New import for Literal and Optional
from pydantic import BaseModel # New import for BaseModel

from intelligence.chronicle_analytics_client import ChronicleAnalyticsClient
from intelligence.data_quality_validator import DataQualityValidator
from intelligence.decision_auditor import DecisionAuditor # New import
from intelligence.decision_tracker import DecisionTracker, TimeRange, EffectivenessReport # New import
from enhanced_decision_engine_v2 import EnhancedDecisionEngineV2
from models import ProjectData # New import
from config_loader import get_config
from intelligence.pattern_engine import PatternEngine
from intelligence.performance_monitor import PerformanceMonitor # New import

# Import dependency functions from dependencies.py
from dependencies import get_chronicle_analytics_client_dependency, get_decision_engine_dependency, get_performance_monitor_dependency # New import

logger = structlog.get_logger()

class DecisionModeConfig(BaseModel):
    mode: Literal["rule_based_only", "intelligence_enhanced", "hybrid"]
    confidence_threshold: float = 0.75
    enable_task_count_adjustment: bool = True
    enable_sprint_duration_adjustment: bool = True
    enable_resource_allocation_adjustment: bool = False
    min_similar_projects: int = 3

intelligence_router = APIRouter(prefix="/intelligence")

@intelligence_router.get("/project/{project_id}/insights", status_code=status.HTTP_200_OK)
async def get_project_intelligence_insights(
    project_id: str,
    decision_engine: EnhancedDecisionEngineV2 = Depends(get_decision_engine_dependency)
):
    """Detailed historical analysis and predictions without triggering orchestration."""
    logger.info("Project intelligence insights requested", project_id=project_id)
    try:
        insights = await decision_engine.get_project_intelligence(project_id)
        return insights
    except HTTPException as e:
        logger.error("Failed to get project intelligence insights due to HTTP error", project_id=project_id, detail=e.detail, status_code=e.status_code)
        raise e
    except Exception as e:
        logger.error("Failed to get project intelligence insights due to unexpected error", project_id=project_id, error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error getting intelligence insights: {e}")

@intelligence_router.get("/patterns/similar-projects/{project_id}", status_code=status.HTTP_200_OK)
async def get_similar_projects_patterns(
    project_id: str,
    chronicle_analytics_client: ChronicleAnalyticsClient = Depends(get_chronicle_analytics_client_dependency),
    performance_monitor: PerformanceMonitor = Depends(get_performance_monitor_dependency) # Get global instance
):
    """Detailed analysis of projects similar to the specified project."""
    logger.info("Similar projects patterns requested", project_id=project_id)
    try:
        pattern_engine = PatternEngine(chronicle_analytics_client, performance_monitor=performance_monitor) # Pass global instance
        
        # Create a dummy ProjectData for pattern analysis if not performing full orchestration
        dummy_project_data = ProjectData(
            project_id=project_id,
            backlog_tasks=0, unassigned_tasks=0, active_sprints=0, team_size=0, team_availability={},
            avg_task_complexity=0.0, domain_category="general", project_duration=0.0
        )
        pattern_analysis = await pattern_engine.analyze_project_patterns(project_id, dummy_project_data)
        
        if not pattern_analysis.similar_projects:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No similar projects found for {project_id} or insufficient data.")

        return {"project_id": project_id, "similar_projects": [p.dict() for p in pattern_analysis.similar_projects]}
    except HTTPException as e:
        logger.error("Failed to get similar projects patterns due to HTTP error", project_id=project_id, detail=e.detail, status_code=e.status_code)
        raise e
    except Exception as e:
        logger.error("Failed to get similar projects patterns due to unexpected error", project_id=project_id, error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error getting similar projects patterns: {e}")

@intelligence_router.get("/patterns/velocity-trends/{project_id}", status_code=status.HTTP_200_OK)
async def get_velocity_trends_patterns(
    project_id: str,
    chronicle_analytics_client: ChronicleAnalyticsClient = Depends(get_chronicle_analytics_client_dependency),
    performance_monitor: PerformanceMonitor = Depends(get_performance_monitor_dependency), # Get global instance
    decision_engine: EnhancedDecisionEngineV2 = Depends(get_decision_engine_dependency) # New dependency
):
    """Team velocity analysis and trend identification."""
    logger.info("Velocity trends patterns requested", project_id=project_id)
    try:
        pattern_engine = PatternEngine(chronicle_analytics_client, decision_engine.decision_config, performance_monitor=performance_monitor) # Pass decision_config
        
        # Create a dummy ProjectData for pattern analysis if not performing full orchestration
        dummy_project_data = ProjectData(
            project_id=project_id,
            backlog_tasks=0, unassigned_tasks=0, active_sprints=0, team_size=0, team_availability={},
            avg_task_complexity=0.0, domain_category="general", project_duration=0.0
        )
        pattern_analysis = await pattern_engine.analyze_project_patterns(project_id, dummy_project_data)
        
        if not pattern_analysis.velocity_trends:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No velocity trends found for {project_id} or insufficient data.")

        return {"project_id": project_id, "velocity_trends": pattern_analysis.velocity_trends.dict()}
    except HTTPException as e:
        logger.error("Failed to get velocity trends patterns due to HTTP error", project_id=project_id, detail=e.detail, status_code=e.status_code)
        raise e
    except Exception as e:
        logger.error("Failed to get velocity trends patterns due to unexpected error", project_id=project_id, error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error getting velocity trends patterns: {e}")


@intelligence_router.get("/models/health", status_code=status.HTTP_200_OK)
async def get_intelligence_models_health(
    chronicle_analytics_client: ChronicleAnalyticsClient = Depends(get_chronicle_analytics_client_dependency)
):
    """Health check for intelligence components and data freshness."""
    logger.info("Intelligence models health check requested")
    try:
        chronicle_status = "ok"
        try:
            # Attempt to fetch a simple metric to check connectivity, e.g., project patterns for a dummy project
            # Or, a more direct health endpoint if available in Chronicle Service
            await chronicle_analytics_client.get_project_patterns("dummy-project-for-health-check")
        except Exception as e:
            chronicle_status = f"error: {e}"

        # Placeholder for actual model status
        model_status = "healthy"
        
        health_status = {
            "intelligence_status": model_status,
            "cache_health": "ok", # Using global pattern_cache, assuming it's healthy if service is up
            "chronicle_service_connectivity": chronicle_status,
            "data_freshness_hours": 1, # Placeholder
            "model_last_updated": datetime.utcnow().isoformat() + "Z"
        }
        return health_status
    except Exception as e:
        logger.error(f"Error during intelligence models health check: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal Server Error: {e}")

@intelligence_router.get("/data-quality/{project_id}", status_code=status.HTTP_200_OK)
async def get_data_quality_report(
    project_id: str,
    chronicle_analytics_client: ChronicleAnalyticsClient = Depends(get_chronicle_analytics_client_dependency)
):
    """Assess historical data availability and quality for a project."""
    logger.info("Data quality report requested", project_id=project_id)
    try:
        data_quality_validator = DataQualityValidator()
        
        # Use the client's method to get the report, which internally uses the validator
        report = await chronicle_analytics_client.validate_data_availability(project_id)
        recommendations = data_quality_validator.recommend_data_improvements(report)
        
        return {
            "project_id": project_id,
            "data_quality_report": report.dict(),
            "recommendations": recommendations
        }
    except HTTPException as e:
        logger.error("Failed to get data quality report due to HTTP error", project_id=project_id, detail=e.detail, status_code=e.status_code)
        raise e
    except Exception as e:
        logger.error("Failed to get data quality report due to unexpected error", project_id=project_id, error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error getting data quality report: {e}")

@intelligence_router.get("/performance/metrics/{project_id}", status_code=status.HTTP_200_OK)
async def get_performance_metrics(
    project_id: str,
    decision_engine: EnhancedDecisionEngineV2 = Depends(get_decision_engine_dependency)
):
    """Get detailed performance metrics for pattern analysis"""
    logger.info("Performance metrics requested", project_id=project_id)
    try:
        # Access the shared PerformanceMonitor instances from the decision_engine
        total_orchestration_summary = decision_engine.total_performance_monitor.get_summary("enhanced_orchestration")
        pattern_analysis_summary = decision_engine.pattern_engine.get_performance_summary("full_pattern_analysis")
        resource_usage = decision_engine.resource_monitor.get_resource_usage()

        # Combine metrics for the response
        component_metrics = {
            "full_pattern_analysis": pattern_analysis_summary,
            "total_orchestration": total_orchestration_summary,
            "resource_usage": resource_usage
        }

        total_time = total_orchestration_summary.get("avg_duration_ms", 0)

        # Retrieve adoption metrics
        intelligence_invocations = decision_engine.total_performance_monitor.intelligence_invocations
        recommendations_generated = decision_engine.total_performance_monitor.recommendations_generated
        adjustments_applied = decision_engine.total_performance_monitor.adjustments_applied
        
        application_rate_percent = (adjustments_applied / recommendations_generated * 100) if recommendations_generated > 0 else 0.0

        return {
            "project_id": project_id,
            "total_execution_time_ms": total_time,
            "component_metrics": component_metrics,
            "adoption_metrics": {
                "intelligence_invocations": intelligence_invocations,
                "recommendations_generated": recommendations_generated,
                "adjustments_applied": adjustments_applied,
                "application_rate_percent": application_rate_percent
            },
            "performance_thresholds": {
                "target_total_time_ms": 2000,
                "actual_total_time_ms": total_time,
                "threshold_met": total_time < 2000
            },
            "recommendations": _generate_performance_recommendations(total_time, component_metrics)
        }
    except Exception as e:
        logger.error("Performance metrics collection failed", error=str(e), project_id=project_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Performance metrics failed: {e}")

def _generate_performance_recommendations(total_time: float, component_metrics: Dict) -> List[str]:
    recommendations = []
    
    if total_time > 2000:
        recommendations.append("Total execution time exceeds 2-second threshold")
    
    # Check full_pattern_analysis specifically, as it's the main component timed by PatternEngine
    full_pattern_analysis_summary = component_metrics.get("full_pattern_analysis", {})
    if full_pattern_analysis_summary.get("avg_duration_ms", 0) > 1000:
        recommendations.append("Pattern analysis component exceeds 1-second threshold")
    
    similarity_time = component_metrics.get("similarity_analysis", {}).get("avg_duration_ms", 0)
    if similarity_time > 500:
        recommendations.append("Similarity analysis is slow - consider reducing dataset size or improving caching")
    
    if full_pattern_analysis_summary.get("success_rate", 100) < 95:
        recommendations.append("Pattern analysis has low success rate - investigate error handling")
    
    return recommendations or ["Performance within acceptable thresholds"]

@intelligence_router.get("/decision-impact/{project_id}", status_code=status.HTTP_200_OK)
async def get_decision_impact(
    project_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    chronicle_analytics_client: ChronicleAnalyticsClient = Depends(get_chronicle_analytics_client_dependency)
):
    """Track outcomes of intelligence-enhanced decisions vs rule-based decisions for validation."""
    logger.info("Decision impact requested", project_id=project_id, start_date=start_date, end_date=end_date)
    try:
        tracker = DecisionTracker(chronicle_analytics_client, project_id=project_id)
        
        # Default time range to last 30 days if not provided
        _end_date = datetime.fromisoformat(end_date) if end_date else datetime.utcnow()
        _start_date = datetime.fromisoformat(start_date) if start_date else (_end_date - timedelta(days=30))
        time_period = TimeRange(start_date=_start_date, end_date=_end_date)

        report = await tracker.compare_decision_effectiveness(project_id, time_period)
        return report
    except HTTPException as e:
        logger.error("Failed to get decision impact due to HTTP error", project_id=project_id, detail=e.detail, status_code=e.status_code)
        raise e
    except Exception as e:
        logger.error("Failed to get decision impact due to unexpected error", project_id=project_id, error=str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error getting decision impact: {e}")

@intelligence_router.post("/project/{project_id}/decision-mode", status_code=status.HTTP_200_OK)
async def configure_decision_mode(
    project_id: str,
    config_data: DecisionModeConfig,
    decision_engine: EnhancedDecisionEngineV2 = Depends(get_decision_engine_dependency)
):
    """Configure decision enhancement level for specific project or globally."""
    logger.info("Configuring decision mode", project_id=project_id, config_data=config_data.dict())
    try:
        # This is a simplified approach. In a real system, this would update a persistent
        # configuration store (e.g., a database or a ConfigMap in Kubernetes) that the
        # decision engine reads from. For now, we'll simulate updating the in-memory config.
        # This change will NOT persist across service restarts without a proper config management system.
        
        # Update the in-memory config object. This is temporary for demonstration.
        get_config()["intelligence"]["decision_enhancement"]["mode"] = config_data.mode
        get_config()["intelligence"]["decision_enhancement"]["confidence_threshold"] = config_data.confidence_threshold
        get_config()["intelligence"]["decision_enhancement"]["enable_task_adjustments"] = config_data.enable_task_count_adjustment
        get_config()["intelligence"]["decision_enhancement"]["enable_sprint_duration_adjustments"] = config_data.enable_sprint_duration_adjustment
        get_config()["intelligence"]["decision_enhancement"]["enable_resource_allocation_adjustment"] = config_data.enable_resource_allocation_adjustment

        # In a real scenario, you might trigger a reload of the config in the decision_engine
        # or have the decision_engine directly read from a dynamic source.

        return {"message": f"Decision mode configured for project {project_id}", "applied_config": config_data.dict()}
    except Exception as e:
        logger.error("Failed to configure decision mode", project_id=project_id, error=str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error configuring decision mode: {e}")

@intelligence_router.get("/decision-audit/{project_id}", status_code=status.HTTP_200_OK)
async def get_decision_audit(
    project_id: str,
    chronicle_analytics_client: ChronicleAnalyticsClient = Depends(get_chronicle_analytics_client_dependency)
):
    """Retrieve complete decision audit trail for a project showing all intelligence modifications."""
    logger.info("Decision audit trail requested", project_id=project_id)
    try:
        # This would query Chronicle for "orchestration_decision_audit" events for the given project_id.
        # For now, returning dummy data or an empty list.
        audit_records = await chronicle_analytics_client.get_decision_audit_trail(project_id)
        
        if not audit_records:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No decision audit records found for project {project_id}.")

        return {"project_id": project_id, "audit_trail": audit_records}
    except HTTPException as e:
        logger.error("Failed to get decision audit trail due to HTTP error", project_id=project_id, detail=e.detail, status_code=e.status_code)
        raise e
    except Exception as e:
        logger.error("Failed to get decision audit trail due to unexpected error", project_id=project_id, error=str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error getting decision audit trail: {e}")

@intelligence_router.get("/hybrid-patterns/{project_id}", status_code=status.HTTP_200_OK)
async def get_hybrid_patterns_analysis(
    project_id: str,
    decision_engine: EnhancedDecisionEngineV2 = Depends(get_decision_engine_dependency)
):
    """Get hybrid pattern analysis combining episode memory and Chronicle data."""
    logger.info("Hybrid patterns analysis requested", project_id=project_id)
    try:
        if not decision_engine.memory_bridge:
            return {
                "project_id": project_id,
                "hybrid_analysis_available": False,
                "message": "Episode learning system not available - hybrid analysis disabled",
                "chronicle_only_available": True
            }
        
        # Retrieve recent episodes for context
        episodes = []
        if decision_engine.episode_retriever:
            episodes = await decision_engine.episode_retriever.get_episodes_by_project(
                project_id=project_id,
                limit=10,
                min_quality=0.6
            )
        
        if not episodes:
            return {
                "project_id": project_id,
                "hybrid_analysis_available": False,
                "message": "No episodes found for hybrid analysis",
                "episodes_count": 0,
                "chronicle_only_available": True
            }
        
        # Translate episodes to decision context
        current_project_context = {"project_id": project_id}
        episode_context = await decision_engine.memory_bridge.translate_episodes_to_context(
            episodes=episodes,
            current_project_context=current_project_context
        )
        
        # Create dummy project data for analysis
        dummy_project_data = ProjectData(
            project_id=project_id,
            backlog_tasks=0, unassigned_tasks=0, active_sprints=0, team_size=0, team_availability={}
        )
        
        # Perform hybrid pattern analysis
        pattern_analysis, pattern_combination_result = await decision_engine.pattern_engine.analyze_hybrid_patterns(
            project_id=project_id,
            project_data=dummy_project_data,
            episode_context=episode_context
        )
        
        # Generate insights summary
        insights_summary = decision_engine.pattern_engine.generate_hybrid_insights_summary(
            enhanced_analysis=pattern_analysis,
            combination_result=pattern_combination_result,
            episode_context=episode_context
        )
        
        return {
            "project_id": project_id,
            "hybrid_analysis_available": True,
            "episode_context": {
                "similar_episodes_analyzed": episode_context.similar_episodes_analyzed,
                "episodes_used_for_context": episode_context.episodes_used_for_context,
                "average_episode_similarity": episode_context.average_episode_similarity,
                "decision_patterns": [p.dict() for p in episode_context.decision_patterns]
            },
            "pattern_combination_result": {
                "combined_patterns_count": len(pattern_combination_result.combined_patterns),
                "overall_confidence": pattern_combination_result.overall_confidence,
                "pattern_source_influence": pattern_combination_result.pattern_source_influence,
                "combined_patterns": [
                    {
                        "pattern_type": p.pattern_type,
                        "confidence": p.confidence,
                        "success_rate": p.success_rate,
                        "total_evidence_count": p.total_evidence_count,
                        "episode_evidence_count": p.episode_evidence_count,
                        "chronicle_evidence_count": p.chronicle_evidence_count
                    }
                    for p in pattern_combination_result.combined_patterns
                ]
            },
            "insights_summary": insights_summary,
            "pattern_analysis": pattern_analysis.dict()
        }
        
    except Exception as e:
        logger.error("Failed to get hybrid patterns analysis", project_id=project_id, error=str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error getting hybrid patterns: {e}")

@intelligence_router.get("/episode-insights/{project_id}", status_code=status.HTTP_200_OK)
async def get_episode_insights(
    project_id: str,
    limit: int = 10,
    decision_engine: EnhancedDecisionEngineV2 = Depends(get_decision_engine_dependency)
):
    """Get episode-based learning insights for a project."""
    logger.info("Episode insights requested", project_id=project_id, limit=limit)
    try:
        if not decision_engine.episode_retriever:
            return {
                "project_id": project_id,
                "episode_learning_available": False,
                "message": "Episode learning system not available"
            }
        
        # Retrieve recent episodes
        episodes = await decision_engine.episode_retriever.get_episodes_by_project(
            project_id=project_id,
            limit=limit,
            min_quality=0.5
        )
        
        if not episodes:
            return {
                "project_id": project_id,
                "episode_learning_available": True,
                "episodes_found": 0,
                "message": "No episodes found for this project"
            }
        
        # Analyze episode patterns
        episode_summary = {
            "total_episodes": len(episodes),
            "successful_decisions": len([ep for ep in episodes if ep.outcome and ep.outcome.get('success', False)]),
            "decision_sources": {},
            "average_confidence": 0.0,
            "recent_decisions": []
        }
        
        # Aggregate decision source statistics
        for episode in episodes:
            source = episode.decision_source or "unknown"
            episode_summary["decision_sources"][source] = episode_summary["decision_sources"].get(source, 0) + 1
        
        # Calculate average confidence
        confidences = []
        for episode in episodes:
            if episode.reasoning and isinstance(episode.reasoning, dict):
                conf_scores = episode.reasoning.get('confidence_scores', {})
                if isinstance(conf_scores, dict) and 'overall' in conf_scores:
                    confidences.append(conf_scores['overall'])
        
        if confidences:
            episode_summary["average_confidence"] = sum(confidences) / len(confidences)
        
        # Format recent decisions
        for episode in episodes[:5]:
            decision_info = {
                "timestamp": episode.timestamp.isoformat(),
                "decision_source": episode.decision_source,
                "action_summary": {},
                "has_outcome": episode.outcome is not None,
                "episode_id": str(episode.episode_id)
            }
            
            if episode.action:
                decision_info["action_summary"] = {
                    "sprint_created": episode.action.get('sprint_created', False),
                    "tasks_assigned": episode.action.get('tasks_assigned', 0),
                    "cronjob_created": episode.action.get('cronjob_created', False)
                }
            
            episode_summary["recent_decisions"].append(decision_info)
        
        return {
            "project_id": project_id,
            "episode_learning_available": True,
            "episode_summary": episode_summary,
            "learning_metadata": {
                "feature_flags": {
                    "async_learning": decision_engine.feature_flags.ENABLE_ASYNC_LEARNING,
                    "strategy_evolution": decision_engine.feature_flags.ENABLE_STRATEGY_EVOLUTION
                },
                "memory_bridge_available": decision_engine.memory_bridge is not None,
                "episode_logger_available": decision_engine.episode_logger is not None
            }
        }
        
    except Exception as e:
        logger.error("Failed to get episode insights", project_id=project_id, error=str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error getting episode insights: {e}")

@intelligence_router.get("/performance/hybrid-metrics/{project_id}", status_code=status.HTTP_200_OK)
async def get_hybrid_performance_metrics(
    project_id: str,
    decision_engine: EnhancedDecisionEngineV2 = Depends(get_decision_engine_dependency)
):
    """Get detailed performance metrics for hybrid intelligence operations."""
    logger.info("Hybrid performance metrics requested", project_id=project_id)
    try:
        # Get enhanced orchestration v2 metrics
        orchestration_v2_summary = decision_engine.total_performance_monitor.get_summary("enhanced_orchestration_v2")
        
        # Get component-specific metrics
        component_metrics = {
            "episode_retrieval": decision_engine.total_performance_monitor.get_summary("episode_retrieval"),
            "memory_bridge_translation": decision_engine.total_performance_monitor.get_summary("memory_bridge_translation"),
            "hybrid_pattern_analysis": decision_engine.total_performance_monitor.get_summary("hybrid_pattern_analysis"),
            "hybrid_adjustment_generation": decision_engine.total_performance_monitor.get_summary("hybrid_adjustment_generation"),
            "intelligence_confidence_gating": decision_engine.total_performance_monitor.get_summary("intelligence_confidence_gating")
        }
        
        # Get resource usage
        resource_usage = decision_engine.resource_monitor.get_resource_usage()
        
        # Get learning system performance
        learning_metrics = {
            "episode_learning_enabled": decision_engine._is_learning_enabled(),
            "episode_logging_enabled": decision_engine._is_episode_logging_enabled(),
            "decision_mode": decision_engine._get_decision_mode()
        }
        
        # Calculate performance thresholds
        total_time = orchestration_v2_summary.get("avg_duration_ms", 0)
        thresholds = {
            "target_total_time_ms": 3000,  # Increased for hybrid operations
            "actual_total_time_ms": total_time,
            "threshold_met": total_time < 3000,
            "component_thresholds": {
                "episode_retrieval_under_500ms": component_metrics["episode_retrieval"].get("avg_duration_ms", 0) < 500,
                "memory_bridge_under_300ms": component_metrics["memory_bridge_translation"].get("avg_duration_ms", 0) < 300,
                "hybrid_analysis_under_1500ms": component_metrics["hybrid_pattern_analysis"].get("avg_duration_ms", 0) < 1500
            }
        }
        
        return {
            "project_id": project_id,
            "hybrid_orchestration_metrics": orchestration_v2_summary,
            "component_metrics": component_metrics,
            "resource_usage": resource_usage,
            "learning_system_metrics": learning_metrics,
            "performance_thresholds": thresholds,
            "recommendations": _generate_hybrid_performance_recommendations(component_metrics, thresholds)
        }
        
    except Exception as e:
        logger.error("Failed to get hybrid performance metrics", project_id=project_id, error=str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error getting hybrid performance metrics: {e}")

def _generate_hybrid_performance_recommendations(component_metrics: Dict, thresholds: Dict) -> List[str]:
    """Generate performance recommendations for hybrid intelligence system."""
    recommendations = []
    
    # Check overall performance
    if not thresholds.get("threshold_met", True):
        recommendations.append("Overall hybrid orchestration exceeds 3-second threshold - consider optimization")
    
    # Check component-specific thresholds
    component_thresholds = thresholds.get("component_thresholds", {})
    
    if not component_thresholds.get("episode_retrieval_under_500ms", True):
        recommendations.append("Episode retrieval is slow - consider improving similarity search or reducing episode limit")
    
    if not component_thresholds.get("memory_bridge_under_300ms", True):
        recommendations.append("Memory bridge translation is slow - optimize episode context conversion")
    
    if not component_thresholds.get("hybrid_analysis_under_1500ms", True):
        recommendations.append("Hybrid pattern analysis is slow - consider caching or reducing analysis complexity")
    
    # Check success rates
    for component, metrics in component_metrics.items():
        if metrics.get("success_rate", 100) < 95:
            recommendations.append(f"{component} has low success rate - investigate error handling")
    
    return recommendations or ["Hybrid intelligence performance within acceptable thresholds"]
