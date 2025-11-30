import os
import random
import json
import asyncio
import uuid
from typing import List, Optional
from datetime import date, timedelta, datetime
import httpx # Added for external API checks

import redis.asyncio as redis
import psycopg2
import structlog
from fastapi import FastAPI, HTTPException, Query, Request, Depends
from pydantic import BaseModel
import logging
from log_config import HealthCheckFilter
from circuit_breaker import CircuitBroken

from utils import get_db_connection, put_db_connection, close_all_db_connections, call_project_service_get_project, call_backlog_service_get_tasks, call_backlog_service_update_task, call_chronicle_service_create_note, publish_event, call_project_service_get_team_members, call_chronicle_service_create_daily_scrum_report, call_chronicle_service_create_sprint_planning_report

class SprintPlanningReportTask(BaseModel):
    task_id: str
    title: str
    assigned_to: Optional[str] = None

class SprintPlanningReport(BaseModel):
    sprint_id: str
    project_id: str
    sprint_name: str
    sprint_goal: str # Added sprint_goal
    start_date: str
    end_date: str
    planned_tasks: List[str] # Changed to List[str]
from fastapi.responses import JSONResponse

logger = structlog.get_logger()

# Configure structlog to output debug messages
structlog.configure(
    processors=[
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

# Configure standard logging to output to console
logging.basicConfig(
    format="%(message)s",
    level=os.environ.get("LOG_LEVEL", "info").upper(),
    handlers=[logging.StreamHandler()],
)

# Configure a formatter for structlog
formatter = structlog.stdlib.ProcessorFormatter(
    processor=structlog.dev.ConsoleRenderer(),
    foreign_pre_chain=[
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
    ],
)

handler = logging.StreamHandler()
handler.setFormatter(formatter)

root_logger = logging.getLogger()
root_logger.addHandler(handler)
root_logger.setLevel(os.environ.get("LOG_LEVEL", "info").upper())

app = FastAPI()

@app.exception_handler(CircuitBroken)
async def circuit_broken_exception_handler(request: Request, exc: CircuitBroken):
    logger.error("Circuit breaker is open", error=str(exc))
    return JSONResponse(
        status_code=503,
        content={"detail": f"Service dependency is unavailable: {str(exc)}"},
    )

# Apply filter to Uvicorn access logger
uvicorn_access_logger = logging.getLogger("uvicorn.access")
uvicorn_access_logger.addFilter(HealthCheckFilter())

# Environment variables for Redis
REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
REDIS_STREAM_NAME = "daily_scrum_events"
TASK_UPDATED_STREAM_NAME = "task_update_events"
DSM_EVENTS_STREAM_NAME = "dsm:events" # New stream for general DSM events
REDIS_CONSUMER_GROUP = "sprint_service_group"
REDIS_CONSUMER_NAME = os.environ.get("HOSTNAME", "sprint_service_consumer_1") # Unique name for this instance

# Redis connection
redis_client = None

async def get_redis_client():
    """
    Initializes and returns a Redis client.
    If a client is already connected, it returns the existing client.
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

# Pydantic models for data validation
class SprintCreate(BaseModel):
    sprint_name: str
    duration_weeks: int

class Sprint(BaseModel):
    sprint_id: str
    project_id: str
    sprint_name: str
    start_date: date
    end_date: date
    duration_weeks: int
    status: str

class TaskInSprint(BaseModel):
    task_id: str
    title: str
    status: str
    sprint_id: Optional[str] = None
    progress_percentage: Optional[int] = 0
    assigned_to: Optional[str] = None
    assigned_to: Optional[str] = None

class SprintTaskUpdate(BaseModel):
    status: Optional[str] = None
    progress_percentage: Optional[int] = None

class SprintTaskSummary(BaseModel):
    total_tasks: int
    completed_tasks: int
    pending_tasks: int

class ProjectWithSprints(BaseModel):
    project_id: str
    sprints: List[Sprint]

class DailyScrumReport(BaseModel):
    project_id: str
    sprint_id: str
    report_date: str
    summary: str
    summary_metrics: dict
    reports: dict

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
    async with httpx.AsyncClient() as client:
        # Check project-service
        try:
            response = await client.get("http://project-service.dsm.svc.cluster.local/health/ready", timeout=5)
            response.raise_for_status()
            statuses["project_service"] = "ok"
        except httpx.RequestError as e:
            logger.error("Project Service health check failed", error=str(e))
            statuses["project_service"] = "error"
        except httpx.HTTPStatusError as e:
            logger.error(f"Project Service health check returned non-2xx status: {e.response.status_code}", error=str(e))
            statuses["project_service"] = "error"

        # Check backlog-service
        try:
            response = await client.get("http://backlog-service.dsm.svc.cluster.local/health/ready", timeout=5)
            response.raise_for_status()
            statuses["backlog_service"] = "ok"
        except httpx.RequestError as e:
            logger.error("Backlog Service health check failed", error=str(e))
            statuses["backlog_service"] = "error"
        except httpx.HTTPStatusError as e:
            logger.error(f"Backlog Service health check returned non-2xx status: {e.response.status_code}", error=str(e))
            statuses["backlog_service"] = "error"

        # Check chronicle-service
        try:
            response = await client.get("http://chronicle-service.dsm.svc.cluster.local/health/ready", timeout=5)
            response.raise_for_status()
            statuses["chronicle_service"] = "ok"
        except httpx.RequestError as e:
            logger.error("Chronicle Service health check failed", error=str(e))
            statuses["chronicle_service"] = "error"
        except httpx.HTTPStatusError as e:
            logger.error(f"Chronicle Service health check returned non-2xx status: {e.response.status_code}", error=str(e))
            statuses["chronicle_service"] = "error"
    return statuses

@app.get("/health/ready")
async def readiness_check():
    """Enhanced health check with dependency validation for sprint-service."""
    db_status = check_database_connection()
    redis_status = await check_redis_connection()
    external_apis_status = await check_external_dependencies()

    is_ready = (
        db_status == "ok" and
        redis_status == "ok" and
        all(status == "ok" for status in external_apis_status.values())
    )

    health_status = {
        "service": "sprint-service",
        "status": "ready" if is_ready else "not_ready",
        "database": db_status,
        "redis": redis_status,
        "external_apis": external_apis_status,
        "timestamp": datetime.utcnow().isoformat()
    }

    status_code = 200 if is_ready else 503
    return JSONResponse(content=health_status, status_code=status_code)

@app.get("/sprints/active", status_code=200)
async def get_active_sprint_id():
    """
    Retrieves the ID of the first active sprint found.
    Returns 404 if no active sprint is found.
    """
    logger.info("Received request to get active sprint ID")
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        query = "SELECT sprint_id FROM sprints WHERE status = 'in_progress' LIMIT 1;"
        logger.info("Executing query for active sprint", query=query)
        cur.execute(query)
        sprint_data = cur.fetchone()
        logger.info("Query result for active sprint", result=sprint_data)

        if not sprint_data:
            logger.warning("No active sprint found in database.")
            raise HTTPException(status_code=404, detail="No active sprint found.")

        active_sprint_id = sprint_data[0]
        logger.info("Found active sprint", sprint_id=active_sprint_id)
        return {"sprint_id": active_sprint_id}

    except HTTPException:
        raise # Re-raise HTTPExceptions
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error("Database error while retrieving active sprint ID", error=str(error))
        raise HTTPException(status_code=500, detail="Database operation failed during active sprint ID retrieval.")
    finally:
        if conn:
            cur.close()
            put_db_connection(conn)
            logger.info("Database connection returned to pool.")

@app.get("/sprints/active/{project_id}", status_code=200)
async def get_active_sprint_id_by_project(project_id: str):
    """
    Retrieves the ID of the active sprint for a specific project.
    Returns 404 if no active sprint is found for the given project.
    """
    logger.info("Received request to get active sprint ID for project", project_id=project_id)
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        query = "SELECT sprint_id FROM sprints WHERE project_id = %s AND status = 'in_progress' LIMIT 1;"
        logger.info("Executing query for active sprint by project", query=query, project_id=project_id)
        cur.execute(query, (project_id,))
        sprint_data = cur.fetchone()
        logger.info("Query result for active sprint by project", result=sprint_data, project_id=project_id)

        if not sprint_data:
            logger.warning("No active sprint found for project in database.", project_id=project_id)
            raise HTTPException(status_code=404, detail=f"No active sprint found for project {project_id}.")

        active_sprint_id = sprint_data[0]
        logger.info("Found active sprint for project", sprint_id=active_sprint_id, project_id=project_id)
        return {"sprint_id": active_sprint_id}

    except HTTPException:
        raise # Re-raise HTTPExceptions
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error("Database error while retrieving active sprint ID for project", error=str(error), project_id=project_id)
        raise HTTPException(status_code=500, detail=f"Database operation failed during active sprint ID retrieval for project {project_id}.")
    finally:
        if conn:
            cur.close()
            put_db_connection(conn)
            logger.info("Database connection returned to pool.")

async def consume_daily_scrum_events():
    global redis_client
    if not redis_client:
        logger.error("Redis client not available for event consumption. Exiting consumer.")
        return

    try:
        # Create consumer group if it doesn't exist
        # MKSTREAM creates the stream if it doesn't exist
        await redis_client.xgroup_create(REDIS_STREAM_NAME, REDIS_CONSUMER_GROUP, id='0', mkstream=True)
        logger.info("Redis consumer group created or already exists", group=REDIS_CONSUMER_GROUP, stream=REDIS_STREAM_NAME)
    except redis.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            logger.error("Error creating Redis consumer group", error=str(e))
            return

    logger.info("Starting Redis event consumer", group=REDIS_CONSUMER_GROUP, consumer=REDIS_CONSUMER_NAME)
    while True:
        try:
            # Read events from the stream
            # Block for 1 second if no new messages, then retry
            messages = await redis_client.xreadgroup(
                REDIS_CONSUMER_GROUP,
                REDIS_CONSUMER_NAME,
                {REDIS_STREAM_NAME: '>'}, # Read new messages
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

                        event_payload = json.loads(payload_str)
                        event_type = event_payload.get("event_type")
                        task_id = event_payload.get("task_id")
                        new_total_progress = event_payload.get("new_total_progress")
                        sprint_id = event_payload.get("sprint_id")

                        if event_type == "TASK_PROGRESSED" and task_id and new_total_progress is not None and sprint_id:
                            logger.info("Processing TASK_PROGRESSED event", task_id=task_id, new_progress=new_total_progress, sprint_id=sprint_id)
                            conn = None
                            try:
                                conn = get_db_connection()
                                cur = conn.cursor()

                                # Update task progress in SprintDB
                                cur.execute(
                                    """
                                    UPDATE tasks
                                    SET progress_percentage = %s,
                                        status = CASE
                                            WHEN %s >= 100 THEN 'completed'
                                            ELSE status
                                        END
                                    WHERE task_id = %s AND sprint_id = %s;
                                    """,
                                    (new_total_progress, new_total_progress, task_id, sprint_id)
                                )
                                if cur.rowcount == 0:
                                    logger.warning("Task not found in SprintDB for update or not assigned to sprint", task_id=task_id, sprint_id=sprint_id)
                                else:
                                    # If the update was successful, publish a TASK_UPDATED event
                                    new_status = "completed" if new_total_progress >= 100 else "in_progress"
                                    project_id = sprint_id.split('-')[0]

                                    # Retrieve assigned_to for the task
                                    cur.execute("SELECT assigned_to FROM tasks WHERE task_id = %s AND sprint_id = %s;", (task_id, sprint_id))
                                    assigned_to_employee_id = cur.fetchone()[0] if cur.rowcount > 0 else None
                                    
                                    task_updated_event = {
                                        "event_id": str(uuid.uuid4()),
                                        "event_type": "TASK_UPDATED",
                                        "timestamp": datetime.utcnow().isoformat(),
                                        "aggregate_id": task_id,
                                        "aggregate_type": "Task",
                                        "event_data": {
                                            "task_id": task_id,
                                            "project_id": project_id,
                                            "sprint_id": sprint_id,
                                            "status": new_status,
                                            "progress_percentage": new_total_progress,
                                            "updated_at": datetime.utcnow().isoformat(),
                                            "assigned_to": assigned_to_employee_id
                                        },
                                        "metadata": {
                                            "source_service": "SprintService",
                                            "correlation_id": str(uuid.uuid4()) # Or use a correlation ID from the incoming event if available
                                        }
                                    }
                                    
                                    await redis_client.xadd(TASK_UPDATED_STREAM_NAME, {"data": json.dumps(task_updated_event)})
                                    logger.info("Published TASK_UPDATED event", event_payload=task_updated_event)

                                    
                                conn.commit()
                                logger.info("Task progress updated in SprintDB", task_id=task_id, new_progress=new_total_progress)

                            except (Exception, psycopg2.DatabaseError) as db_error:
                                logger.error("Database error during task update from event", error=str(db_error), task_id=task_id)
                                if conn:
                                    conn.rollback()
                            finally:
                                if conn:
                                    cur.close()
                                    put_db_connection(conn)
                                    logger.info("Database connection returned to pool after event processing.")
                        else:
                            logger.warning("Received unhandled event type or incomplete payload", event_type=event_type, payload=event_payload)

                        # Acknowledge the message after processing
                        await redis_client.xack(REDIS_STREAM_NAME, REDIS_CONSUMER_GROUP, message_id)
                        logger.debug("Acknowledged Redis message", message_id=message_id)

                    except json.JSONDecodeError:
                        logger.error("Failed to decode JSON payload from Redis message", message_id=message_id, raw_data=message_data.get('data'))
                        await redis_client.xack(REDIS_STREAM_NAME, REDIS_CONSUMER_GROUP, message_id) # Acknowledge malformed messages to avoid reprocessing
                    except Exception as ex:
                        logger.error("Unhandled error during event processing", error=str(ex), message_id=message_id)
                        # Depending on error, might NACK or just ACK and log for further investigation
                        await redis_client.xack(REDIS_STREAM_NAME, REDIS_CONSUMER_GROUP, message_id) # For now, ACK to prevent reprocessing on unhandled errors
            
        except redis.ConnectionError as e:
            logger.error("Redis connection lost, attempting to reconnect...", error=str(e))
            redis_client = None # Reset client to force re-initialization
            await asyncio.sleep(5) # Wait before retrying connection
        except Exception as e:
            logger.error("Unhandled error in Redis consumer loop", error=str(e))
            await asyncio.sleep(1) # Prevent tight loop on persistent errors

@app.on_event("startup")
async def startup_event():
    global redis_client
    logger.info("Sprint Service starting up...")
    redis_client = await get_redis_client() # Initialize Redis client on startup
    if redis_client:
        asyncio.create_task(consume_daily_scrum_events()) # Start consumer as a background task
    else:
        logger.error("Redis connection failed. Consumer not started.")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Sprint Service shutting down...")
    if redis_client:
        await redis_client.close()
        logger.info("Redis client closed.")
    close_all_db_connections()

@app.post("/sprints/{project_id}", status_code=201)
async def start_new_sprint(project_id: str, sprint_create: SprintCreate):
    """
    Starts a new sprint for a given project.
    This endpoint will internally communicate with the Project Service to verify project existence
    and with the Backlog Service to retrieve unassigned tasks and assign a selection of them to the new sprint.
    It will also publish a SprintStarted event.
    """
    logger.info("Received request to start new sprint", project_id=project_id, sprint_name=sprint_create.sprint_name)
    conn = None
    correlation_id = str(uuid.uuid4())
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Create sprints table if it doesn't exist
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sprints (
                sprint_id VARCHAR(20) PRIMARY KEY,
                project_id VARCHAR(10) NOT NULL,
                sprint_name VARCHAR(255) NOT NULL,
                start_date DATE NOT NULL,
                end_date DATE NOT NULL,
                duration_weeks INTEGER NOT NULL,
                status VARCHAR(50) NOT NULL
            );
        """)
        # Create tasks table if it doesn't exist (for Sprint Service's own task state)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id VARCHAR(50) PRIMARY KEY,
                sprint_id VARCHAR(20) NOT NULL,
                title VARCHAR(255) NOT NULL,
                status VARCHAR(50) NOT NULL,
                progress_percentage INTEGER DEFAULT 0,
                assigned_to VARCHAR(50),
                FOREIGN KEY (sprint_id) REFERENCES sprints(sprint_id)
            );
        """)

        # Check if a sprint is already in progress for this project (local check)
        cur.execute("SELECT sprint_id FROM sprints WHERE project_id = %s AND status = 'in_progress'", (project_id,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail=f"A sprint is already in progress for project {project_id}.")

        # Retrieve unassigned tasks from Backlog Service BEFORE creating the sprint
        unassigned_tasks = await call_backlog_service_get_tasks(project_id, status="unassigned")
        logger.info("Retrieved unassigned tasks from backlog service", count=len(unassigned_tasks))

        if not unassigned_tasks:
            logger.warning("No unassigned tasks found for project. Cannot create sprint.", project_id=project_id)
            raise HTTPException(status_code=409, detail=f"Cannot create sprint: No unassigned tasks found for project {project_id}.")

        # Generate a unique sprint ID
        cur.execute("SELECT COUNT(*) FROM sprints WHERE project_id = %s", (project_id,))
        sprint_count = cur.fetchone()[0]
        sprint_id = f"{project_id}-S{sprint_count + 1:02d}"

        start_date = date.today()
        end_date = start_date + timedelta(weeks=sprint_create.duration_weeks)

        # Insert new sprint into sprint-db
        cur.execute(
            "INSERT INTO sprints (sprint_id, project_id, sprint_name, start_date, end_date, duration_weeks, status) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (sprint_id, project_id, sprint_create.sprint_name, start_date, end_date, sprint_create.duration_weeks, "in_progress")
        )
        conn.commit() # Commit sprint creation to sprint-db
        logger.info("Successfully started new sprint in database", sprint_id=sprint_id)

        # Publish SprintStarted event immediately after local DB commit
        sprint_started_event = {
            "event_id": str(uuid.uuid4()),
            "event_type": "SprintStarted",
            "aggregate_id": sprint_id,
            "payload": {
                "sprint_id": sprint_id,
                "project_id": project_id,
                "sprint_name": sprint_create.sprint_name,
                "start_date": start_date,
                "end_date": end_date,
                "tasks": [] # Tasks will be assigned by backlog-service consumer
            },
            "timestamp": datetime.utcnow().isoformat(),
            "correlation_id": correlation_id
        }
        await publish_event(redis_client, DSM_EVENTS_STREAM_NAME, sprint_started_event)
        logger.info("Published SprintStarted event", sprint_id=sprint_id)

        # --- Synchronous calls to other services (now optional/best-effort after event) ---
        assigned_task_ids = []
        try:
            # 1. Verify project existence via Project Service (now after event publish)
            project_details = await call_project_service_get_project(project_id)
            if not project_details:
                logger.error("Project Service is unavailable or project not found during synchronous call.", project_id=project_id)
                raise HTTPException(status_code=503, detail="Project Service is currently unavailable or project not found.")

            # Retrieve team members for the project
            team_members_data = await call_project_service_get_team_members(project_id)
            team_member_ids = [member["id"] for member in team_members_data] if team_members_data else []
            logger.info("Retrieved team members for project", project_id=project_id, team_members=team_member_ids, count=len(team_member_ids))

            if not team_member_ids:
                logger.warning("No team members found for project. Tasks will be assigned to sprint but not to individuals.", project_id=project_id)

            assigned_task_ids = []
            team_member_index = 0

            for task in unassigned_tasks:
                task_id = task["task_id"]
                existing_assigned_to = task.get("assigned_to") # Get existing assigned_to from backlog task

                assigned_to_employee_id = existing_assigned_to # Default to existing

                if not assigned_to_employee_id and team_member_ids: # If no existing assignment, and team members are available
                    assigned_to_employee_id = team_member_ids[team_member_index]
                    team_member_index = (team_member_index + 1) % len(team_member_ids)
                    logger.info("Assigning task to new employee via round-robin", task_id=task_id, employee_id=assigned_to_employee_id)
                elif assigned_to_employee_id:
                    logger.info("Task already has an assigned employee, retaining assignment", task_id=task_id, employee_id=assigned_to_employee_id)
                else:
                    logger.warning("No team members available for assignment, task will remain unassigned to an individual.", task_id=task_id)

                assigned_task_ids.append(task_id)
                # Insert task into Sprint Service's own tasks table
                cur.execute(
                    "INSERT INTO tasks (task_id, sprint_id, title, status, progress_percentage, assigned_to) VALUES (%s, %s, %s, %s, %s, %s)",
                    (task_id, sprint_id, task["title"], "assigned_to_sprint", 0, assigned_to_employee_id) # Initial progress 0
                )
                # [SAFEGUARD] Keep synchronous call for backward compatibility during transition
                await call_backlog_service_update_task(
                    task_id,
                    {"status": "assigned_to_sprint", "sprint_id": sprint_id, "assigned_to": assigned_to_employee_id}
                )

                # Publish TASK_UPDATED event for each assigned task
                task_updated_event = {
                    "event_id": str(uuid.uuid4()),
                    "event_type": "TASK_UPDATED",
                    "timestamp": datetime.utcnow().isoformat(),
                    "aggregate_id": task_id,
                    "aggregate_type": "Task",
                    "event_data": {
                        "task_id": task_id,
                        "project_id": project_id,
                        "sprint_id": sprint_id,
                        "status": "assigned_to_sprint",
                        "progress_percentage": 0,
                        "updated_at": datetime.utcnow().isoformat(),
                        "assigned_to": assigned_to_employee_id
                    },
                    "metadata": {
                        "source_service": "SprintService",
                        "correlation_id": correlation_id
                    }
                }
                await publish_event(redis_client, TASK_UPDATED_STREAM_NAME, task_updated_event)
                logger.info("Published TASK_UPDATED event for assigned task", task_id=task_id, employee_id=assigned_to_employee_id)

            conn.commit() # Commit tasks assigned to sprint
            logger.info("Successfully assigned tasks to sprint in database", sprint_id=sprint_id, assigned_tasks_count=len(assigned_task_ids))

            # --- NEW: Generate and send Sprint Planning Report to Chronicle Service ---
            planned_task_ids_for_report = [
                task["task_id"]
                for task in unassigned_tasks # Use the original unassigned_tasks list, as these are the 'planned' tasks
            ]

            sprint_planning_report_payload = SprintPlanningReport(
                sprint_id=sprint_id,
                project_id=project_id,
                sprint_name=sprint_create.sprint_name,
                sprint_goal=f"Complete all assigned tasks for sprint {sprint_id}.", # Added sprint_goal
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                planned_tasks=planned_task_ids_for_report # Changed to list of task IDs
            ).dict()

            try:
                chronicle_response = await call_chronicle_service_create_sprint_planning_report(sprint_planning_report_payload)
                if chronicle_response and "report_id" in chronicle_response:
                    logger.info("Successfully published sprint planning report to Chronicle Service", sprint_id=sprint_id, report_id=chronicle_response["report_id"])
                else:
                    logger.warning("Failed to publish sprint planning report to Chronicle Service", sprint_id=sprint_id, response=chronicle_response)
            except Exception as e:
                logger.error("Error publishing sprint planning report to Chronicle Service", sprint_id=sprint_id, error=str(e))
                # IMPORTANT: Do NOT re-raise or fail sprint creation. Log and continue.

        except HTTPException as e:
            # Re-raise HTTPExceptions with status code 409 or 503 directly
            if e.status_code == 409 or e.status_code == 503:
                raise
            logger.error("Synchronous call to Project/Backlog Service failed after event publish", error=str(e), project_id=project_id, detail=e.detail)
            # Do not rollback sprint creation, as it's already committed and event published
            return {
                "message": f"Sprint '{sprint_create.sprint_name}' started successfully for project {project_id}, but synchronous task assignment failed.",
                "sprint_id": sprint_id,
                "assigned_tasks_count": len(assigned_task_ids),
                "warnings": [f"Synchronous task assignment failed: {e.detail}"]
            }
        except Exception as e:
            error_msg = str(e) if str(e) else repr(e)
            logger.error("An unexpected error occurred during synchronous task assignment", error=error_msg, project_id=project_id)
            return {
                "message": f"Sprint '{sprint_create.sprint_name}' started successfully for project {project_id}, but an unexpected error occurred during task assignment.",
                "sprint_id": sprint_id,
                "assigned_tasks_count": len(assigned_task_ids),
                "warnings": [f"Unexpected error during task assignment: {error_msg}"]
            }

        return {
            "message": f"Sprint '{sprint_create.sprint_name}' started successfully for project {project_id}",
            "sprint_id": sprint_id,
            "assigned_tasks_count": len(assigned_task_ids)
        }

    except HTTPException:
        raise
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error("Database error during initial sprint creation", error=str(error))
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database operation failed during initial sprint creation: {error}")
    finally:
        if conn:
            cur.close()
            put_db_connection(conn)
            logger.info("Database connection returned to pool.")

@app.get("/sprints/list_projects", status_code=200, response_model=List[ProjectWithSprints])
async def get_projects_with_sprints():
    """
    Retrieves a list of unique project IDs that have associated sprints, along with their sprint details.
    """
    logger.info("Received request to get projects with sprints and their details")
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Fetch all sprints to group them by project_id
        cur.execute("SELECT sprint_id, project_id, sprint_name, start_date, end_date, duration_weeks, status FROM sprints ORDER BY project_id, start_date DESC;")
        all_sprints_data = cur.fetchall()

        projects_map = {}
        for s_id, p_id, s_name, s_start, s_end, s_duration, s_status in all_sprints_data:
            start_date = s_start.date() if hasattr(s_start, 'date') else s_start
            end_date = s_end.date() if hasattr(s_end, 'date') else s_end
            
            sprint = Sprint(
                sprint_id=s_id,
                project_id=p_id,
                sprint_name=s_name,
                start_date=start_date,
                end_date=end_date,
                duration_weeks=s_duration,
                status=s_status
            )
            if p_id not in projects_map:
                projects_map[p_id] = ProjectWithSprints(project_id=p_id, sprints=[])
            projects_map[p_id].sprints.append(sprint)

        projects_list = list(projects_map.values())
        projects_list.sort(key=lambda p: p.project_id) # Sort by project_id for consistent output

        logger.info("Successfully retrieved projects with sprints", count=len(projects_list))
        return projects_list

    except (Exception, psycopg2.DatabaseError) as error:
        logger.error("Database error while retrieving projects with sprints", error=str(error))
        raise HTTPException(status_code=500, detail="Database operation failed during retrieval of projects with sprints.")
    finally:
        if conn:
            cur.close()
            put_db_connection(conn)
            logger.info("Database connection returned to pool.")

@app.get("/sprints/{sprint_id}", status_code=200)
async def get_sprint_details(sprint_id: str):
    """
    Retrieves the details of a specific sprint, including its assigned tasks.
    """
    logger.info("Received request to get sprint details", sprint_id=sprint_id)
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT sprint_id, project_id, sprint_name, start_date, end_date, duration_weeks, status FROM sprints WHERE sprint_id = %s", (sprint_id,))
        sprint_data = cur.fetchone()
        if not sprint_data:
            raise HTTPException(status_code=404, detail=f"Sprint {sprint_id} not found.")

        # Convert datetime to date if needed
        start_date = sprint_data[3].date() if hasattr(sprint_data[3], 'date') else sprint_data[3]
        end_date = sprint_data[4].date() if hasattr(sprint_data[4], 'date') else sprint_data[4]
        
        sprint = Sprint(
            sprint_id=sprint_data[0],
            project_id=sprint_data[1],
            sprint_name=sprint_data[2],
            start_date=start_date,
            end_date=end_date,
            duration_weeks=sprint_data[5],
            status=sprint_data[6]
        )

        # Get tasks assigned to this sprint directly from the database
        cur.execute("SELECT task_id, title, status, progress_percentage, sprint_id, assigned_to FROM tasks WHERE sprint_id = %s", (sprint.sprint_id,))
        tasks_data = cur.fetchall()
        
        filtered_tasks = [
            TaskInSprint(
                task_id=row[0],
                title=row[1],
                status=row[2],
                progress_percentage=row[3],
                sprint_id=row[4],
                assigned_to=row[5]
            ) for row in tasks_data
        ]

        logger.info("Successfully retrieved sprint details", sprint_id=sprint_id, tasks_count=len(filtered_tasks))
        return {"sprint": sprint, "tasks": filtered_tasks}

    except HTTPException:
        raise # Re-raise HTTPExceptions
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error("Database error while retrieving sprint details", error=str(error))
        raise HTTPException(status_code=500, detail="Database operation failed during sprint details retrieval.")
    finally:
        if conn:
            cur.close()
            put_db_connection(conn)
            logger.info("Database connection returned to pool.")

@app.get("/sprints/{sprint_id}/tasks", status_code=200, response_model=List[TaskInSprint])
async def get_sprint_tasks(sprint_id: str):
    """
    Retrieves all tasks for a specific sprint.
    """
    logger.info("Received request to get tasks for sprint", sprint_id=sprint_id)
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT task_id, title, status, progress_percentage, sprint_id, assigned_to FROM tasks WHERE sprint_id = %s", (sprint_id,))
        tasks_data = cur.fetchall()

        tasks_list = [
            TaskInSprint(
                task_id=row[0],
                title=row[1],
                status=row[2],
                progress_percentage=row[3],
                sprint_id=row[4],
                assigned_to=row[5]
            ) for row in tasks_data
        ]

        logger.info("Successfully retrieved tasks for sprint", sprint_id=sprint_id, tasks_count=len(tasks_list))
        return tasks_list

    except (Exception, psycopg2.DatabaseError) as error:
        logger.error("Database error while retrieving tasks for sprint", error=str(error))
        raise HTTPException(status_code=500, detail="Database operation failed during task retrieval for sprint.")
    finally:
        if conn:
            cur.close()
            put_db_connection(conn)
            logger.info("Database connection returned to pool.")

@app.get("/sprints/by-project/{project_id}", status_code=200, response_model=List[Sprint])
async def get_sprints_by_project(project_id: str, status: Optional[str] = Query(None, description="Filter sprints by status (e.g., 'in_progress', 'completed')")):
    """
    Retrieves a list of sprints for a given project, ordered by start date (newest first).
    Optionally filters by status.
    """
    logger.info("Received request to get sprints by project", project_id=project_id, status=status)
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        query = "SELECT sprint_id, project_id, sprint_name, start_date, end_date, duration_weeks, status FROM sprints WHERE project_id = %s"
        params = [project_id]

        if status:
            query += " AND status = %s"
            params.append(status)

        query += " ORDER BY start_date DESC"

        cur.execute(query, tuple(params))
        sprints_data = cur.fetchall()
        
        sprints_list = []
        for s_id, p_id, s_name, s_start, s_end, s_duration, s_status in sprints_data:
            # Convert datetime to date if needed
            start_date = s_start.date() if hasattr(s_start, 'date') else s_start
            end_date = s_end.date() if hasattr(s_end, 'date') else s_end
            
            sprints_list.append(Sprint(
                sprint_id=s_id,
                project_id=p_id,
                sprint_name=s_name,
                start_date=start_date,
                end_date=end_date,
                duration_weeks=s_duration,
                status=s_status
            ))

        logger.info("Successfully retrieved sprints for project", project_id=project_id, count=len(sprints_list), status_filter=status)
        return sprints_list

    except (Exception, psycopg2.DatabaseError) as error:
        logger.error("Database error while retrieving sprints by project", error=str(error))
        raise HTTPException(status_code=500, detail="Database operation failed during sprint retrieval by project.")
    finally:
        if conn:
            cur.close()
            put_db_connection(conn)
            logger.info("Database connection returned to pool.")

@app.get("/sprints/{sprint_id}/tasks", status_code=200, response_model=List[TaskInSprint])
async def get_sprint_tasks(sprint_id: str):
    """
    Retrieves all tasks for a specific sprint.
    """
    logger.info("Received request to get tasks for sprint", sprint_id=sprint_id)
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT task_id, title, status, progress_percentage, sprint_id, assigned_to FROM tasks WHERE sprint_id = %s", (sprint_id,))
        tasks_data = cur.fetchall()

        tasks_list = [
            TaskInSprint(
                task_id=row[0],
                title=row[1],
                status=row[2],
                progress_percentage=row[3],
                sprint_id=row[4],
                assigned_to=row[5]
            ) for row in tasks_data
        ]

        logger.info("Successfully retrieved tasks for sprint", sprint_id=sprint_id, tasks_count=len(tasks_list))
        return tasks_list

    except (Exception, psycopg2.DatabaseError) as error:
        logger.error("Database error while retrieving tasks for sprint", error=str(error))
        raise HTTPException(status_code=500, detail="Database operation failed during task retrieval for sprint.")
    finally:
        if conn:
            cur.close()
            put_db_connection(conn)
            logger.info("Database connection returned to pool.")

@app.get("/sprints/by-project/{project_id}", status_code=200, response_model=List[Sprint])
async def get_sprints_by_project(project_id: str, status: Optional[str] = Query(None, description="Filter sprints by status (e.g., 'in_progress', 'completed')")):
    """
    Retrieves a list of sprints for a given project, ordered by start date (newest first).
    Optionally filters by status.
    """
    logger.info("Received request to get sprints by project", project_id=project_id, status=status)
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        query = "SELECT sprint_id, project_id, sprint_name, start_date, end_date, duration_weeks, status FROM sprints WHERE project_id = %s"
        params = [project_id]

        if status:
            query += " AND status = %s"
            params.append(status)

        query += " ORDER BY start_date DESC"

        cur.execute(query, tuple(params))
        sprints_data = cur.fetchall()
        
        sprints_list = []
        for s_id, p_id, s_name, s_start, s_end, s_duration, s_status in sprints_data:
            # Convert datetime to date if needed
            start_date = s_start.date() if hasattr(s_start, 'date') else s_start
            end_date = s_end.date() if hasattr(s_end, 'date') else s_end
            
            sprints_list.append(Sprint(
                sprint_id=s_id,
                project_id=p_id,
                sprint_name=s_name,
                start_date=start_date,
                end_date=end_date,
                duration_weeks=s_duration,
                status=s_status
            ))

        logger.info("Successfully retrieved sprints for project", project_id=project_id, count=len(sprints_list), status_filter=status)
        return sprints_list

    except (Exception, psycopg2.DatabaseError) as error:
        logger.error("Database error while retrieving sprints by project", error=str(error))
        raise HTTPException(status_code=500, detail="Database operation failed during sprint retrieval by project.")
    finally:
        if conn:
            cur.close()
            put_db_connection(conn)
            logger.info("Database connection returned to pool.")

@app.post("/tasks/{task_id}/progress", status_code=200)
async def update_task_progress(task_id: str, task_update: SprintTaskUpdate):
    """
    Updates the progress or status of a specific task within a sprint.
    This endpoint is primarily intended for use by the Daily Scrum Service.
    """
    logger.info("Received request to update task progress", task_id=task_id, update_data=task_update.dict())
    conn = None
    try:
        update_data_dict = {}
        if task_update.status is not None:
            update_data_dict["status"] = task_update.status
        if task_update.progress_percentage is not None:
            update_data_dict["progress_percentage"] = task_update.progress_percentage

        if not update_data_dict:
            raise HTTPException(status_code=422, detail="No fields provided for update.")

        conn = get_db_connection()
        cur = conn.cursor()

        # Update task progress in SprintDB directly
        set_clauses = []
        params = []
        if "status" in update_data_dict:
            set_clauses.append("status = %s")
            params.append(update_data_dict["status"])
        if "progress_percentage" in update_data_dict:
            set_clauses.append("progress_percentage = %s")
            params.append(update_data_dict["progress_percentage"])

        if not set_clauses:
            raise HTTPException(status_code=422, detail="No valid fields to update.")

        query = f"UPDATE tasks SET {', '.join(set_clauses)} WHERE task_id = %s;"
        params.append(task_id)

        cur.execute(query, tuple(params))
        if cur.rowcount == 0:
            logger.warning("Task not found in SprintDB for direct update", task_id=task_id)
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found in SprintDB.")
        conn.commit()

        # If the update was successful, also call the backlog service to sync the data
        backlog_update_payload = {}
        if "status" in update_data_dict:
            backlog_update_payload["status"] = update_data_dict["status"]
        if "progress_percentage" in update_data_dict:
            backlog_update_payload["progress_percentage"] = update_data_dict["progress_percentage"]
            # Determine status based on progress if not explicitly set
            if "status" not in backlog_update_payload:
                backlog_update_payload["status"] = "completed" if update_data_dict["progress_percentage"] >= 100 else "in_progress"

        # If the update was successful, publish a TASK_UPDATED event
        if update_data_dict:
            # Determine status based on progress if not explicitly set
            current_status = update_data_dict.get("status")
            current_progress = update_data_dict.get("progress_percentage")

            if current_progress is not None:
                new_status = "completed" if current_progress >= 100 else "in_progress"
            else:
                # If only status was updated, use that
                new_status = current_status if current_status else "in_progress" # Default if neither is set

            # Retrieve sprint_id, project_id, and assigned_to for the task
            cur.execute("SELECT sprint_id, assigned_to FROM tasks WHERE task_id = %s;", (task_id,))
            task_data = cur.fetchone()
            if task_data:
                sprint_id = task_data[0]
                assigned_to_employee_id = task_data[1]
                project_id = sprint_id.split('-')[0]
            else:
                logger.warning("Could not find sprint_id or assigned_to for task when publishing TASK_UPDATED event", task_id=task_id)
                sprint_id = None
                project_id = None
                assigned_to_employee_id = None

            task_updated_event = {
                "event_id": str(uuid.uuid4()),
                "event_type": "TASK_UPDATED",
                "timestamp": datetime.utcnow().isoformat(),
                "aggregate_id": task_id,
                "aggregate_type": "Task",
                "event_data": {
                    "task_id": task_id,
                    "project_id": project_id,
                    "sprint_id": sprint_id,
                    "status": new_status,
                    "progress_percentage": current_progress,
                    "updated_at": datetime.utcnow().isoformat(),
                    "assigned_to": assigned_to_employee_id
                },
                "metadata": {
                    "source_service": "SprintService",
                    "correlation_id": str(uuid.uuid4())
                }
            }
            await redis_client.xadd(TASK_UPDATED_STREAM_NAME, {"data": json.dumps(task_updated_event)})
            logger.info("Published TASK_UPDATED event from update_task_progress", event_payload=task_updated_event)

        

        logger.info("Successfully updated task progress in SprintDB directly", task_id=task_id, update_data=update_data_dict)
        return {"message": f"Task {task_id} progress updated successfully in SprintDB"}

    except HTTPException:
        raise # Re-raise HTTPExceptions
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error("Database error while updating task progress directly", error=str(error))
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail="Operation failed during direct task progress update.")
    finally:
        if conn:
            cur.close()
            put_db_connection(conn)
            logger.info("Database connection returned to pool.")

@app.post("/sprints/{sprint_id}/close", status_code=200)
async def close_sprint(sprint_id: str):
    """
    Initiates the closure process for a specified sprint.
    Checks task completion, updates sprint status, moves uncompleted tasks,
    and generates a retrospective report in the Chronicle Service.
    """
    logger.info("Received request to close sprint", sprint_id=sprint_id)

    # --- Step 1: Validate Sprint and Get Initial Data ---
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT project_id, sprint_name, start_date, end_date, duration_weeks, status FROM sprints WHERE sprint_id = %s;", (sprint_id,))
            sprint_data = cur.fetchone()
            if not sprint_data:
                raise HTTPException(status_code=404, detail=f"Sprint {sprint_id} not found.")
            
            project_id, sprint_name, start_date, end_date, duration_weeks, current_status = sprint_data
            if current_status != "in_progress":
                raise HTTPException(status_code=409, detail=f"Sprint {sprint_id} is not in 'in_progress' status. Current status: {current_status}")
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error("Database error during sprint validation", error=str(error), sprint_id=sprint_id)
        raise HTTPException(status_code=500, detail=f"Database error during sprint validation: {error}")
    finally:
        if conn:
            put_db_connection(conn)

    # --- Step 2: Analyze Tasks (Async) ---
    tasks_in_sprint = await get_sprint_tasks(sprint_id)
    completed_tasks_count = sum(1 for task in tasks_in_sprint if task.progress_percentage == 100)
    uncompleted_tasks = [task for task in tasks_in_sprint if task.progress_percentage < 100]
    uncompleted_tasks_count = len(uncompleted_tasks)
    
    # --- Step 3: Update Databases and Move Tasks ---
    tasks_moved_to_backlog_count = 0
    status_updated_to = ""

    if uncompleted_tasks_count > 0:
        logger.info("Sprint has uncompleted tasks, moving them to backlog", sprint_id=sprint_id, uncompleted_tasks_count=uncompleted_tasks_count)
        for task in uncompleted_tasks:
            try:
                await call_backlog_service_update_task(task.task_id, {"status": "unassigned", "sprint_id": None})
                tasks_moved_to_backlog_count += 1
                logger.info("Moved task to backlog", task_id=task.task_id, sprint_id=sprint_id)
            except HTTPException as e:
                logger.error("Failed to move task to backlog", task_id=task.task_id, error=str(e))
        status_updated_to = "closed_with_pending_tasks"
    else:
        status_updated_to = "completed"

    # Update local sprint status and clean up tasks table
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("UPDATE sprints SET status = %s WHERE sprint_id = %s;", (status_updated_to, sprint_id))
            logger.info(f"Sprint status updated to '{status_updated_to}'", sprint_id=sprint_id)
            
            cur.execute("DELETE FROM tasks WHERE sprint_id = %s;", (sprint_id,))
            logger.info("Deleted tasks from sprint service's local table", sprint_id=sprint_id)
        conn.commit()
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error("Database error during sprint status update", error=str(error), sprint_id=sprint_id)
        if conn: conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error during sprint status update: {error}")
    finally:
        if conn:
            put_db_connection(conn)

    # --- Step 4: Generate and Publish Retrospective Report (Async) ---
    logger.info("Generating retrospective report", sprint_id=sprint_id)

    # Categorize tasks for action items
    in_progress_tasks_count = sum(1 for task in tasks_in_sprint if task.progress_percentage > 0 and task.progress_percentage < 100)
    open_tasks_count = sum(1 for task in tasks_in_sprint if task.progress_percentage == 0 or task.status in ["not_started", "assigned_to_sprint"])

    what_went_well = f"Successfully completed {completed_tasks_count} tasks." if completed_tasks_count > 0 else "No tasks were completed."
    what_could_be_improved = "Continue current practices."
    
    generated_action_items = []
    if completed_tasks_count > 0:
        generated_action_items.append({"description": f"Review {completed_tasks_count} tasks that were completed.", "status": "open"})
    if in_progress_tasks_count > 0:
        generated_action_items.append({"description": f"Address {in_progress_tasks_count} tasks that are still in progress.", "status": "open"})
        what_could_be_improved = f"Address the {in_progress_tasks_count} tasks that are still in progress."
    if open_tasks_count > 0:
        generated_action_items.append({"description": f"Investigate {open_tasks_count} tasks that were not started.", "status": "open"})
        if not what_could_be_improved or what_could_be_improved == "Continue current practices.":
            what_could_be_improved = f"Investigate the {open_tasks_count} tasks that were not started."
        else:
            what_could_be_improved += f" Also, investigate the {open_tasks_count} tasks that were not started."

    facilitator_id = "EMP_FACILITATOR"
    attendees = ["EMP_ATTENDEE_1", "EMP_ATTENDEE_2"]

    # Format tasks_summary
    tasks_summary_list = []
    for task in tasks_in_sprint:
        tasks_summary_list.append({
            "description": task.title, # Assuming title is the description
            "status": task.status,
            "task_id": task.task_id,
            "employee_id": task.assigned_to if task.assigned_to else "unassigned",
            "progress_percentage": task.progress_percentage
        })

    retrospective_report_id = None
    try:
        chronicle_response = await call_chronicle_service_create_note(
            project_id=project_id, sprint_id=sprint_id, sprint_name=sprint_name,
            start_date=start_date, end_date=end_date, duration_weeks=duration_weeks,
            what_went_well=what_went_well, what_could_be_improved=what_could_be_improved,
            action_items=generated_action_items, facilitator_id=facilitator_id,
            attendees=attendees, tasks_summary=tasks_summary_list
        )
        if chronicle_response and "retrospective_id" in chronicle_response:
            retrospective_report_id = chronicle_response["retrospective_id"]
            logger.info("Successfully published retrospective report", sprint_id=sprint_id, report_id=retrospective_report_id)
        else:
            logger.warning("Failed to publish retrospective report", sprint_id=sprint_id, response=chronicle_response)
    except Exception as e:
        logger.error("Error publishing retrospective report", sprint_id=sprint_id, error=str(e))


    return {
        "message": f"Sprint closure processed for {sprint_id}.",
        "sprint_id": sprint_id,
        "status_updated_to": status_updated_to,
        "completed_tasks_count": completed_tasks_count,
        "uncompleted_tasks_moved_to_backlog_count": tasks_moved_to_backlog_count,
        "retrospective_report_id": retrospective_report_id
    }


@app.get("/sprints/{sprint_id}/task-summary", status_code=200, response_model=SprintTaskSummary)
async def get_sprint_task_summary(sprint_id: str):
    """
    Retrieves a summary of task statistics for a specific sprint.
    """
    logger.info("Received request to get task summary for sprint", sprint_id=sprint_id)
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Check if sprint exists
        cur.execute("SELECT sprint_id FROM sprints WHERE sprint_id = %s", (sprint_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail=f"Sprint {sprint_id} not found.")

        # Get total tasks
        cur.execute("SELECT COUNT(*) FROM tasks WHERE sprint_id = %s", (sprint_id,))
        total_tasks = cur.fetchone()[0]

        # Get completed tasks based on progress percentage
        cur.execute("SELECT COUNT(*) FROM tasks WHERE sprint_id = %s AND progress_percentage = 100", (sprint_id,))
        completed_tasks = cur.fetchone()[0]
        
        pending_tasks = total_tasks - completed_tasks

        logger.info("Successfully retrieved task summary for sprint", sprint_id=sprint_id, total=total_tasks, completed=completed_tasks, pending=pending_tasks)
        return SprintTaskSummary(
            total_tasks=total_tasks,
            completed_tasks=completed_tasks,
            pending_tasks=pending_tasks
        )

    except HTTPException:
        raise
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error("Database error while retrieving task summary for sprint", error=str(error))
        raise HTTPException(status_code=500, detail="Database operation failed during task summary retrieval.")
    finally:
        if conn:
            cur.close()
            put_db_connection(conn)
            logger.info("Database connection returned to pool.")


@app.post("/sprints/{sprint_id}/run-daily-scrum", status_code=200)
async def run_daily_scrum(sprint_id: str):
    """
    Triggers the complete daily scrum process:
    - Simulates task progress for active tasks in the sprint.
    - Updates task progress in SprintDB.
    - Publishes TASK_UPDATED events for Backlog Service.
    - Compiles and submits a daily scrum report to Chronicle Service.
    """
    logger.info("Received request to run daily scrum process", sprint_id=sprint_id)
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # 1. Validate sprint existence and status
        cur.execute("SELECT project_id, sprint_name FROM sprints WHERE sprint_id = %s AND status = 'in_progress';", (sprint_id,))
        sprint_data = cur.fetchone()
        if not sprint_data:
            raise HTTPException(status_code=404, detail=f"Active sprint {sprint_id} not found.")

        project_id, sprint_name = sprint_data[0], sprint_data[1]

        # 2. Retrieve active tasks for the sprint from SprintDB
        cur.execute("SELECT task_id, title, status, progress_percentage, COALESCE(assigned_to, 'unassigned') FROM tasks WHERE sprint_id = %s AND progress_percentage < 100;", (sprint_id,))
        active_tasks = cur.fetchall()
        logger.debug("Active tasks retrieved for daily scrum simulation", sprint_id=sprint_id, count=len(active_tasks), tasks=active_tasks)

        tasks_updated_count = 0
        grouped_reports = {} # To store data grouped by employee_id

        for task_id, title, current_status, current_progress, assigned_to_employee_id in active_tasks:
            logger.debug("Processing task for daily scrum", task_id=task_id, assigned_to=assigned_to_employee_id)
            logger.debug("assigned_to_employee_id before grouping", assigned_to_employee_id=assigned_to_employee_id)
            # Simulate progress
            progress_made = random.randint(5, 30) # Simulate 5-30% progress
            new_total_progress = min(100, current_progress + progress_made)
            new_status = "completed" if new_total_progress >= 100 else "in_progress"

            # Update task in SprintDB
            cur.execute(
                """
                UPDATE tasks
                SET progress_percentage = %s,
                    status = %s
                WHERE task_id = %s AND sprint_id = %s;
                """,
                (new_total_progress, new_status, task_id, sprint_id)
            )
            if cur.rowcount > 0:
                tasks_updated_count += 1
                logger.info("Simulated and updated task progress in SprintDB", task_id=task_id, new_progress=new_total_progress, new_status=new_status)

                # Publish TASK_UPDATED event
                task_updated_event = {
                    "event_id": str(uuid.uuid4()),
                    "event_type": "TASK_UPDATED",
                    "timestamp": datetime.utcnow().isoformat(),
                    "aggregate_id": task_id,
                    "aggregate_type": "Task",
                    "event_data": {
                        "task_id": task_id,
                        "project_id": project_id,
                        "sprint_id": sprint_id,
                        "status": new_status,
                        "progress_percentage": new_total_progress,
                        "updated_at": datetime.utcnow().isoformat(),
                        "assigned_to": assigned_to_employee_id # Include assigned_to in the event
                    },
                    "metadata": {
                        "source_service": "SprintService",
                        "correlation_id": str(uuid.uuid4())
                    }
                }
                await publish_event(redis_client, TASK_UPDATED_STREAM_NAME, task_updated_event)

                # Collect data for individual reports, grouped by employee_id
                employee_id_for_report = assigned_to_employee_id
                if employee_id_for_report not in grouped_reports:
                    grouped_reports[employee_id_for_report] = {"assigned_to": employee_id_for_report, "tasks": []}
                
                grouped_reports[employee_id_for_report]["tasks"].append({
                    "id": task_id,
                    "yesterday_work": f"Worked on {title} and completed {progress_made}% of it.",
                    "today_work": f"Continuing work on {title} to reach {new_total_progress}% completion.",
                    "impediments": "None." if random.random() > 0.1 else "Encountered a minor blocker with external dependency.",
                    "created_at": datetime.utcnow().isoformat()
                })
        conn.commit() # Commit all task updates

        # Convert grouped_reports dictionary to a list of reports for the payload
        individual_reports_list = list(grouped_reports.values())

        # 3. Compile and submit daily scrum report to Chronicle Service
        logger.info("Compiling daily scrum report for Chronicle Service", sprint_id=sprint_id)

        # Get team members for the report (synchronous call to Project Service)
        team_members_data = await call_project_service_get_team_members(project_id)
        total_team_members = len(team_members_data) if team_members_data else 0

        # Get task summary for the report
        cur.execute("SELECT COUNT(*) FROM tasks WHERE sprint_id = %s;", (sprint_id,))
        total_tasks_in_sprint = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM tasks WHERE sprint_id = %s AND progress_percentage = 100;", (sprint_id,))
        completed_tasks_in_sprint = cur.fetchone()[0]
        pending_tasks_in_sprint = total_tasks_in_sprint - completed_tasks_in_sprint

        report_payload = {
            "project_id": project_id,
            "sprint_id": sprint_id,
            "report_date": date.today().isoformat(),
            "summary": f"Daily stand-up for sprint {sprint_id}. {tasks_updated_count} tasks had progress simulated.",
            "summary_metrics": {
                "total_team_members": total_team_members,
                "total_tasks": total_tasks_in_sprint,
                "completed_tasks": completed_tasks_in_sprint,
                "pending_tasks": pending_tasks_in_sprint
            },
            "reports": {
                date.today().isoformat(): individual_reports_list # Group individual reports by date
            }
        }
        logger.debug("Sending daily scrum report payload to Chronicle Service", payload=report_payload)

        chronicle_response = await call_chronicle_service_create_daily_scrum_report(report_payload)
        report_id = chronicle_response.get("retrospective_id") if chronicle_response else "N/A" # Chronicle service returns retrospective_id for daily scrum reports as well
        logger.info("Submitted daily scrum report to Chronicle Service", sprint_id=sprint_id, report_id=report_id)

        return {
            "message": f"Daily scrum process completed for sprint {sprint_id}",
            "sprint_id": sprint_id,
            "tasks_updated_count": tasks_updated_count,
            "report_id": report_id
        }

    except HTTPException:
        raise
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error("Database error during daily scrum process", error=str(error), sprint_id=sprint_id)
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database operation failed during daily scrum process: {error}")
    finally:
        if conn:
            cur.close()
            put_db_connection(conn)
            logger.info("Database connection returned to pool after daily scrum process.")
