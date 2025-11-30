import os
import json
import asyncio
import httpx
import redis.asyncio as redis
import structlog
import logging
from fastapi import FastAPI, HTTPException, status, Body, Request
from fastapi.responses import JSONResponse
from kubernetes import client, config
from log_config import HealthCheckFilter
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import uuid
from datetime import datetime
import traceback
from intelligence.custom_circuit_breaker import CircuitBroken as CircuitBrokenError
import yaml # Added import

from intelligence.chronicle_analytics_client import ChronicleAnalyticsClient
from intelligence.cache_manager import CacheManager
from enhanced_decision_engine_v2 import EnhancedDecisionEngineV2
from models import ProjectData, AnalysisResult, EnhancedDecision
# from .config_loader import load_config # Commented out
from config_loader import get_config # Still needed for EnhancedDecisionEngine, will be passed directly
from intelligence.decision_auditor import DecisionAuditor # New import

from project_analyzer import ProjectAnalyzer

from cronjob_generator import CronJobGenerator
from service_clients import SprintServiceClient, ChronicleServiceClient, ProjectServiceClient, BacklogServiceClient
from k8s_client import KubernetesClient
from memory.agent_memory_system import AgentMemorySystem # New import

from dependencies import (
    set_chronicle_analytics_client_instance,
    set_decision_engine_instance,
    set_project_analyzer_instance,
    set_cronjob_generator_instance,
    set_sprint_service_client_instance,
    set_chronicle_service_client_instance,
    set_cache_manager_instance,
    set_performance_monitor_instance, # New import
    get_project_analyzer_dependency,
    get_decision_engine_dependency,
    get_cronjob_generator_dependency,
    get_sprint_service_client_dependency,
    get_chronicle_service_client_dependency,
    get_cache_manager_dependency,
    get_chronicle_analytics_client_dependency,
    get_agent_memory_system_dependency, # New import
    set_agent_memory_system_instance # New import
)

logger = structlog.get_logger()

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

from starlette_exporter import PrometheusMiddleware, handle_metrics # New import

app = FastAPI()

app.add_middleware(PrometheusMiddleware, app_name="project-orchestrator")
app.add_route("/metrics", handle_metrics)

@app.exception_handler(CircuitBrokenError)
async def circuit_breaker_exception_handler(request: Request, exc: CircuitBrokenError):
    logger.warning("Circuit breaker is open, service degraded", path=request.url.path, error=str(exc))
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Service temporarily unavailable due to downstream service failures. Circuit breaker is open.",
            "service_status": "degraded",
            "error_type": "circuit_breaker_open",
            "retry_after": "30 seconds"
        }
    )

uvicorn_access_logger = logging.getLogger("uvicorn.access")
uvicorn_access_logger.addFilter(HealthCheckFilter())

REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
REDIS_STREAM_NAME = os.environ.get("REDIS_STREAM_NAME", "orchestration_events")

redis_client = None
k8s_client = None

def load_config_local(config_path="config/base.yaml"):
    absolute_config_path = os.path.join(os.getcwd(), config_path)
    logger.info(f"Attempting to load config locally from: {absolute_config_path}")
    if not os.path.exists(absolute_config_path):
        logger.error(f"Configuration file not found at {absolute_config_path}. Current working directory: {os.getcwd()}")
        raise FileNotFoundError(f"Configuration file not found at {absolute_config_path}")
    with open(absolute_config_path, 'r') as f:
        local_config = yaml.safe_load(f)
    logger.info("Local configuration loaded successfully.")
    return local_config

async def get_redis_client():
    global redis_client
    if redis_client:
        return redis_client
    
    try:
        client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)
        if await client.ping():
            logger.info("Successfully connected to Redis", host=REDIS_HOST, port=REDIS_PORT)
            redis_client = client
            return redis_client
        else:
            logger.error("Redis ping failed", host=REDIS_HOST, port=REDIS_PORT)
            return None
    except redis.ConnectionError as e:
        logger.error("Failed to connect to Redis", host=REDIS_HOST, port=REDIS_PORT, error=str(e), exc_info=True)
        return None

@app.on_event("startup")
async def startup_event():
    global k8s_client
    await get_redis_client()
    k8s_client = KubernetesClient()
    if not k8s_client.api_client:
        raise RuntimeError("Failed to initialize Kubernetes client.")

    # Ensure configuration is loaded before use
    current_config = load_config_local()

    chronicle_analytics_client_local = ChronicleAnalyticsClient(chronicle_service_url=current_config['external_services']['chronicle_service_url'])
    cache_manager_local = CacheManager(ttl_minutes=current_config['intelligence']['cache_ttl_minutes'])
    from intelligence.performance_monitor import PerformanceMonitor # New import

    # Initialize global PerformanceMonitor
    performance_monitor_local = PerformanceMonitor()
    set_performance_monitor_instance(performance_monitor_local)

    chronicle_analytics_client_local = ChronicleAnalyticsClient(chronicle_service_url=current_config['external_services']['chronicle_service_url'])
    cache_manager_local = CacheManager(ttl_minutes=current_config['intelligence']['cache_ttl_minutes'])
    chronicle_service_client_local = ChronicleServiceClient()
    decision_auditor_local = DecisionAuditor(chronicle_service_client_local)
    
    # Initialize AgentMemorySystem first
    logger.info("Attempting to initialize AgentMemorySystem.")
    logger.info("Current external_services config:", external_services=current_config.get('external_services'))
    agent_memory_system_local = None
    try:
        agent_memory_system_local = AgentMemorySystem(
            connection_string=current_config['external_services']['agent_memory_db_connection_string'],
            embedding_service_url=current_config['external_services']['embedding_service_url']
        )
        await agent_memory_system_local.initialize(
            min_connections=current_config['external_services']['agent_memory_db_min_connections'],
            max_connections=current_config['external_services']['agent_memory_db_max_connections']
        )
        set_agent_memory_system_instance(agent_memory_system_local)
        logger.info("AgentMemorySystem initialized successfully.")
    except Exception as e:
        logger.error("Failed to initialize AgentMemorySystem", error=str(e), exc_info=True)
        # Set to None - decision engine will run without episode learning
        agent_memory_system_local = None
    
    # Initialize EnhancedDecisionEngineV2 with episode learning capabilities
    memory_store = None
    embedding_client = None
    knowledge_store = None
    
    if agent_memory_system_local:
        memory_store = agent_memory_system_local.agent_memory_store
        embedding_client = agent_memory_system_local.embedding_client
        knowledge_store = agent_memory_system_local.knowledge_store
        logger.info("Episode learning capabilities available for decision engine")
    else:
        logger.warning("Agent memory system not available - decision engine will run without episode learning")
    
    decision_engine_local = EnhancedDecisionEngineV2(
        chronicle_analytics_client_local, 
        k8s_client, 
        current_config, 
        performance_monitor=performance_monitor_local, 
        decision_auditor=decision_auditor_local,
        memory_store=memory_store,
        embedding_client=embedding_client,
        knowledge_store=knowledge_store
    )

    # Set global instances in dependencies.py
    set_chronicle_analytics_client_instance(chronicle_analytics_client_local)
    set_cache_manager_instance(cache_manager_local)
    set_decision_engine_instance(decision_engine_local)

    # Initialize service clients
    project_analyzer_local = ProjectAnalyzer(chronicle_analytics_client_local, performance_monitor=performance_monitor_local) # Pass performance_monitor
    cronjob_generator_local = CronJobGenerator()
    sprint_service_client_local = SprintServiceClient()
    chronicle_service_client_local = ChronicleServiceClient()

    set_project_analyzer_instance(project_analyzer_local)
    set_cronjob_generator_instance(cronjob_generator_local)
    set_sprint_service_client_instance(sprint_service_client_local)
    set_chronicle_service_client_instance(chronicle_service_client_local)

    # Import intelligence_router here to avoid circular dependency
    from intelligence_router import intelligence_router
    app.include_router(intelligence_router, prefix="/orchestrate")

    logger.info("Startup event completed successfully.")

@app.on_event("shutdown")
async def shutdown_event():
    if redis_client:
        await redis_client.close()
        logger.info("Redis client closed.")
    # Use the global instance from dependencies for closing httpx client session
    chronicle_analytics_client_instance = get_chronicle_analytics_client_dependency()
    if chronicle_analytics_client_instance:
        await chronicle_analytics_client_instance.client.aclose()
        logger.info("ChronicleAnalyticsClient httpx session closed.")
    
    global k8s_client
    if k8s_client and k8s_client.executor:
        k8s_client.executor.shutdown(wait=True)
        logger.info("KubernetesClient ThreadPoolExecutor shut down.")

    # Close AgentMemorySystem
    agent_memory_system_instance = get_agent_memory_system_dependency()
    if agent_memory_system_instance:
        await agent_memory_system_instance.close()
        logger.info("AgentMemorySystem closed.")

@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    return {"status": "ok"}

@app.get("/health/ready", status_code=status.HTTP_200_OK)
async def readiness_check():
    dependencies_ready = True
    messages = []
    external_apis_status = {}
    intelligence_status = {}

    # Check Redis
    redis_status = "ok"
    try:
        if not redis_client or not await redis_client.ping():
            redis_status = "not ready"
            dependencies_ready = False
            messages.append("Redis connection not ready.")
    except Exception as e:
        redis_status = "error"
        dependencies_ready = False
        messages.append(f"Redis check failed: {e}")

    # Check Kubernetes API
    k8s_status = "ok"
    try:
        if not k8s_client or not k8s_client.api_client:
            k8s_status = "not ready"
            dependencies_ready = False
            messages.append("Kubernetes client not initialized.")
    except Exception as e:
        k8s_status = "error"
        dependencies_ready = False
        messages.append(f"Kubernetes API check failed: {e}")

    # Check external service health
    service_clients_for_health = [
        ("project_service", ProjectServiceClient()),
        ("backlog_service", BacklogServiceClient()),
        ("sprint_service", SprintServiceClient()),
        ("chronicle_service", ChronicleServiceClient())
    ]

    # Check Agent Memory System
    agent_memory_system_instance = get_agent_memory_system_dependency()
    if agent_memory_system_instance:
        try:
            logger.debug("Calling AgentMemorySystem health_check.")
            agent_memory_health = await agent_memory_system_instance.health_check()
            logger.debug("AgentMemorySystem health_check returned", health_status=agent_memory_health)

            # Extract embedding service health from agent_memory_health for top-level reporting
            embedding_service_health = agent_memory_health.pop("embedding_client", {"status": "not_checked"})
            external_apis_status["embedding-service"] = embedding_service_health

            if not agent_memory_health.get("overall", False):
                dependencies_ready = False
                messages.append("Agent Memory System not fully healthy.")
            external_apis_status["agent_memory_system"] = agent_memory_health
        except Exception as e:
            logger.error("Error during AgentMemorySystem health check", error=str(e), exc_info=True)
            dependencies_ready = False
            messages.append(f"Agent Memory System health check failed: {e}")
            external_apis_status["agent_memory_system"] = {"status": "error", "error_message": str(e)}
            external_apis_status["embedding-service"] = {"status": "error", "error_message": "Agent Memory System health check failed"}
    else:
        logger.warning("AgentMemorySystem instance not available during readiness check.")
        dependencies_ready = False
        messages.append("Agent Memory System not initialized.")
        external_apis_status["agent_memory_system"] = {"status": "not_initialized"}
        external_apis_status["embedding-service"] = {"status": "not_initialized"}
    
    for service_name, client_instance in service_clients_for_health:
        try:
            health_response = await client_instance._make_request("GET", "/health/ready")
            external_apis_status[service_name] = "ok"
        except CircuitBrokenError:
            external_apis_status[service_name] = "circuit_open"
        except Exception:
            external_apis_status[service_name] = "error"

    # Check Intelligence components
    cache_manager_instance = get_cache_manager_dependency()
    if cache_manager_instance:
        intelligence_status["cache_health"] = cache_manager_instance.get_health()
    else:
        intelligence_status["cache_health"] = {"status": "not_initialized"}
        dependencies_ready = False
        messages.append("CacheManager not initialized for intelligence health check.")

    intelligence_status["model_status"] = "healthy" # Placeholder for actual model health
    
    # Check Ollama LLM (AI Agent Advisor) if enabled
    decision_engine_instance = get_decision_engine_dependency()
    if decision_engine_instance and hasattr(decision_engine_instance, 'ai_advisor') and decision_engine_instance.ai_advisor:
        try:
            ollama_health = await decision_engine_instance.ai_advisor.health_check()
            external_apis_status["ollama_llm"] = ollama_health
            if ollama_health.get("status") != "ok":
                # Don't mark system as not ready - AI advisor is optional
                messages.append(f"Ollama LLM status: {ollama_health.get('status', 'unknown')}")
        except Exception as e:
            logger.error("Ollama LLM health check failed", error=str(e), exc_info=True)
            external_apis_status["ollama_llm"] = {
                "status": "error", 
                "error": str(e)[:100],
                "service_url": decision_engine_instance.ai_advisor.service_url if decision_engine_instance.ai_advisor else "unknown"
            }
            messages.append("Ollama LLM health check failed - AI advisor may be unavailable")
    else:
        # AI advisor not enabled - this is normal
        external_apis_status["ollama_llm"] = {
            "status": "disabled",
            "message": "AI Agent Advisor not enabled in configuration"
        }

    response_data = {
        "service": "project-orchestrator",
        "status": "ready" if dependencies_ready else "not_ready",
        "dependencies": {"redis": redis_status, "kubernetes_api": k8s_status},
        "external_apis": external_apis_status,
        "intelligence_components": intelligence_status,
        "timestamp": datetime.utcnow().isoformat()
    }

    if dependencies_ready:
        return response_data
    else:
        response_data["messages"] = messages
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=response_data
        )

class OrchestrationOptions(BaseModel):
    create_sprint_if_needed: bool = True
    assign_tasks: bool = True
    create_cronjob: bool = True
    schedule: str = "0 14 * * 1-5"
    sprint_duration_weeks: int = 2
    max_tasks_per_sprint: int = 10
    enable_pattern_recognition: bool = True

class OrchestrationRequest(BaseModel):
    action: str = "analyze_and_orchestrate"
    options: OrchestrationOptions = OrchestrationOptions()

@app.post("/orchestrate/project/{project_id}", status_code=status.HTTP_200_OK)
async def orchestrate_project(project_id: str, request: OrchestrationRequest = Body(...)):
    logger.info("Orchestration triggered", project_id=project_id, action=request.action, options=request.options.dict())

    project_analyzer_instance = get_project_analyzer_dependency()
    decision_engine_instance = get_decision_engine_dependency()
    cronjob_generator_instance = get_cronjob_generator_dependency()
    sprint_service_client_instance = get_sprint_service_client_dependency()
    chronicle_service_client_instance = get_chronicle_service_client_dependency()

    if not project_analyzer_instance or not decision_engine_instance or not cronjob_generator_instance or not sprint_service_client_instance or not chronicle_service_client_instance:
        logger.error("Service instances not initialized via dependencies.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Orchestrator not fully initialized.")

    try:
        analysis_result = await project_analyzer_instance.analyze_project_state(project_id, request.options.sprint_duration_weeks)

        project_data_for_decision = ProjectData(
            project_id=project_id,
            backlog_tasks=analysis_result.get("total_backlog_tasks", 0),
            unassigned_tasks=analysis_result.get("unassigned_tasks", 0),
            active_sprints=analysis_result.get("active_sprints_count", 0),
            team_size=analysis_result.get("team_size", 0),
            team_availability=analysis_result.get("team_availability", {}),
            current_active_sprint=analysis_result.get("current_active_sprint"),
            sprint_tasks_summary=analysis_result.get("sprint_tasks_summary")
        )
        full_orchestration_response = await decision_engine_instance.make_orchestration_decision(project_data_for_decision, request.options.dict())
        decisions = full_orchestration_response["decisions"]
        analysis_result_enhanced = full_orchestration_response["analysis"]

        actions_taken = []
        sprint_id = decisions.get("sprint_id") # Initialize sprint_id from decisions
        cronjob_name = None
        cronjob_name_to_delete = None # Initialize here

        if decisions["sprint_closure_triggered"]:
            sprint_id_to_close = decisions.get("sprint_id_to_close")
            if sprint_id_to_close:
                logger.debug("Attempting to close sprint", project_id=project_id, sprint_id=sprint_id_to_close)
                try:
                    close_sprint_response = await sprint_service_client_instance.close_sprint(sprint_id_to_close)
                    logger.debug("Sprint closure response", project_id=project_id, sprint_id=sprint_id_to_close, response=close_sprint_response)
                    actions_taken.append(f"Closed sprint {sprint_id_to_close}")
                    actions_taken.append(f"Generated retrospective report for {sprint_id_to_close}")

                    # --- NEW: Record Sprint Retrospective ---
                    retrospective_payload = {
                        "project_id": project_id,
                        "sprint_id": sprint_id_to_close,
                        "report_date": datetime.utcnow().date().isoformat(),
                        "summary": f"Automated retrospective for sprint {sprint_id_to_close} closure. All tasks completed.",
                        "what_went_well": ["All tasks completed as planned.", "Automated closure successful."],
                        "what_could_be_improved": ["N/A"],
                        "action_items": []
                    }
                    try:
                        await chronicle_service_client_instance.record_sprint_retrospective(retrospective_payload)
                        logger.info("Sprint retrospective recorded in Chronicle", project_id=project_id, sprint_id=sprint_id_to_close)
                    except Exception as e:
                        logger.error("Failed to record sprint retrospective in Chronicle", project_id=project_id, sprint_id=sprint_id_to_close, error=str(e), exc_info=True)
                        decisions["warnings"].append(f"Failed to record retrospective for sprint {sprint_id_to_close}: {e}")
                    # --- END NEW ---

                    if decisions["cronjob_deleted"]:
                        cronjob_name_to_delete = f"run-dailyscrum-{project_id.lower()}-{sprint_id_to_close.lower()}"
                        logger.info("Decision: Deleting CronJob", project_id=project_id, cronjob_name=cronjob_name_to_delete)
                        await k8s_client.delete_cronjob(namespace="dsm", name=cronjob_name_to_delete)
                        actions_taken.append(f"Deleted cronjob {cronjob_name_to_delete}")
                    
                    sprint_id = None
                    cronjob_name = None
                except HTTPException as e:
                    logger.error("Failed to close sprint due to HTTP error", project_id=project_id, sprint_id=sprint_id_to_close, detail=e.detail, status_code=e.status_code, exc_info=True)
                    decisions["warnings"].append(f"Failed to close sprint {sprint_id_to_close}: {e.detail}")
                except Exception as e:
                    logger.error("Failed to close sprint due to unexpected error", project_id=project_id, sprint_id=sprint_id_to_close, error=str(e), exc_info=True)
                    decisions["warnings"].append(f"Failed to close sprint {sprint_id_to_close}: {e}")
            else:
                logger.error("Cannot close sprint, sprint ID is missing from analysis", project_id=project_id, exc_info=True)
                decisions["warnings"].append("Cannot close sprint: Sprint ID is missing from analysis.")

        if decisions["create_new_sprint"] and sprint_id is None:
            logger.info("Decision: Creating new sprint", project_id=project_id, tasks_to_assign=decisions["tasks_to_assign"])
            sprint_name = decisions.get("sprint_name")
            if not sprint_name:
                logger.error("Decision engine did not provide a sprint name", project_id=project_id, exc_info=True)
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to generate sprint name.")
            
            create_sprint_payload = {
                "sprint_name": sprint_name,
                "duration_weeks": request.options.sprint_duration_weeks,
            }
            logger.debug("Sending sprint creation payload to Sprint Service", payload=create_sprint_payload)
            new_sprint = await sprint_service_client_instance.create_sprint(project_id, create_sprint_payload)
            sprint_id = new_sprint.get("sprint_id")
            actions_taken.append(f"Created new sprint {sprint_id}")
            actions_taken.append(f"Assigned {decisions['tasks_to_assign']} tasks to sprint")

        logger.debug("Checking CronJob creation conditions", cronjob_created=decisions["cronjob_created"], sprint_id=sprint_id)
        if decisions["cronjob_created"] and sprint_id is not None:
            sprint_id_for_cronjob = sprint_id
            if sprint_id_for_cronjob:
                logger.info("Decision: Creating CronJob", project_id=project_id, sprint_id=sprint_id_for_cronjob, schedule=request.options.schedule)
                logger.debug("Attempting to call cronjob_generator_instance.deploy_cronjob", project_id=project_id, sprint_id=sprint_id_for_cronjob) # Added debug log
                try:
                    cronjob_response = await cronjob_generator_instance.deploy_cronjob(
                        project_id=project_id,
                        sprint_id=sprint_id_for_cronjob,
                        schedule=request.options.schedule
                    )
                    cronjob_name = cronjob_response.get("cronjob_name")
                    actions_taken.append(f"Created cronjob {cronjob_name}")
                    logger.info("CronJob creation successful in app.py", cronjob_name=cronjob_name)
                    # Ensure decisions["cronjob_created"] remains true if successful
                    decisions["cronjob_created"] = True
                except Exception as e:
                    error_message = f"Failed to create CronJob for sprint {sprint_id_for_cronjob}: {e}"
                    logger.error("Failed to deploy CronJob from app.py", project_id=project_id, sprint_id=sprint_id_for_cronjob, error=str(e), exc_info=True)
                    decisions["warnings"].append(error_message)
                    actions_taken.append(f"Failed to create cronjob for sprint {sprint_id_for_cronjob}")
                    cronjob_name = None
                    # Set cronjob_created to False if deployment failed
                    decisions["cronjob_created"] = False
            else:
                logger.error("Cannot create cronjob, sprint ID is missing", project_id=project_id, exc_info=True)
                decisions["warnings"].append("Cannot create CronJob: Sprint ID is missing.")

        chronicle_payload_reports = {
            datetime.utcnow().date().isoformat(): [
                {
                    "assigned_to": "orchestrator",
                    "tasks": [
                        {
                            "id": "orchestration-task-" + str(uuid.uuid4()),
                            "yesterday_work": "N/A",
                            "today_work": decisions["reasoning"],
                            "impediments": "N/A",
                            "created_at": datetime.utcnow().isoformat()
                        }
                    ]
                }
            ]
        }

        orchestration_decision_details = {
            "decision_type": "SPRINT_CLOSED" if decisions["sprint_closure_triggered"] else ("CREATE_NEW_SPRINT" if decisions["create_new_sprint"] else "NO_SPRINT_CREATED"),
            "reasoning": decisions["reasoning"],
            "actions_taken": actions_taken,
            "cronjob_name": cronjob_name_to_delete if decisions["cronjob_deleted"] else cronjob_name,
            "sprint_closure_triggered": decisions["sprint_closure_triggered"],
            "cronjob_deleted": decisions["cronjob_deleted"],
            "decision_source": decisions.get("decision_source", "unknown"),
            "intelligence_adjustments": decisions.get("intelligence_adjustments", {})
        }

        chronicle_payload = {
            "project_id": project_id,
            "sprint_id": sprint_id_to_close if decisions["sprint_closure_triggered"] else sprint_id,
            "report_date": datetime.utcnow().date().isoformat(),
            "summary": decisions["reasoning"],
            "summary_metrics": {
                "total_team_members": analysis_result_enhanced.get("team_size", 0),
                "total_tasks": analysis_result_enhanced.get("backlog_tasks", 0),
                "completed_tasks": 0,
                "pending_tasks": analysis_result_enhanced.get("unassigned_tasks", 0)
            },
            "reports": chronicle_payload_reports,
            "orchestration_decision_details": orchestration_decision_details
        }

        if decisions.get("sprint_id_to_close"):
            # This field is part of the top-level DailyScrumReportNote, not additional_data
            # It's already handled by the sprint_id field above, so no need to add to additional_data
            pass

        await chronicle_service_client_instance.record_daily_scrum_report(chronicle_payload)
        logger.info("Orchestration decision recorded in Chronicle", project_id=project_id)

        if redis_client:
            event_payload = json.dumps(chronicle_payload)
            await redis_client.xadd(REDIS_STREAM_NAME, {"data": event_payload})
            logger.info("Orchestration event published to Redis Stream", stream=REDIS_STREAM_NAME, project_id=project_id)

        full_orchestration_response["actions_taken"] = actions_taken
        full_orchestration_response["cronjob_name"] = cronjob_name_to_delete if decisions.get("cronjob_deleted") else cronjob_name
        full_orchestration_response["sprint_id"] = sprint_id_to_close if decisions.get("sprint_closure_triggered") else sprint_id

        return full_orchestration_response

    except HTTPException as e:
        logger.error("Orchestration failed due to HTTP error", project_id=project_id, detail=e.detail, status_code=e.status_code, exc_info=True)
        raise e
    except Exception as e:
        full_traceback = traceback.format_exc()
        logger.error("Orchestration failed due to unexpected error", project_id=project_id, error=str(e), traceback=full_traceback, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error during orchestration: {e}")

@app.get("/orchestrate/project/{project_id}/status", status_code=status.HTTP_200_OK)
async def get_orchestration_status(project_id: str):
    logger.info("Orchestration status requested", project_id=project_id)

    project_analyzer_instance = get_project_analyzer_dependency()
    decision_engine_instance = get_decision_engine_dependency()
    cronjob_generator_instance = get_cronjob_generator_dependency()
    chronicle_analytics_client_instance = get_chronicle_analytics_client_dependency()

    if not project_analyzer_instance or not decision_engine_instance or not cronjob_generator_instance or not chronicle_analytics_client_instance:
        logger.error("Service instances not initialized via dependencies for status endpoint.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Orchestrator not fully initialized for status endpoint.")

    try:
        analysis_result = await project_analyzer_instance.analyze_project_state(project_id, sprint_duration_weeks=2)
        project_cronjobs = await cronjob_generator_instance.list_project_cronjobs(project_id)
        
        project_intelligence = await decision_engine_instance.get_project_intelligence(project_id)

        current_sprint = analysis_result.get("current_active_sprint")
        sprint_status = "no active sprint"
        if current_sprint:
            sprint_status = current_sprint.get("status", "active")

        return {
            "project_id": project_id,
            "last_analysis": datetime.utcnow().isoformat() + "Z",
            "current_sprint": current_sprint.get("sprint_id") if current_sprint else None,
            "sprint_status": sprint_status,
            "backlog_status": {
                "total_tasks": analysis_result.get("unassigned_tasks"),
                "unassigned": analysis_result.get("unassigned_tasks"),
                "in_progress": "N/A",
                "completed": "N/A"
            },
            "cronjobs": project_cronjobs,
            "intelligence_insights": project_intelligence
        }
    except HTTPException as e:
        logger.error("Failed to get orchestration status due to HTTP error", project_id=project_id, detail=e.detail, status_code=e.status_code, exc_info=True)
        raise e
    except Exception as e:
        logger.error("Failed to get orchestration status due to unexpected error", project_id=project_id, error=str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error getting status: {e}")

@app.delete("/orchestrate/project/{project_id}/cronjob/{cronjob_name}", status_code=status.HTTP_200_OK)
async def delete_project_cronjob(project_id: str, cronjob_name: str):
    logger.info("CronJob deletion requested", project_id=project_id, cronjob_name=cronjob_name)

    cronjob_generator_instance = get_cronjob_generator_dependency()

    if not cronjob_generator_instance:
        logger.error("CronJobGenerator instance not initialized via dependencies for deletion endpoint.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Orchestrator not fully initialized for deletion endpoint.")

    try:
        response = await cronjob_generator_instance.delete_cronjob(cronjob_name)
        return {"message": f"CronJob {cronjob_name} deleted successfully", "cronjob_name": cronjob_name, "status": response.get("status")}
    except HTTPException as e:
        logger.error("Failed to delete CronJob due to HTTP error", project_id=project_id, cronjob_name=cronjob_name, detail=e.detail, status_code=e.status_code, exc_info=True)
        raise e
    except Exception as e:
        logger.error("Failed to delete CronJob due to unexpected error", project_id=project_id, cronjob_name=cronjob_name, error=str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error deleting CronJob: {e}")

# Strategy Evolution API Endpoints
@app.get("/strategy/status", status_code=status.HTTP_200_OK)
async def get_strategy_evolution_status():
    """Get current status of the strategy evolution system."""
    logger.info("Strategy evolution status requested")
    
    try:
        engine = get_decision_engine_dependency()
        if not engine:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                              detail="Decision engine not available")
        
        # Check if strategy evolver is available
        if hasattr(engine, 'strategy_repository') and engine.strategy_repository:
            from services.strategy_evolver import StrategyEvolver
            strategy_evolver = StrategyEvolver(
                memory_store=engine.memory_store,
                knowledge_store=engine.strategy_repository.knowledge_store,
                feature_flags=engine.feature_flags
            )
            
            status_info = await strategy_evolver.get_evolution_status()
            return status_info
        else:
            return {
                "system_status": "disabled",
                "reason": "Strategy Evolution Layer not initialized",
                "timestamp": datetime.utcnow().isoformat()
            }
            
    except Exception as e:
        logger.error(f"Failed to get strategy evolution status: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail=f"Failed to get strategy status: {e}")

@app.post("/strategy/evolve", status_code=status.HTTP_200_OK)
async def trigger_strategy_evolution(force_parameters: Optional[Dict[str, Any]] = None):
    """Manually trigger strategy evolution process."""
    logger.info("Manual strategy evolution triggered", force_parameters=force_parameters)
    
    try:
        engine = get_decision_engine_dependency()
        if not engine:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                              detail="Decision engine not available")
        
        if hasattr(engine, 'strategy_repository') and engine.strategy_repository:
            from services.strategy_evolver import StrategyEvolver
            strategy_evolver = StrategyEvolver(
                memory_store=engine.memory_store,
                knowledge_store=engine.strategy_repository.knowledge_store,
                feature_flags=engine.feature_flags
            )
            
            if force_parameters:
                evolution_results = await strategy_evolver.force_strategy_evolution(force_parameters)
            else:
                evolution_results = await strategy_evolver.run_daily_evolution()
                
            return evolution_results
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                              detail="Strategy Evolution Layer not available")
            
    except Exception as e:
        logger.error(f"Failed to trigger strategy evolution: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail=f"Failed to evolve strategies: {e}")

@app.post("/strategy/evolve/project/{project_id}", status_code=status.HTTP_200_OK)
async def trigger_project_strategy_evolution(project_id: str):
    """Trigger targeted strategy evolution for a specific project."""
    logger.info("Project-specific strategy evolution triggered", project_id=project_id)
    
    try:
        engine = get_decision_engine_dependency()
        if not engine:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                              detail="Decision engine not available")
        
        if hasattr(engine, 'strategy_repository') and engine.strategy_repository:
            from services.strategy_evolver import StrategyEvolver
            strategy_evolver = StrategyEvolver(
                memory_store=engine.memory_store,
                knowledge_store=engine.strategy_repository.knowledge_store,
                feature_flags=engine.feature_flags
            )
            
            evolution_results = await strategy_evolver.evolve_for_project(project_id)
            return evolution_results
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                              detail="Strategy Evolution Layer not available")
            
    except Exception as e:
        logger.error(f"Failed to trigger project strategy evolution: {e}", project_id=project_id, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail=f"Failed to evolve strategies for project: {e}")

@app.get("/strategy/analytics", status_code=status.HTTP_200_OK)
async def get_strategy_analytics():
    """Get strategy repository analytics and performance metrics."""
    logger.info("Strategy analytics requested")
    
    try:
        engine = get_decision_engine_dependency()
        if not engine:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                              detail="Decision engine not available")
        
        if hasattr(engine, 'strategy_repository') and engine.strategy_repository:
            analytics = await engine.strategy_repository.get_strategy_analytics()
            return analytics
        else:
            return {
                "error": "Strategy Evolution Layer not available",
                "timestamp": datetime.utcnow().isoformat()
            }
            
    except Exception as e:
        logger.error(f"Failed to get strategy analytics: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail=f"Failed to get strategy analytics: {e}")

@app.get("/strategy/list", status_code=status.HTTP_200_OK)
async def list_active_strategies(limit: int = 50):
    """List active strategies in the repository."""
    logger.info("Active strategies list requested", limit=limit)
    
    try:
        engine = get_decision_engine_dependency()
        if not engine:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                              detail="Decision engine not available")
        
        if hasattr(engine, 'strategy_repository') and engine.strategy_repository:
            strategies = await engine.strategy_repository.get_active_strategies(limit=limit)
            
            strategy_list = []
            for strategy in strategies:
                strategy_list.append({
                    "strategy_id": str(strategy.knowledge_id),
                    "description": strategy.description,
                    "confidence": strategy.confidence,
                    "success_rate": strategy.success_rate,
                    "times_applied": strategy.times_applied,
                    "created_at": strategy.created_at.isoformat() if strategy.created_at else None,
                    "last_applied": strategy.last_applied.isoformat() if strategy.last_applied else None,
                    "is_active": strategy.is_active
                })
            
            return {
                "strategies": strategy_list,
                "total_count": len(strategy_list),
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                              detail="Strategy Evolution Layer not available")
            
    except Exception as e:
        logger.error(f"Failed to list active strategies: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail=f"Failed to list strategies: {e}")

@app.get("/strategy/{strategy_id}/performance", status_code=status.HTTP_200_OK)
async def get_strategy_performance(strategy_id: str, days: int = 30):
    """Get performance history for a specific strategy."""
    logger.info("Strategy performance requested", strategy_id=strategy_id, days=days)
    
    try:
        engine = get_decision_engine_dependency()
        if not engine:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                              detail="Decision engine not available")
        
        if hasattr(engine, 'strategy_repository') and engine.strategy_repository:
            performance_history = await engine.strategy_repository.get_strategy_performance_history(
                strategy_id=strategy_id,
                days=days,
                limit=100
            )
            
            return {
                "strategy_id": strategy_id,
                "performance_history": performance_history,
                "days_analyzed": days,
                "total_applications": len(performance_history),
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                              detail="Strategy Evolution Layer not available")
            
    except Exception as e:
        logger.error(f"Failed to get strategy performance: {e}", strategy_id=strategy_id, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail=f"Failed to get strategy performance: {e}")

@app.post("/strategy/{strategy_id}/deactivate", status_code=status.HTTP_200_OK)
async def deactivate_strategy(strategy_id: str, reason: str = "manual_deactivation"):
    """Manually deactivate a strategy."""
    logger.info("Strategy deactivation requested", strategy_id=strategy_id, reason=reason)
    
    try:
        engine = get_decision_engine_dependency()
        if not engine:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                              detail="Decision engine not available")
        
        if hasattr(engine, 'strategy_repository') and engine.strategy_repository:
            await engine.strategy_repository.deactivate_strategy(strategy_id, reason)
            
            return {
                "message": f"Strategy {strategy_id} deactivated successfully",
                "strategy_id": strategy_id,
                "reason": reason,
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, 
                              detail="Strategy Evolution Layer not available")
            
    except Exception as e:
        logger.error(f"Failed to deactivate strategy: {e}", strategy_id=strategy_id, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail=f"Failed to deactivate strategy: {e}")

@app.get("/strategy/health", status_code=status.HTTP_200_OK)
async def get_strategy_system_health():
    """Get health status of the strategy evolution system."""
    logger.info("Strategy system health check requested")
    
    try:
        engine = get_decision_engine_dependency()
        if not engine:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                              detail="Decision engine not available")
        
        if hasattr(engine, 'strategy_repository') and engine.strategy_repository:
            from services.strategy_evolver import StrategyEvolver
            strategy_evolver = StrategyEvolver(
                memory_store=engine.memory_store,
                knowledge_store=engine.strategy_repository.knowledge_store,
                feature_flags=engine.feature_flags
            )
            
            health_status = await strategy_evolver.health_check()
            return health_status
        else:
            return {
                "overall_status": "not_available",
                "reason": "Strategy Evolution Layer not initialized",
                "timestamp": datetime.utcnow().isoformat()
            }
            
    except Exception as e:
        logger.error(f"Failed to get strategy system health: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                          detail=f"Failed to get strategy health: {e}")