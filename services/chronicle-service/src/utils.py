import structlog
from fastapi import HTTPException
from database import db_pool # Import db_pool from the new database.py

logger = structlog.get_logger()

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