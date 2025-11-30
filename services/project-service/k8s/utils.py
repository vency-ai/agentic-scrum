import os
import psycopg2
import structlog

# Configure a simple logger for the utility module
logger = structlog.get_logger(__name__)

def get_db_connection():
    """
    Establishes a connection to the PostgreSQL database using credentials
    from environment variables.
    """
    try:
        db_host = os.getenv("POSTGRES_HOST", "postgres")
        db_name = os.getenv("POSTGRES_DB")
        db_user = os.getenv("POSTGRES_USER")
        db_password = os.getenv("POSTGRES_PASSWORD")

        logger.info("Attempting to connect to database...")

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
