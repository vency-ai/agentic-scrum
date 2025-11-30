import os
import psycopg2
import structlog
import httpx # For making HTTP requests to other services
from fastapi import HTTPException

logger = structlog.get_logger(__name__)

def get_db_connection():
    try:
        db_host = os.getenv("POSTGRES_HOST", "postgres")
        db_name = os.getenv("POSTGRES_DB")
        db_user = os.getenv("POSTGRES_USER")
        db_password = os.getenv("POSTGRES_PASSWORD")

        logger.info("Attempting to connect to database", db_host=db_host, db_name=db_name)
        conn = psycopg2.connect(
            host=db_host,
            database=db_name,
            user=db_user,
            password=db_password
        )
        logger.info("Database connection successful.")
        return conn
    except psycopg2.OperationalError as e:
        logger.error("Database connection failed.", error=str(e))
        raise

async def call_project_service(project_id: str):
    project_service_url = os.getenv("PROJECT_SERVICE_URL", "http://project-service.dsm.svc.cluster.local")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{project_service_url}/projects/{project_id}")
            response.raise_for_status() # Raise an exception for 4xx/5xx responses
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error("Error calling Project Service", status_code=e.response.status_code, response_text=e.response.text)
            raise HTTPException(status_code=e.response.status_code, detail=f"Error from Project Service: {e.response.text}")
        except httpx.RequestError as e:
            logger.error("Network error calling Project Service", error=str(e))
            raise HTTPException(status_code=500, detail=f"Network error connecting to Project Service: {e}")
