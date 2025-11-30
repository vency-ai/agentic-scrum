import os
import json
import asyncio
from typing import List, Optional, Dict
import httpx # For making HTTP requests to other services
import random # For simulating task generation
from urllib.parse import urlparse

import redis.asyncio as redis
import psycopg2
import structlog
structlog.configure([structlog.processors.JSONRenderer()])
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
import logging
from log_config import HealthCheckFilter
import logging
logging.basicConfig(level=logging.INFO)

# Suppress httpx INFO level logs for outgoing requests
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING) # httpcore is a dependency of httpx

from utils import get_db_connection, put_db_connection, close_all_db_connections, call_project_service, get_all_projects
from event_consumer import RedisConsumer
from tenacity import RetryError
from fastapi import Request, status
from fastapi.responses import JSONResponse
from circuit_breaker import CircuitBrokenError

logger = structlog.get_logger()

app = FastAPI()

@app.exception_handler(CircuitBrokenError)
async def circuit_broken_exception_handler(request: Request, exc: CircuitBrokenError):
    logger.error("Project Service circuit is open. Failing fast.", error=str(exc))
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "Project Service is temporarily unavailable. Circuit breaker is open."}
    )

# Apply filter to Uvicorn access logger
uvicorn_access_logger = logging.getLogger("uvicorn.access")
uvicorn_access_logger.addFilter(HealthCheckFilter())

# Environment variables for Redis
REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))

REDIS_STREAM_NAME = "task_update_events"
REDIS_CONSUMER_GROUP = "backlog_service_group"
REDIS_CONSUMER_NAME = os.environ.get("HOSTNAME", "backlog_service_consumer_1")

# Redis connection
redis_client = None
sprint_started_consumer = None

async def get_redis_client():
    """
    Initializes and returns a Redis client.
    """
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
            logger.error("Redis ping failed.")
            return None
    except redis.ConnectionError as e:
        logger.error("Failed to connect to Redis", error=str(e))
        return None

async def consume_task_updated_events():
    global redis_client
    if not redis_client:
        logger.error("Redis client not available for event consumption. Exiting consumer.")
        return

    try:
        await redis_client.xgroup_create(REDIS_STREAM_NAME, REDIS_CONSUMER_GROUP, id='0', mkstream=True)
        logger.info("Redis consumer group created or already exists", group=REDIS_CONSUMER_GROUP, stream=REDIS_STREAM_NAME)
    except redis.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            logger.error("Error creating Redis consumer group", error=str(e))
            return

    logger.info("Starting Redis event consumer for task updates", group=REDIS_CONSUMER_GROUP, consumer=REDIS_CONSUMER_NAME)
    while True:
        try:
            messages = await redis_client.xreadgroup(
                REDIS_CONSUMER_GROUP,
                REDIS_CONSUMER_NAME,
                {REDIS_STREAM_NAME: '>'},
                count=1,
                block=1000
            )

            for stream, message_list in messages:
                for message_id, message_data in message_list:
                    try:
                        payload_str = message_data.get('data')
                        if not payload_str:
                            logger.warning("Received message with no 'data' field", message_id=message_id)
                            await redis_client.xack(REDIS_STREAM_NAME, REDIS_CONSUMER_GROUP, message_id)
                            continue

                        event = json.loads(payload_str)
                        if event.get("event_type") == "TASK_UPDATED":
                            event_data = event.get("event_data", {})
                            task_id = event_data.get("task_id")
                            status = event_data.get("status")
                            progress = event_data.get("progress_percentage")

                            if task_id and status and progress is not None:
                                logger.info("Processing TASK_UPDATED event", task_id=task_id, status=status, progress=progress)
                                conn = None
                                try:
                                    conn = get_db_connection()
                                    cur = conn.cursor()
                                    cur.execute(
                                        "UPDATE tasks SET status = %s, progress_percentage = %s WHERE task_id = %s",
                                        (status, progress, task_id)
                                    )
                                    conn.commit()
                                    logger.info("Successfully updated task in backlog from event", task_id=task_id)
                                except (Exception, psycopg2.DatabaseError) as db_error:
                                    logger.error("Database error during task update from event", error=str(db_error), task_id=task_id)
                                    if conn:
                                        conn.rollback()
                                finally:
                                    if conn:
                                        cur.close()
                                        put_db_connection(conn)
                        
                        await redis_client.xack(REDIS_STREAM_NAME, REDIS_CONSUMER_GROUP, message_id)

                    except json.JSONDecodeError:
                        logger.error("Failed to decode JSON payload from Redis message", message_id=message_id)
                        await redis_client.xack(REDIS_STREAM_NAME, REDIS_CONSUMER_GROUP, message_id)
                    except Exception as ex:
                        logger.error("Unhandled error during event processing", error=str(ex), message_id=message_id)
                        await redis_client.xack(REDIS_STREAM_NAME, REDIS_CONSUMER_GROUP, message_id)
            
        except redis.ConnectionError as e:
            logger.error("Redis connection lost, attempting to reconnect...", error=str(e))
            redis_client = None
            await asyncio.sleep(5)
        except Exception as e:
            logger.error("Unhandled error in Redis consumer loop", error=str(e))
            await asyncio.sleep(1)

@app.on_event("startup")
async def startup_event():
    global redis_client, sprint_started_consumer
    logger.info("Backlog Service starting up...")
    redis_client = await get_redis_client()
    if redis_client:
        asyncio.create_task(consume_task_updated_events())
        sprint_started_consumer = RedisConsumer()
        logger.info("Starting SprintStarted event consumer...")
        asyncio.create_task(sprint_started_consumer.start_consuming())
    else:
        logger.error("Redis connection failed. Consumer not started.")

@app.on_event("shutdown")
async def shutdown_event():
    global sprint_started_consumer
    logger.info("Backlog Service shutting down...")
    if redis_client:
        await redis_client.close()
        logger.info("Redis client closed.")
    if sprint_started_consumer:
        sprint_started_consumer.stop()
    close_all_db_connections()

# Pydantic models for data validation
class Project(BaseModel):
    id: str
    name: str
    description: str

class Task(BaseModel):
    task_id: str
    project_id: str
    title: str
    description: str
    status: str = "unassigned" # Default status
    assigned_to: Optional[str] = None
    sprint_id: Optional[str] = None
    progress_percentage: Optional[int] = 0

import datetime
from fastapi.responses import JSONResponse

@app.get("/health", status_code=200)
def health_check():
    """Health check endpoint to verify service is running."""
    return {"status": "ok"}

def check_database_connection():
    """Checks the PostgreSQL database connection."""
    try:
        conn = get_db_connection()
        put_db_connection(conn)
        return "ok"
    except Exception as e:
        logger.error("Database connection check failed", error=str(e))
        return "error"

async def check_redis_connection():
    """Checks the Redis connection."""
    try:
        client = await get_redis_client()
        if client and await client.ping():
            return "ok"
        return "error"
    except Exception as e:
        logger.error("Redis connection check failed", error=str(e))
        return "error"

async def check_external_dependencies():
    """Checks external API dependencies."""
    statuses = {}
    # Check project-service
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://project-service.dsm.svc.cluster.local/health/ready", timeout=5)
            response.raise_for_status()
            statuses["project_service"] = "ok"
    except httpx.RequestError as e:
        logger.error("Project Service health check failed", error=str(e))
        statuses["project_service"] = "error"
    except httpx.HTTPStatusError as e:
        logger.error(f"Project Service health check returned non-2xx status: {e.response.status_code}", error=str(e))
        statuses["project_service"] = "error"
    return statuses

@app.get("/health/ready")
async def readiness_check():
    """Enhanced health check with dependency validation for backlog-service."""
    db_status = check_database_connection()
    redis_status = await check_redis_connection()
    external_apis_status = await check_external_dependencies()

    is_ready = (
        db_status == "ok" and
        redis_status == "ok"
        # Temporarily removed external_apis_status check for circuit breaker testing
        # and all(status == "ok" for status in external_apis_status.values())
    )

    health_status = {
        "service": "backlog-service",
        "status": "ready" if is_ready else "not_ready",
        "database": db_status,
        "redis": redis_status,
        "external_apis": external_apis_status,
        "timestamp": datetime.datetime.utcnow().isoformat()
    }

    status_code = 200 if is_ready else 503
    return JSONResponse(content=health_status, status_code=status_code)

@app.get("/backlogs/summary", status_code=200)
async def get_all_backlog_summaries():
    """
    Retrieves a summary of all backlogs for all projects.
    """
    logger.info("Received request to get all backlog summaries")
    conn = None
    try:
        # 1. Get all projects
        projects = await get_all_projects()
        logger.info("Projects received from project-service", projects=projects)
        if not projects:
            return []

        project_ids = [p['id'] for p in projects]

        # 2. Get backlog summaries for all projects in one query
        conn = get_db_connection()
        cur = conn.cursor()

        query = "SELECT project_id, status, COUNT(*) FROM tasks WHERE project_id = ANY(%s) GROUP BY project_id, status"
        cur.execute(query, (project_ids,))
        
        summary_data = cur.fetchall()

        # 3. Process the data
        summaries = {}
        for project_id, status, count in summary_data:
            if project_id not in summaries:
                summaries[project_id] = {
                    "project_id": project_id,
                    "total_tasks": 0,
                    "status_counts": {}
                }
            summaries[project_id]["total_tasks"] += count
            summaries[project_id]["status_counts"][status] = count
        
        # Add projects that might not have tasks yet and fetch unassigned_for_sprint_count
        for p in projects:
            project_id = p['id']
            if project_id not in summaries:
                summaries[project_id] = {
                    "project_id": project_id,
                    "total_tasks": 0,
                    "status_counts": {}
                }
            
            # Get unassigned_for_sprint_count for each project
            cur.execute("SELECT COUNT(*) FROM tasks WHERE project_id = %s AND status = 'unassigned' AND sprint_id IS NULL", (project_id,))
            unassigned_count = cur.fetchone()[0]
            summaries[project_id]["unassigned_for_sprint_count"] = unassigned_count

        logger.info("Successfully retrieved all backlog summaries", count=len(summaries))
        return list(summaries.values())

    except (Exception, psycopg2.DatabaseError) as error:
        logger.error("Database error while retrieving all backlog summaries", error=str(error))
        raise HTTPException(status_code=500, detail="Database operation failed during summary retrieval.")
    except CircuitBroken as e:
        logger.error("Project Service circuit is open in get_all_backlog_summaries.", error=str(e))
        raise HTTPException(status_code=503, detail="Project Service is temporarily unavailable. Circuit breaker is open.")
    finally:
        if conn:
            put_db_connection(conn)
            logger.info("Database connection returned to pool.")

@app.post("/backlogs/{project_id}", status_code=201)
async def generate_backlog(project_id: str):
    """
    Generates the initial task backlog for a given project.
    This endpoint will call the Project Service to get project details and simulate task creation.
    """
    logger.info("Received request to generate backlog", project_id=project_id)
    conn = None
    try:
        # 1. Call Project Service to verify project existence and get team members (simulated)
        # In a real scenario, Project Service would return team members for task assignment
        project_details = await call_project_service(project_id)
        if not project_details:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found.")

        # Simulate task generation based on project details
        # For simplicity, we'll create some generic tasks
        simulated_tasks = [
            {"title": "Setup development environment", "description": "Configure IDEs and necessary tools."},
            {"title": "Design database schema", "description": "Create ERD and define tables."},
            {"title": "Implement user authentication", "description": "Develop login/logout and registration features."},
            {"title": "Build UI for dashboard", "description": "Create the main dashboard interface."},
            {"title": "Develop API for task management", "description": "Implement CRUD operations for tasks."},
            {"title": "Write unit tests for backend", "description": "Ensure code quality with comprehensive tests."},
            {"title": "Deploy to staging environment", "description": "Set up CI/CD for automated deployments."},
            {"title": "Conduct user acceptance testing", "description": "Gather feedback from end-users."},
            {"title": "Prepare documentation", "description": "Write API docs and user guides."},
            {"title": "Refactor legacy code", "description": "Improve existing code for maintainability."},
        ]
        
        tasks_to_insert = []
        for i, task_data in enumerate(simulated_tasks):
            task_id = f"{project_id}-TASK{i+1:03d}"
            tasks_to_insert.append(Task(
                task_id=task_id,
                project_id=project_id,
                title=task_data["title"],
                description=task_data["description"],
                status="unassigned"
            ))

        conn = get_db_connection()
        cur = conn.cursor()

        # Insert tasks
        for task in tasks_to_insert:
            cur.execute(
                "INSERT INTO tasks (task_id, project_id, title, description, status, assigned_to, sprint_id, progress_percentage) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (task_id) DO UPDATE SET title = EXCLUDED.title, description = EXCLUDED.description, status = EXCLUDED.status, assigned_to = EXCLUDED.assigned_to, sprint_id = EXCLUDED.sprint_id, progress_percentage = EXCLUDED.progress_percentage;",
                (task.task_id, task.project_id, task.title, task.description, task.status, task.assigned_to, task.sprint_id, task.progress_percentage)
            )

        conn.commit()
        cur.close()
        logger.info("Successfully generated backlog", project_id=project_id, tasks_count=len(tasks_to_insert))
        return {"message": f"Backlog generated successfully for project {project_id}", "tasks_count": len(tasks_to_insert)}

    except HTTPException:
        raise # Re-raise HTTPExceptions from call_project_service
    except CircuitBroken as e:
        logger.error("Project Service circuit is open in generate_backlog.", error=str(e))
        raise HTTPException(status_code=503, detail="Project Service is temporarily unavailable. Circuit breaker is open.")
    except psycopg2.DatabaseError as error:
        logger.error("Database error while generating backlog", error=str(error))
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail="Database operation failed during backlog generation.")
    finally:
        if conn:
            put_db_connection(conn)
            logger.info("Database connection returned to pool.")

@app.get("/backlogs/{project_id}/summary", status_code=200)
def get_backlog_summary(project_id: str):
    """
    Retrieves a summary of the backlog for a specific project,
    including total tasks and counts by status.
    """
    logger.info("Received request to get backlog summary", project_id=project_id)
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Get total tasks
        cur.execute("SELECT COUNT(*) FROM tasks WHERE project_id = %s", (project_id,))
        total_tasks = cur.fetchone()[0]

        # Get tasks by status
        cur.execute("SELECT status, COUNT(*) FROM tasks WHERE project_id = %s GROUP BY status", (project_id,))
        status_counts = {row[0]: row[1] for row in cur.fetchall()}

        # Get count of tasks that are 'unassigned' and not assigned to any sprint
        cur.execute("SELECT COUNT(*) FROM tasks WHERE project_id = %s AND status = 'unassigned' AND sprint_id IS NULL", (project_id,))
        unassigned_for_sprint_count = cur.fetchone()[0]

        logger.info("Successfully retrieved backlog summary", project_id=project_id, total_tasks=total_tasks, status_counts=status_counts, unassigned_for_sprint_count=unassigned_for_sprint_count)
        return {
            "project_id": project_id,
            "total_tasks": total_tasks,
            "status_counts": status_counts,
            "unassigned_for_sprint_count": unassigned_for_sprint_count
        }

    except (Exception, psycopg2.DatabaseError) as error:
        logger.error("Database error while retrieving backlog summary", error=str(error))
        raise HTTPException(status_code=500, detail="Database operation failed during summary retrieval.")
    finally:
        if conn:
            put_db_connection(conn)
            logger.info("Database connection returned to pool.")

@app.get("/backlogs/{project_id}", status_code=200, response_model=List[Task])
def get_backlog_tasks(project_id: str, status: Optional[str] = Query(None)):
    """
    Retrieves the current list of tasks in the backlog for a specific project.
    Can be filtered by status.
    """
    logger.info("Received request to get backlog tasks", project_id=project_id, status=status)
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        query = "SELECT task_id, project_id, title, description, status, assigned_to, sprint_id, progress_percentage FROM tasks WHERE project_id = %s"
        params = [project_id]

        if status:
            query += " AND status = %s"
            params.append(status)

        cur.execute(query, params)
        tasks_data = cur.fetchall()
        cur.close()

        tasks_list = []
        for task_id, prj_id, title, desc, stat, assigned, sprint, progress in tasks_data:
            tasks_list.append(Task(
                task_id=task_id,
                project_id=prj_id,
                title=title,
                description=desc,
                status=stat,
                assigned_to=assigned,
                sprint_id=sprint,
                progress_percentage=progress
            ))

        logger.info("Successfully retrieved backlog tasks", project_id=project_id, count=len(tasks_list))
        return tasks_list

    except (Exception, psycopg2.DatabaseError) as error:
        logger.error("Database error while retrieving backlog tasks", error=str(error))
        raise HTTPException(status_code=500, detail="Database operation failed during task retrieval.")
    finally:
        if conn:
            put_db_connection(conn)
            logger.info("Database connection returned to pool.")

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    assigned_to: Optional[str] = None
    sprint_id: Optional[str] = None
    progress_percentage: Optional[int] = None

@app.put("/tasks/{task_id}", status_code=200)
def update_task(task_id: str, task_update: TaskUpdate): # Using Task model for update, but only relevant fields will be used
    """
    Updates the status or other attributes of a specific task in the backlog.
    """
    logger.info("Received request to update task", task_id=task_id, update_data=task_update.dict())
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Build dynamic update query based on provided fields
        update_fields = []
        params = []
        if task_update.title is not None:
            update_fields.append("title = %s")
            params.append(task_update.title)
        if task_update.description is not None:
            update_fields.append("description = %s")
            params.append(task_update.description)
        if task_update.status is not None:
            update_fields.append("status = %s")
            params.append(task_update.status)
            # If status is set to 'unassigned', ensure sprint_id is null unless explicitly provided
            if task_update.status == "unassigned" and 'sprint_id' not in task_update.__fields_set__:
                update_fields.append("sprint_id = NULL")
        if task_update.assigned_to is not None:
            update_fields.append("assigned_to = %s")
            params.append(task_update.assigned_to)
        if 'sprint_id' in task_update.__fields_set__:
            if task_update.sprint_id is None:
                update_fields.append("sprint_id = NULL")
            else:
                update_fields.append("sprint_id = %s")
                params.append(task_update.sprint_id)
        if task_update.progress_percentage is not None:
            update_fields.append("progress_percentage = %s")
            params.append(task_update.progress_percentage)

        if not update_fields:
            raise HTTPException(status_code=422, detail="No fields provided for update.")

        query = f"UPDATE tasks SET {', '.join(update_fields)} WHERE task_id = %s"
        params.append(task_id)

        cur.execute(query, params)
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found.")

        conn.commit()
        cur.close()
        logger.info("Successfully updated task", task_id=task_id)
        return {"message": f"Task {task_id} updated successfully"}

    except HTTPException:
        raise # Re-raise HTTPExceptions
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error("Database error while updating task", error=str(error))
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail="Database operation failed during task update.")
    finally:
        if conn:
            put_db_connection(conn)
            logger.info("Database connection returned to pool.")