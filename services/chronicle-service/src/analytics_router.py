
from fastapi import APIRouter, HTTPException, Query
from datetime import datetime
from typing import Optional
import structlog

from analytics_engine import AnalyticsEngine

logger = structlog.get_logger()

analytics_engine = AnalyticsEngine()

analytics_router = APIRouter()

@analytics_router.get("/metrics/summary", summary="System-wide analytics summary")
async def get_analytics_summary():
    """Provides a system-wide summary of key analytics metrics across all projects."""
    try:
        summary = await analytics_engine.get_system_summary_metrics()
        if not summary:
            raise HTTPException(status_code=404, detail="No analytics metrics found.")
        return summary
    except Exception as e:
        logger.error(f"Error retrieving analytics summary: {e}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")

@analytics_router.get("/project/{project_id}/patterns", summary="Extract historical patterns for a specific project")
async def get_project_patterns(project_id: str):
    """Extracts historical patterns and key insights for a specific project based on its daily scrums and sprint retrospectives."""
    try:
        patterns = await analytics_engine.get_project_patterns(project_id)
        if not patterns:
            raise HTTPException(status_code=404, detail=f"No patterns found for project {project_id}.")
        return patterns
    except Exception as e:
        logger.error(f"Error retrieving project patterns for {project_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")

@analytics_router.get("/project/{project_id}/velocity", summary="Calculate team velocity trends over time")
async def get_project_velocity(project_id: str):
    """Calculates and provides team velocity trends for a specific project over its sprints."""
    try:
        velocity = await analytics_engine.get_project_velocity(project_id)
        if not velocity:
            raise HTTPException(status_code=404, detail=f"No velocity data found for project {project_id}.")
        return velocity
    except Exception as e:
        logger.error(f"Error retrieving project velocity for {project_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")

@analytics_router.get("/project/{project_id}/impediments", summary="Analyze common impediments and their frequency")
async def get_project_impediments(project_id: str):
    """Analyzes common impediments reported in sprint retrospectives for a specific project and their frequency/status."""
    try:
        impediments = await analytics_engine.get_project_impediments(project_id)
        if not impediments:
            raise HTTPException(status_code=404, detail=f"No impediment data found for project {project_id}.")
        return impediments
    except Exception as e:
        logger.error(f"Error retrieving project impediments for {project_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")

@analytics_router.get("/projects/similar", summary="Find projects with similar characteristics")
async def get_similar_projects(
    reference_project_id: str = Query(..., description="The ID of the project to compare against."),
    similarity_threshold: float = Query(0.7, ge=0.0, le=1.0, description="A float value (0.0-1.0) to filter similar projects. Defaults to 0.7.")
):
    print(f"[DEBUG] Entering get_similar_projects endpoint for reference_project_id: {reference_project_id}") # TEMP DEBUG
    """Identifies projects with similar characteristics based on historical data, such as common impediments or task patterns."""
    try:
        similar_projects = await analytics_engine.get_similar_projects(reference_project_id, similarity_threshold)
        print(f"[DEBUG] Returned from analytics_engine.get_similar_projects: {similar_projects}") # TEMP DEBUG
        if not similar_projects:
            raise HTTPException(status_code=404, detail=f"No similar projects found for {reference_project_id}.")
        return similar_projects
    except Exception as e:
        logger.error(f"Error retrieving similar projects for {reference_project_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")

@analytics_router.get("/decisions/impact/{project_id}", summary="Retrieve decision impact report for a project")
async def get_decision_impact_report(
    project_id: str,
    start_date: Optional[datetime] = Query(None, description="Start date for the analysis (ISO 8601 format)."),
    end_date: Optional[datetime] = Query(None, description="End date for the analysis (ISO 8601 format).")
):
    """
    Retrieves aggregated historical decision audit records and their associated sprint/project outcomes
    for a given project within a specified time range. This endpoint correlates orchestration_decision_audit
    events with sprint_retrospective or other outcome-tracking events.
    """
    try:
        report = await analytics_engine.get_decision_impact_report(project_id, start_date, end_date)
        if not report:
            raise HTTPException(status_code=404, detail=f"No decision impact data found for project {project_id}.")
        return report
    except Exception as e:
        logger.error(f"Error retrieving decision impact report for {project_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")
