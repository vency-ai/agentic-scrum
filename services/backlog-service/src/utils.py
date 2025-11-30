from psycopg2 import pool
import os
import structlog
import httpx
from fastapi import HTTPException
import asyncio
from circuit_breaker import CircuitBreaker, CircuitBrokenError

logger = structlog.get_logger()

# Configure the custom circuit breaker for calls to the project service
project_service_circuit_breaker = CircuitBreaker(
    error_ratio=0.5,  # Open if 50% of calls fail
    response_time=10, # Monitor failures within a 10-second window
    exceptions=[Exception], # Count these exceptions as failures
    broken_time=30    # Stay open for 30 seconds before attempting recovery
)

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

async def call_project_service(project_id: str):
    project_service_url = os.getenv("PROJECT_SERVICE_URL", "http://project-service.dsm.svc.cluster.local")
    async with httpx.AsyncClient() as client:
        async with project_service_circuit_breaker.context():
            response = await client.get(f"{project_service_url}/projects/{project_id}")
            response.raise_for_status() # Raise an exception for 4xx/5xx responses
            return response.json()

async def get_all_projects():
    project_service_url = os.getenv("PROJECT_SERVICE_URL", "http://project-service.dsm.svc.cluster.local")
    async with httpx.AsyncClient() as client:
        async with project_service_circuit_breaker.context():
            response = await client.get(f"{project_service_url}/projects")
            response.raise_for_status()
            return response.json()
