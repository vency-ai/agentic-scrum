from typing import Optional
from fastapi import HTTPException, status

from intelligence.chronicle_analytics_client import ChronicleAnalyticsClient
from intelligence.cache_manager import CacheManager
from enhanced_decision_engine import EnhancedDecisionEngine
from project_analyzer import ProjectAnalyzer
from cronjob_generator import CronJobGenerator
from service_clients import SprintServiceClient, ChronicleServiceClient
from intelligence.performance_monitor import PerformanceMonitor
from intelligence.decision_auditor import DecisionAuditor # New import
from memory.agent_memory_system import AgentMemorySystem # New import

# Global instances (will be set during app startup)
chronicle_analytics_client_instance: Optional[ChronicleAnalyticsClient] = None
cache_manager_instance: Optional[CacheManager] = None
decision_engine_instance: Optional[EnhancedDecisionEngine] = None
project_analyzer_instance: Optional[ProjectAnalyzer] = None
cronjob_generator_instance: Optional[CronJobGenerator] = None
sprint_service_client_instance: Optional[SprintServiceClient] = None
chronicle_service_client_instance: Optional[ChronicleServiceClient] = None
performance_monitor_instance: Optional[PerformanceMonitor] = None
decision_auditor_instance: Optional[DecisionAuditor] = None
agent_memory_system_instance: Optional[AgentMemorySystem] = None # New global instance

def set_chronicle_analytics_client_instance(instance: ChronicleAnalyticsClient):
    global chronicle_analytics_client_instance
    chronicle_analytics_client_instance = instance

def set_cache_manager_instance(instance: CacheManager):
    global cache_manager_instance
    cache_manager_instance = instance

def set_decision_engine_instance(instance: EnhancedDecisionEngine):
    global decision_engine_instance
    decision_engine_instance = instance

def set_project_analyzer_instance(instance: ProjectAnalyzer):
    global project_analyzer_instance
    project_analyzer_instance = instance

def set_cronjob_generator_instance(instance: CronJobGenerator):
    global cronjob_generator_instance
    cronjob_generator_instance = instance

def set_sprint_service_client_instance(instance: SprintServiceClient):
    global sprint_service_client_instance
    sprint_service_client_instance = instance

def set_chronicle_service_client_instance(instance: ChronicleServiceClient):
    global chronicle_service_client_instance
    chronicle_service_client_instance = instance

def set_performance_monitor_instance(instance: PerformanceMonitor):
    global performance_monitor_instance
    performance_monitor_instance = instance

def set_decision_auditor_instance(instance: DecisionAuditor):
    global decision_auditor_instance
    decision_auditor_instance = instance

def set_agent_memory_system_instance(instance: AgentMemorySystem):
    global agent_memory_system_instance
    agent_memory_system_instance = instance

# Dependency to get ChronicleAnalyticsClient
def get_chronicle_analytics_client_dependency() -> ChronicleAnalyticsClient:
    if not chronicle_analytics_client_instance:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="ChronicleAnalyticsClient not initialized.")
    return chronicle_analytics_client_instance

# Dependency to get CacheManager
def get_cache_manager_dependency() -> CacheManager:
    if not cache_manager_instance:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="CacheManager not initialized.")
    return cache_manager_instance

# Dependency to get EnhancedDecisionEngine
def get_decision_engine_dependency() -> EnhancedDecisionEngine:
    if not decision_engine_instance:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="EnhancedDecisionEngine not initialized.")
    return decision_engine_instance

def get_project_analyzer_dependency() -> ProjectAnalyzer:
    if not project_analyzer_instance:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="ProjectAnalyzer not initialized.")
    return project_analyzer_instance

def get_cronjob_generator_dependency() -> CronJobGenerator:
    if not cronjob_generator_instance:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="CronjobGenerator not initialized.")
    return cronjob_generator_instance

def get_sprint_service_client_dependency() -> SprintServiceClient:
    if not sprint_service_client_instance:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="SprintServiceClient not initialized.")
    return sprint_service_client_instance

def get_chronicle_service_client_dependency() -> ChronicleServiceClient:
    if not chronicle_service_client_instance:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="ChronicleServiceClient not initialized.")
    return chronicle_service_client_instance

def get_performance_monitor_dependency() -> PerformanceMonitor:
    if not performance_monitor_instance:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="PerformanceMonitor not initialized.")
    return performance_monitor_instance

def get_decision_auditor_dependency() -> DecisionAuditor:
    if not decision_auditor_instance:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="DecisionAuditor not initialized.")
    return decision_auditor_instance

def get_agent_memory_system_dependency() -> AgentMemorySystem:
    if not agent_memory_system_instance:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="AgentMemorySystem not initialized.")
    return agent_memory_system_instance