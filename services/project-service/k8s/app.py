from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import structlog
import psycopg2

from utils import get_db_connection

# Configure logging
logger = structlog.get_logger()

app = FastAPI()

# Pydantic model for data validation
class Project(BaseModel):
    id: str
    name: str
    description: str

@app.get("/health", status_code=200)
def health_check():
    """Health check endpoint to verify service is running."""
    return {"status": "ok"}

@app.post("/projects", status_code=201)
def create_project(project: Project):
    """
    Creates a new project in the database.
    """
    logger.info("Received request to create project", project_id=project.id)
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            "INSERT INTO projects (prjid, projectname, codename) VALUES (%s, %s, %s)",
            (project.id, project.name, project.description)
        )

        conn.commit()
        cur.close()
        logger.info("Successfully created project", project_id=project.id)
        return {"message": "Project created successfully", "project_id": project.id}

    except (Exception, psycopg2.DatabaseError) as error:
        logger.error("Database error while creating project", error=str(error))
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail="Database operation failed.")

    finally:
        if conn:
            conn.close()
            logger.info("Database connection closed.")

@app.get("/projects", status_code=200)
def list_projects():
    """
    Retrieves a list of all projects from the database.
    """
    logger.info("Received request to list all projects")
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT prjid, projectname, codename FROM projects")
        projects_data = cur.fetchall()
        cur.close()

        projects_list = []
        for prjid, projectname, codename in projects_data:
            projects_list.append(Project(id=prjid, name=projectname, description=codename))

        logger.info("Successfully retrieved all projects", count=len(projects_list))
        return projects_list

    except (Exception, psycopg2.DatabaseError) as error:
        logger.error("Database error while listing projects", error=str(error))
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail="Database operation failed.")

    finally:
        if conn:
            conn.close()
            logger.info("Database connection closed.")

@app.get("/projects/{project_id}", status_code=200, response_model=Project)
def get_project(project_id: str):
    """
    Retrieves details for a single project by its ID.
    """
    logger.info("Received request to get project details", project_id=project_id)
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT prjid, projectname, codename FROM projects WHERE prjid = %s", (project_id,))
        project_data = cur.fetchone()
        cur.close()

        if not project_data:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found.")

        prjid, projectname, codename = project_data
        project = Project(id=prjid, name=projectname, description=codename)

        logger.info("Successfully retrieved project details", project_id=project_id)
        return project

    except HTTPException:
        raise # Re-raise HTTPExceptions
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error("Database error while retrieving project details", error=str(error))
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail="Database operation failed.")

    finally:
        if conn:
            conn.close()
            logger.info("Database connection closed.")

@app.get("/projects/{project_id}/team-members", status_code=200)
def get_project_team_members(project_id: str):
    """
    Retrieves team members associated with a specific project.
    """
    logger.info("Received request to get team members for project", project_id=project_id)
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT t.id, t.name, t.gender, t.state, t.age
            FROM teams t
            JOIN project_team_mapping ptm ON t.id = ptm.employee_id
            WHERE ptm.project_id = %s
            """,
            (project_id,)
        )
        team_members = []
        for row in cur.fetchall():
            team_members.append({
                "id": row[0],
                "name": row[1],
                "gender": row[2],
                "state": row[3],
                "age": row[4]
            })

        cur.close()
        logger.info("Successfully retrieved team members for project", project_id=project_id, count=len(team_members))
        return {"project_id": project_id, "team_members": team_members}

    except (Exception, psycopg2.DatabaseError) as error:
        logger.error("Database error while retrieving team members", error=str(error))
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail="Database operation failed.")

    finally:
        if conn:
            conn.close()
            logger.info("Database connection closed.")
