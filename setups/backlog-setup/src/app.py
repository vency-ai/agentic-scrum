import os
import json
import random
import time
from datetime import datetime
import psycopg2
import httpx
import structlog

structlog.configure([structlog.processors.JSONRenderer()])
logger = structlog.get_logger()

# Test project constants
TEST_PROJECT_ID = os.getenv("PROJECT_ID", "TEST-001")
TEST_SPRINT_ID = os.getenv("SPRINT_ID", "SPRINT-001")


def get_backlog_db_connection():
    """Connect to the dedicated backlog database."""
    try:
        db_host = os.getenv("POSTGRES_HOST", "backlog-db")
        db_name = os.getenv("POSTGRES_DB")
        db_user = os.getenv("POSTGRES_USER")
        db_password = os.getenv("POSTGRES_PASSWORD")
        db_port = os.getenv("POSTGRES_PORT", "5432")

        logger.info("Connecting to backlog database", db_host=db_host, db_port=db_port, db_name=db_name)
        conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            database=db_name,
            user=db_user,
            password=db_password
        )
        logger.info("Backlog database connection successful.")
        return conn
    except psycopg2.OperationalError as e:
        logger.error("Backlog database connection failed", error=str(e))
        raise


def call_project_service_api(project_id):
    """Call Project Service API to get project details and team members."""
    project_service_url = os.getenv("PROJECT_SERVICE_URL", "http://project-service.dsm.svc.cluster.local")
    
    try:
        # Check if project exists
        with httpx.Client(timeout=30.0) as client:
            response = client.get(f"{project_service_url}/projects/{project_id}")
            response.raise_for_status()
            project_data = response.json()
            logger.info("Project found via API", project_id=project_id)
            
            # Get team members for project
            response = client.get(f"{project_service_url}/projects/{project_id}/team-members")
            response.raise_for_status()
            team_data = response.json()
            
            team_members = team_data.get("team_members", [])
            team_members = [member["id"] for member in team_members] # Extract only IDs
            logger.info("Retrieved team members for project", count=len(team_members), project_id=project_id)
            
            return project_data, team_members
            
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.warning("Project not found in Project Service", project_id=project_id)
            return None, []
        else:
            logger.error("HTTP error calling Project Service", status_code=e.response.status_code, error=str(e))
            raise
    except httpx.RequestError as e:
        logger.error("Network error calling Project Service", error=str(e))
        raise



def ensure_backlog_tables_exist(conn):
    """Verify required backlog tables exist in the backlog database."""
    cur = conn.cursor()
    
    # Tables should already exist from migrations, just verify
    # Check if tables exist
    cur.execute("""
        SELECT table_name FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_name IN ('tasks', 'stories', 'story_tasks', 'backlog')
    """)
    existing_tables = [row[0] for row in cur.fetchall()]
    
    required_tables = ['tasks', 'stories', 'story_tasks']
    missing_tables = [table for table in required_tables if table not in existing_tables]
    
    if missing_tables:
        logger.error("Missing required tables", missing_tables=missing_tables)
        raise Exception(f"Required tables not found: {missing_tables}")
    
    conn.commit()
    cur.close()
    logger.info("Required backlog database tables verified successfully")





def create_sample_data(conn, project_id, team_members):
    """Create sample backlog data for the test project."""
    cur = conn.cursor()
    
    # Sample tasks data - using the actual table structure
    sample_tasks = [
        ("TSK-001", "Setup Development Environment", "Configure local development environment with required tools"),
        ("TSK-002", "Database Schema Design", "Design and create database schema for the application"),
        ("TSK-003", "API Endpoint Implementation", "Implement REST API endpoints for core functionality"),
        ("TSK-004", "Frontend Component Development", "Develop React components for user interface"),
        ("TSK-005", "User Authentication", "Implement user login and authentication system"),
        ("TSK-006", "Testing and Quality Assurance", "Write unit tests and perform QA testing"),
        ("TSK-007", "Documentation", "Create technical and user documentation"),
        ("TSK-008", "Deployment Setup", "Configure CI/CD pipeline and deployment process")
    ]
    
    # Sample stories data
    sample_stories = [
        ("STR-001", "As a new user, I want to register an account so I can access the system"),
        ("STR-002", "As a logged-in user, I want to see a dashboard with my recent activities"),
        ("STR-003", "As a project manager, I want to create and manage projects"),
        ("STR-004", "As a team member, I want to collaborate with other team members")
    ]
    
    # Clear existing test data for idempotency
    cur.execute("DELETE FROM story_tasks WHERE task_id LIKE 'TSK-%' OR story_id LIKE 'STR-%'")
    cur.execute("DELETE FROM tasks WHERE task_id LIKE 'TSK-%'")
    cur.execute("DELETE FROM stories WHERE id LIKE 'STR-%'")
    
    # Insert sample tasks using actual table structure
    for task_id, title, description in sample_tasks:
        # Assign to team members in round-robin fashion
        assigned_to = str(team_members[len(sample_tasks[:sample_tasks.index((task_id, title, description))]) % len(team_members)]) if team_members else "1"
        
        cur.execute(
            """
            INSERT INTO tasks (task_id, project_id, title, description, status, assigned_to, progress_percentage)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (task_id) DO UPDATE SET
                project_id = EXCLUDED.project_id,
                title = EXCLUDED.title,
                description = EXCLUDED.description,
                status = EXCLUDED.status,
                assigned_to = EXCLUDED.assigned_to,
                progress_percentage = EXCLUDED.progress_percentage
            """,
            (task_id, project_id, title, description, 'NotStarted', assigned_to, 0)
        )
    
    # Insert sample stories
    for story_id, description in sample_stories:
        cur.execute(
            """
            INSERT INTO stories (id, description)
            VALUES (%s, %s)
            ON CONFLICT (id) DO UPDATE SET
                description = EXCLUDED.description
            """,
            (story_id, description)
        )
    
    # Link stories to tasks
    story_task_mappings = [
        ("STR-001", "TSK-001"),  # User Registration -> Setup Environment
        ("STR-001", "TSK-005"),  # User Registration -> User Authentication
        ("STR-002", "TSK-003"),  # User Dashboard -> API Implementation
        ("STR-002", "TSK-004"),  # User Dashboard -> Frontend Development
        ("STR-003", "TSK-002"),  # Project Management -> Database Design
        ("STR-003", "TSK-003"),  # Project Management -> API Implementation
        ("STR-004", "TSK-004"),  # Team Collaboration -> Frontend Development
        ("STR-004", "TSK-006"),  # Team Collaboration -> Testing
    ]
    
    for story_id, task_id in story_task_mappings:
        cur.execute(
            """
            INSERT INTO story_tasks (story_id, task_id)
            VALUES (%s, %s)
            ON CONFLICT (story_id, task_id) DO NOTHING
            """,
            (story_id, task_id)
        )
    
    conn.commit()
    cur.close()
    
    backlog_items_created = len(sample_tasks)
    logger.info("Created backlog items", tasks_count=len(sample_tasks), stories_count=len(sample_stories), story_task_mappings_count=len(story_task_mappings))
    return backlog_items_created


def setup_backlog_job():
    """Main function to setup backlog data for the test project."""
    logger.info("Starting backlog setup job")
    
    try:
        # Connect to backlog database
        conn = get_backlog_db_connection()
        
        # Ensure required tables exist
        ensure_backlog_tables_exist(conn)
        
        # Try to get project info and team members from Project Service
        try:
            project_data, team_members = call_project_service_api(TEST_PROJECT_ID)
            if project_data is None:
                logger.warning("Project not found via API, using default team members", project_id=TEST_PROJECT_ID)
                team_members = [1, 2, 3, 4]  # Default employee IDs
        except Exception as e:
            logger.warning("Could not call Project Service API, using default team members", error=str(e))
            team_members = [1, 2, 3, 4]  # Default employee IDs
        
        # Create sample backlog data
        items_created = create_sample_data(conn, TEST_PROJECT_ID, team_members)
        
        conn.close()
        
        logger.info("Backlog setup completed successfully", items_created=items_created, project_id=TEST_PROJECT_ID)
        return True
        
    except Exception as e:
        logger.error("Backlog setup failed", error=str(e))
        return False



if __name__ == '__main__':
    success = setup_backlog_job()
    if success:
        logger.info("Backlog setup job completed successfully")
        exit(0)
    else:
        logger.error("Backlog setup job failed")
        exit(1)
