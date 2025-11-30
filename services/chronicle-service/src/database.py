from psycopg2 import pool
import os
import structlog

logger = structlog.get_logger()

class DatabasePool:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabasePool, cls).__new__(cls)
            cls._instance._initialize_pool()
        return cls._instance

    def _initialize_pool(self):
        db_host = os.getenv("POSTGRES_HOST", "chronicle-db") # Default to chronicle-db for this service
        db_name = os.getenv("POSTGRES_DB", "chronicle_db")
        db_user = os.getenv("POSTGRES_USER", "chronicle_user")
        db_password = os.getenv("POSTGRES_PASSWORD", "chronicle_password")

        db_config = {
            "host": db_host,
            "database": db_name,
            "user": db_user,
            "password": db_password
        }

        try:
            self.pool = pool.SimpleConnectionPool(
                minconn=1,
                maxconn=20, # Adjust maxconn based on expected load
                **db_config
            )
            logger.info("Database connection pool initialized.")
        except Exception as e:
            logger.error("Failed to initialize database connection pool.", error=str(e))
            raise

    def get_connection(self):
        """Acquires a connection from the pool."""
        try:
            return self.pool.getconn()
        except Exception as e:
            logger.error("Failed to get connection from pool.", error=str(e))
            raise

    def put_connection(self, conn):
        """Returns a connection to the pool."""
        if conn:
            self.pool.putconn(conn)

    def close_all_connections(self):
        """Closes all connections in the pool."""
        if self.pool:
            self.pool.closeall()
            logger.info("Database connection pool closed.")

# Global instance used by services
db_pool = DatabasePool()
