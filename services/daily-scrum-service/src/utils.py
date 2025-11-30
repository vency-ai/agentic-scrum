import os
import requests
import structlog
from fastapi import HTTPException

logger = structlog.get_logger(__name__)

CHRONICLE_SERVICE_URL = os.environ.get("CHRONICLE_SERVICE_URL", "http://chronicle-service.dsm.svc.cluster.local")
SPRINT_SERVICE_URL = os.environ.get("SPRINT_SERVICE_URL", "http://sprint-service.dsm.svc.cluster.local")


def call_chronicle_service_record_daily_scrum(payload: dict):
    """Calls the chronicle service to record a daily scrum report."""
    try:
        response = requests.post(f"{CHRONICLE_SERVICE_URL}/v1/notes/daily_scrum_report", json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error("Failed to call chronicle service", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to record daily scrum report.")


def call_sprint_service_update_task_progress(task_id: str, progress: int):
    """Calls the sprint service to update task progress."""
    try:
        payload = {"progress_percentage": progress}
        response = requests.post(f"{SPRINT_SERVICE_URL}/tasks/{task_id}/progress", json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error("Failed to call sprint service", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to update task progress.")