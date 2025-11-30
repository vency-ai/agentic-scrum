from psycopg2 import pool
import os
import structlog
import httpx
from fastapi import HTTPException
from datetime import date, timedelta
from typing import List, Optional

logger = structlog.get_logger()

class DatabasePool:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabasePool, cls).__new__(cls)
            cls._instance._initialize_pool()
        return cls._instance

    def _initialize_pool(self):
        db_host = os.getenv("POSTGRES_HOST", "postgres")
        db_name = os.getenv("POSTGRES_DB")
        db_user = os.getenv("POSTGRES_USER")
        db_password = os.getenv("POSTGRES_PASSWORD")

        db_config = {
            "host": db_host,
            "database": db_name,
            "user": db_user,
            "password": db_password
        }
        
        try:
            self.pool = pool.SimpleConnectionPool(
                minconn=1, 
                maxconn=20, # Adjust maxconn based on expected load and database capacity
                **db_config
            )
            logger.info("Database connection pool initialized successfully.", minconn=1, maxconn=20, db_host=db_host, db_name=db_name)
        except Exception as e:
            logger.error("Failed to initialize database connection pool.", error=str(e))
            raise

    def get_connection(self):
        try:
            conn = self.pool.getconn()
            #logger.debug("Connection acquired from pool.")
            return conn
        except Exception as e:
            logger.error("Failed to get connection from pool.", error=str(e))
            raise

    def put_connection(self, conn):
        if conn:
            self.pool.putconn(conn)
            #logger.debug("Connection returned to pool.")

    def close_all_connections(self):
        if self.pool:
            self.pool.closeall()
            logger.info("All database connections in the pool closed.")

# Global instance to be used across the application
db_pool = DatabasePool()

def get_db_connection():
    """
    Gets a connection from the connection pool.
    """
    return db_pool.get_connection()

def put_db_connection(conn):
    """
    Returns a connection to the connection pool.
    """
    db_pool.put_connection(conn)

def close_all_db_connections():
    """
    Closes all connections in the pool.
    """
    db_pool.close_all_connections()

async def call_project_service_get_project(project_id: str):
    project_service_url = os.getenv("PROJECT_SERVICE_URL", "http://project-service.dsm.svc.cluster.local")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{project_service_url}/projects/{project_id}")
            response.raise_for_status() # Raise an exception for 4xx/5xx responses
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning("Project not found in Project Service (GET project)", status_code=e.response.status_code, project_id=project_id)
                return None # Return None if project not found
            else:
                logger.error("Error calling Project Service (GET project)", status_code=e.response.status_code, response_text=e.response.text)
                return None # Return None for other HTTP errors to prevent crashing sprint-service
        except httpx.RequestError as e:
            logger.error("Network error calling Project Service (GET project)", error=str(e), project_id=project_id)
            return None # Return None on network errors

async def call_backlog_service_get_tasks(project_id: str, status: str = "unassigned"):
    backlog_service_url = os.getenv("BACKLOG_SERVICE_URL", "http://backlog-service.dsm.svc.cluster.local")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{backlog_service_url}/backlogs/{project_id}?status={status}")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error("Error calling Backlog Service (GET tasks)", status_code=e.response.status_code, response_text=e.response.text)
            raise HTTPException(status_code=e.response.status_code, detail=f"Error from Backlog Service: {e.response.text}")
        except httpx.RequestError as e:
            logger.error("Network error calling Backlog Service (GET tasks)", error=str(e))
            raise HTTPException(status_code=500, detail=f"Network error connecting to Backlog Service: {e}")

async def call_backlog_service_update_task(task_id: str, update_data: dict):
    backlog_service_url = os.getenv("BACKLOG_SERVICE_URL", "http://backlog-service.dsm.svc.cluster.local")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.put(f"{backlog_service_url}/tasks/{task_id}", json=update_data)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error("Error calling Backlog Service (PUT task)", status_code=e.response.status_code, response_text=e.response.text)
            raise HTTPException(status_code=e.response.status_code, detail=f"Error from Backlog Service: {e.response.text}")
        except httpx.RequestError as e:
            logger.error("Network error calling Backlog Service (PUT task)", error=str(e))
            raise HTTPException(status_code=500, detail=f"Network error connecting to Backlog Service: {e}")

async def call_chronicle_service_create_note(project_id: str, sprint_id: str, what_went_well: str, what_could_be_improved: str, action_items: list, facilitator_id: str, attendees: list):
    """
    Calls Chronicle Service to create a retrospective note.
    """
    chronicle_service_url = os.getenv("CHRONICLE_SERVICE_URL", "http://chronicle-service.dsm.svc.cluster.local")
    
    payload = {
        "sprint_id": sprint_id,
        "project_id": project_id,
        "what_went_well": what_went_well,
        "what_could_be_improved": what_could_be_improved,
        "action_items": action_items,
        "facilitator_id": facilitator_id,
        "attendees": attendees
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(f"{chronicle_service_url}/v1/notes/sprint_retrospective", json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error("Error calling Chronicle Service (POST retrospective)", status_code=e.response.status_code, response_text=e.response.text)
            raise HTTPException(status_code=e.response.status_code, detail=f"Error from Chronicle Service: {e.response.text}")
        except httpx.RequestError as e:
            logger.error("Network error calling Chronicle Service (POST retrospective)", error=str(e))
            raise HTTPException(status_code=500, detail=f"Network error connecting to Chronicle Service: {e}")

async def publish_event(redis_client, stream_name: str, event_data: dict):
    """
    Publishes an event to a Redis stream with proper error handling and logging.
    
    Args:
        redis_client: Redis async client instance
        stream_name: Name of the Redis stream to publish to
        event_data: Dictionary containing the event payload
    """
    import json
    try:
        if not redis_client:
            logger.error("Redis client is not available for event publishing", stream_name=stream_name)
            return False
            
        # Serialize event data to JSON
        event_json = json.dumps(event_data, default=str)  # default=str handles datetime objects
        
        # Publish to Redis stream
        message_id = await redis_client.xadd(stream_name, {"data": event_json})
        
        logger.info("Successfully published event to stream", 
                   stream_name=stream_name, 
                   event_type=event_data.get("event_type", "unknown"),
                   message_id=message_id,
                   event_id=event_data.get("event_id", "unknown"))
        return True
        
    except json.JSONEncodeError as e:
        logger.error("Failed to serialize event data to JSON", 
                    error=str(e), 
                    stream_name=stream_name,
                    event_type=event_data.get("event_type", "unknown"))
        return False
    except Exception as e:
        logger.error("Failed to publish event to Redis stream", 
                    error=str(e), 
                    stream_name=stream_name,
                    event_type=event_data.get("event_type", "unknown"))
        return False
