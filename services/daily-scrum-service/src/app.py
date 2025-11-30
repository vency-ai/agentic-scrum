import os
import random
import json
from typing import List, Dict, Any
import uuid
import datetime

import structlog
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests

from utils import call_chronicle_service_record_daily_scrum, call_sprint_service_update_task_progress

logger = structlog.get_logger()

app = FastAPI()

# Environment variables
SPRINT_SERVICE_URL = os.environ.get("SPRINT_SERVICE_URL", "http://sprint-service.dsm.svc.cluster.local")

# Pydantic Models for response
class Task(BaseModel):
    task_id: str
    status: str
    progress_percentage: int = 0

class TaskUpdate(BaseModel):
    task_id: str
    progress_made: str
    new_status: str

class SimulationResult(BaseModel):
    message: str
    tasks_updated_count: int
    updates: List[TaskUpdate]

async def get_tasks_for_sprint(sprint_id: str) -> List[Task]:
    """
    Fetches tasks for a given sprint from the sprint-service.
    """
    try:
        response = requests.get(f"{SPRINT_SERVICE_URL}/sprints/{sprint_id}/tasks")
        response.raise_for_status()  # Raise an exception for HTTP errors
        tasks_data = response.json()
        return [Task(**task) for task in tasks_data]
    except requests.exceptions.RequestException as e:
        logger.error("Failed to fetch tasks from sprint-service", sprint_id=sprint_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to fetch tasks for sprint {sprint_id}: {e}")

@app.get("/health", status_code=200)
def health_check():
    """Health check endpoint to verify service is running."""
    return {"status": "ok"}

@app.post("/scrums/{sprint_id}/run", status_code=200, response_model=SimulationResult, deprecated=True)
async def run_daily_scrum(sprint_id: str):
    """
    [DEPRECATED] Executes the daily scrum simulation and publishes progress events to Redis.
    This endpoint's functionality has been moved to the Sprint Service.
    """
    logger.info("Starting daily scrum simulation", sprint_id=sprint_id)

    tasks = await get_tasks_for_sprint(sprint_id)

    if not tasks:
        logger.info("No tasks found for sprint", sprint_id=sprint_id)
        return SimulationResult(message="No tasks found for sprint.", tasks_updated_count=0, updates=[])

    # Simulate work on active tasks and publish events
    tasks_to_update = [task for task in tasks if task.status != "completed"]
    updated_tasks_summary: List[TaskUpdate] = []

    for task in tasks_to_update:
        task_id = task.task_id
        current_progress = task.progress_percentage
        progress_increase = random.randint(5, 35)
        new_progress = min(100, current_progress + progress_increase)

        # Placeholder for employee_id and daily scrum details
        employee_id = f"employee-{random.randint(1, 5):03d}" # Simulate different employees
        yesterday_work = f"Worked on {task_id} and completed {progress_increase}% of it."
        today_work = f"Continuing work on {task_id} to reach {new_progress}% completion."
        impediments = "No major impediments." if random.random() > 0.2 else "Encountered a minor blocker with external dependency."

        # Get project_id from sprint_id
        project_id = sprint_id.split('-')[0]

        daily_scrum_payload = {
            "project_id": project_id,
            "sprint_id": sprint_id,
            "report_date": datetime.date.today().isoformat(),
            "employee_id": employee_id,
            "yesterday_work": yesterday_work,
            "today_work": today_work,
            "impediments": impediments,
        }

        try:
            # Record daily scrum update in chronicle service
            call_chronicle_service_record_daily_scrum(daily_scrum_payload)
            logger.info("Recorded daily scrum update in chronicle service", payload=daily_scrum_payload)

            # Update task progress in sprint service
            call_sprint_service_update_task_progress(task_id, new_progress)
            logger.info("Updated task progress in sprint service", task_id=task_id, new_progress=new_progress)

            summary = TaskUpdate(
                task_id=task_id,
                progress_made=f"{progress_increase}%",
                new_status=f"{new_progress}%"
            )
            updated_tasks_summary.append(summary)
        except HTTPException as e:
            logger.error("Failed to process daily scrum update", error=str(e))
            # Decide if we should continue or fail the whole run. For now, we'll log and continue.
            continue

    logger.info("Daily scrum simulation completed", sprint_id=sprint_id, tasks_updated=len(updated_tasks_summary))

    return SimulationResult(
        message=f"Daily scrum simulation completed for sprint {sprint_id}",
        tasks_updated_count=len(updated_tasks_summary),
        updates=updated_tasks_summary,
    )