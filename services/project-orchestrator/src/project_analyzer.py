import structlog
from typing import Dict, Any, List
from service_clients import ProjectServiceClient, BacklogServiceClient, SprintServiceClient
from intelligence.chronicle_analytics_client import ChronicleAnalyticsClient # New import
import datetime
from fastapi import HTTPException # Import HTTPException
from models import ProjectData # Import ProjectData from models.py

logger = structlog.get_logger()

from intelligence.performance_monitor import PerformanceMonitor # New import

class ProjectAnalyzer:
    def __init__(self, chronicle_analytics_client: ChronicleAnalyticsClient, performance_monitor: PerformanceMonitor):
        self.project_client = ProjectServiceClient()
        self.backlog_client = BacklogServiceClient()
        self.sprint_client = SprintServiceClient()
        self.chronicle_analytics_client = chronicle_analytics_client # Store client
        self.performance_monitor = performance_monitor # Store performance monitor

    async def analyze_project_state(self, project_id: str, sprint_duration_weeks: int) -> Dict[str, Any]:
        logger.info("Analyzing project state", project_id=project_id)
        
        project_details = {}
        try:
            project_details = await self.project_client.get_project(project_id)
        except HTTPException as e:
            logger.error("Error fetching project details", project_id=project_id, error=str(e))
            raise e

        team_members = []
        try:
            team_members = await self.project_client.get_team_members(project_id)
        except HTTPException as e:
            logger.error("Error fetching team members", project_id=project_id, error=str(e))
            raise e
        
        today = datetime.date.today()
        end_date = today + datetime.timedelta(weeks=sprint_duration_weeks)
        team_availability = {}
        try:
            team_availability = await self.project_client.check_team_availability(project_id, str(today), str(end_date))
        except HTTPException as e:
            logger.error("Error checking team availability", project_id=project_id, error=str(e))
            raise e
        
        backlog_summary = {}
        try:
            backlog_summary = await self.backlog_client.get_backlog_summary(project_id)
            logger.debug("Raw backlog summary from service", project_id=project_id, raw_summary=backlog_summary)
            logger.info("Backlog summary received", project_id=project_id, backlog_summary=backlog_summary)
        except HTTPException as e:
            logger.error("Error fetching backlog summary", project_id=project_id, error=str(e))
            raise e
        
        active_sprints = []
        try:
            active_sprints = await self.sprint_client.get_active_sprints()
        except HTTPException as e:
            logger.error("Error fetching active sprints", project_id=project_id, error=str(e))
            raise e
        
        project_sprints = []
        try:
            project_sprints = await self.sprint_client.get_sprints_by_project(project_id)
        except HTTPException as e:
            logger.error("Error fetching project sprints", project_id=project_id, error=str(e))
            raise e

        current_active_sprint = None
        for sprint in active_sprints:
            if isinstance(sprint, dict) and sprint.get("project_id") == project_id:
                current_active_sprint = sprint
                break
        
        logger.debug("Fetched project sprints", project_id=project_id, sprints=project_sprints)
        current_active_sprint_from_project_sprints = next((s for s in project_sprints if s.get("status") == "in_progress"), None)
        logger.debug("Determined current active sprint from project sprints", sprint=current_active_sprint_from_project_sprints)

        sprint_tasks_summary = None
        if current_active_sprint_from_project_sprints:
            try:
                sprint_tasks_summary = await self.sprint_client.get_sprint_task_summary(current_active_sprint_from_project_sprints["sprint_id"])
                logger.info("Fetched sprint task summary", sprint_id=current_active_sprint_from_project_sprints["sprint_id"], summary=sprint_tasks_summary)
            except HTTPException as e:
                logger.error("Error fetching sprint task summary", sprint_id=current_active_sprint_from_project_sprints["sprint_id"], error=str(e))

        # Fetch project patterns for additional characteristics
        project_patterns = None
        try:
            project_patterns = await self.chronicle_analytics_client.get_project_patterns(project_id)
        except HTTPException as e:
            logger.error("Error fetching project patterns from Chronicle Service", project_id=project_id, error=str(e))
        except Exception as e:
            logger.error("Unexpected error fetching project patterns", project_id=project_id, error=str(e))

        avg_task_complexity = 0.0
        domain_category = "general"
        project_duration = 0.0

        if project_patterns:
            # These fields are not directly in ProjectPatterns, but can be derived or assumed from it
            # For now, using placeholders or deriving from existing data if possible
            # In a real scenario, these would be explicitly returned by Chronicle Service or derived from more detailed data
            avg_task_complexity = 0.5 # Placeholder
            domain_category = "general" # Placeholder
            # project_duration could be derived from sprint history if available
            project_duration = (project_patterns.retrospective_count * sprint_duration_weeks) if project_patterns.retrospective_count else 0.0 # Placeholder

        analysis_result = {
            "project_id": project_id,
            "project_details": project_details,
            "team_size": len(team_members),
            "team_availability": team_availability,
            "backlog_tasks": backlog_summary.get("total_tasks", 0),
            "unassigned_tasks": backlog_summary.get("unassigned_for_sprint_count", 0),
            "active_sprints_count": len([s for s in project_sprints if s.get("status") == "in_progress"]),
            "current_active_sprint": current_active_sprint_from_project_sprints,
            "project_sprints_count": len(project_sprints),
            "has_active_sprint_for_project": bool(current_active_sprint_from_project_sprints),
            "sprint_count": len(project_sprints),
            "sprint_tasks_summary": sprint_tasks_summary,
            "avg_task_complexity": avg_task_complexity, # New field
            "domain_category": domain_category, # New field
            "project_duration": project_duration # New field
        }
        logger.info("Project state analysis complete", project_id=project_id, analysis=analysis_result)
        return analysis_result