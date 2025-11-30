import structlog
import logging
from log_config import HealthCheckFilter

# Configure structured logging
logger = structlog.get_logger()

# Apply filter to Uvicorn access logger
uvicorn_access_logger = logging.getLogger("uvicorn.access")
uvicorn_access_logger.addFilter(HealthCheckFilter())

import os
import psycopg2
from fastapi import FastAPI, HTTPException, Body, Request
import json
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date, datetime
import uuid
from psycopg2.extras import RealDictCursor
from utils import get_db_connection, put_db_connection, close_all_db_connections
from fastapi.responses import JSONResponse
import asyncio
from event_consumer import RedisConsumer

# Define Pydantic models for request and response bodies
class Project(BaseModel):
    id: str
    name: str
    description: str
    status: str

class ProjectStatus(BaseModel):
    status: str

class Holiday(BaseModel):
    holiday_date: date
    holiday_name: str
    type: str

class PTORequest(BaseModel):
    start_date: date
    end_date: date
    reason: Optional[str] = None

class PTOResponse(BaseModel):
    pto_id: uuid.UUID
    employee_id: str
    start_date: date
    end_date: date
    reason: Optional[str] = None

class AvailabilityConflict(BaseModel):
    type: str
    date: date
    name: str
    details: str

class AvailabilityResponse(BaseModel):
    status: str
    conflicts: List[AvailabilityConflict]

class TeamMember(BaseModel):
    employee_id: str
    employee_name: Optional[str] = None

class EmployeeCreate(BaseModel):
    employee_id: str
    name: str
    gender: Optional[str] = None
    state: Optional[str] = None
    age: Optional[int] = None

class TeamMembersAssign(BaseModel):
    employee_ids: List[str]



class TeamMembersAssign(BaseModel):
    employee_ids: List[str]



app = FastAPI()
sprint_started_consumer = None

async def handle_sprint_started(event_payload: dict):
    project_id = event_payload.get("project_id")
    sprint_id = event_payload.get("sprint_id")
    logger.info("Processing SprintStarted event", project_id=project_id, sprint_id=sprint_id)

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # Update project status to 'in_progress'
        cur.execute(
            "UPDATE projects SET status = %s WHERE prjid = %s",
            ("in_progress", project_id)
        )
        if cur.rowcount == 0:
            logger.warning("Project not found for status update", project_id=project_id)
        else:
            conn.commit()
            logger.info("Project status updated to 'in_progress'", project_id=project_id, sprint_id=sprint_id)
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error("Database error during SprintStarted event handling", error=str(error), project_id=project_id)
        if conn:
            conn.rollback()
    finally:
        if conn:
            cur.close()
            put_db_connection(conn)

@app.on_event("startup")
async def startup_event():
    global sprint_started_consumer
    logger.info("Project Service starting up...")
    # Initialize RedisConsumer with service_name, stream_name, and handler_function
    sprint_started_consumer = RedisConsumer(
        service_name="project-service",
        stream_name="dsm:events",
        handler_function=handle_sprint_started
    )
    logger.info("Starting SprintStarted event consumer...")
    # Start the consumer in a background task
    asyncio.create_task(sprint_started_consumer.start()) # Changed to asyncio.create_task

@app.on_event("shutdown")
def shutdown_event():
    global sprint_started_consumer
    if sprint_started_consumer:
        sprint_started_consumer.stop()
    close_all_db_connections()

@app.get("/health", status_code=200)
def health_check():
    """Health check endpoint to verify service is running."""
    return {"status": "ok"}

@app.get("/health/ready", status_code=200)
def readiness_check():
    """
    Comprehensive readiness probe for project-service.
    Checks database connectivity.
    """
    db_status = "ok"
    try:
        conn = get_db_connection()
        # Perform a simple query to check connectivity
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        put_db_connection(conn)
    except Exception as e:
        logger.error("Database readiness check failed", error=str(e))
        db_status = "error"
        
    overall_status = "ready" if db_status == "ok" else "not_ready"
    status_code = 200 if overall_status == "ready" else 503

    response_content = {
        "service": "project-service",
        "status": overall_status,
        "database": db_status,
        "timestamp": datetime.utcnow().isoformat()
    }
    return JSONResponse(content=response_content, status_code=status_code)

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
            "INSERT INTO projects (prjid, projectname, codename, status) VALUES (%s, %s, %s, %s)",
            (project.id, project.name, project.description, project.status)
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
            put_db_connection(conn)
            logger.info("Database connection returned to pool.")

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

        cur.execute("SELECT prjid, projectname, codename, status FROM projects")
        projects_data = cur.fetchall()
        cur.close()

        projects_list = []
        for prjid, projectname, codename, status in projects_data:
            projects_list.append(Project(id=prjid, name=projectname, description=codename, status=status))
        logger.info("Successfully retrieved all projects", count=len(projects_list))
        return projects_list

    except (Exception, psycopg2.DatabaseError) as error:
        logger.error("Database error while listing projects", error=str(error))
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail="Database operation failed.")

    finally:
        if conn:
            put_db_connection(conn)
            logger.info("Database connection returned to pool.")

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

        query = "SELECT prjid, projectname, codename, status FROM projects WHERE prjid = %s"
        logger.info("Executing query", query=query, params=(project_id,))
        cur.execute(query, (project_id,))
        project_data = cur.fetchone()
        logger.info("Raw query result", result=project_data)
        
        if not project_data:
            cur.close()
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found.")

        prjid, projectname, codename, status = project_data
        project = Project(id=prjid.strip(), name=projectname.strip(), description=codename.strip(), status=status.strip())
        logger.info("Successfully retrieved project details", project_id=project.id)
        
        cur.close()
        return project
    
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error("Database error while getting project", error=str(error))
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail="Database operation failed.")
    finally:
        if conn:
            put_db_connection(conn)
            logger.info("Database connection returned to pool.")

@app.put("/projects/{project_id}/status", status_code=200)
def update_project_status(project_id: str, status: ProjectStatus):
    """
    Updates the status of a project.
    """
    logger.info("Received request to update project status", project_id=project_id, status=status.status)
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            "UPDATE projects SET status = %s WHERE prjid = %s",
            (status.status, project_id)
        )

        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found.")

        conn.commit()
        cur.close()
        logger.info("Successfully updated project status", project_id=project_id, status=status.status)
        return {"message": "Project status updated successfully", "project_id": project_id, "status": status.status}

    except (Exception, psycopg2.DatabaseError) as error:
        logger.error("Database error while updating project status", error=str(error))
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail="Database operation failed.")

    finally:
        if conn:
            put_db_connection(conn)
            logger.info("Database connection returned to pool.")

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
            put_db_connection(conn)
            logger.info("Database connection returned to pool.")

# === Calendar Endpoints (from Calendar Service) ===

@app.get("/calendar/holidays", status_code=200)
def get_holidays():
    """
    Retrieves all US holidays from the database.
    """
    logger.info("Received request to get all holidays")
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("SELECT holiday_date, holiday_name, type FROM us_holidays ORDER BY holiday_date")
        holidays_data = cur.fetchall()
        cur.close()
        
        holidays = [Holiday(holiday_date=row['holiday_date'], holiday_name=row['holiday_name'], type=row['type']) for row in holidays_data]
        
        logger.info("Successfully retrieved holidays", count=len(holidays))
        return holidays
        
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error("Database error while getting holidays", error=str(error))
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail="Database operation failed.")
    finally:
        if conn:
            put_db_connection(conn)
            logger.info("Database connection returned to pool.")

@app.get("/projects/{project_id}/calendar/pto", status_code=200)
def get_project_pto(project_id: str):
    """
    Retrieves PTO calendar for a specific project's team members.
    """
    logger.info("Received request to get PTO for project", project_id=project_id)
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get PTO entries for team members assigned to this project
        cur.execute("""
            SELECT pc.pto_id, pc.employee_id, pc.start_date, pc.end_date, pc.reason
            FROM pto_calendar pc
            JOIN project_team_mapping ptm ON pc.employee_id = ptm.employee_id
            WHERE ptm.project_id = %s
            ORDER BY pc.start_date
        """, (project_id,))
        
        pto_data = cur.fetchall()
        cur.close()
        
        pto_entries = [PTOResponse(
            pto_id=row['pto_id'],
            employee_id=row['employee_id'],
            start_date=row['start_date'],
            end_date=row['end_date'],
            reason=row['reason']
        ) for row in pto_data]
        
        logger.info("Successfully retrieved project PTO entries", project_id=project_id, count=len(pto_entries))
        return pto_entries
        
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error("Database error while getting project PTO", error=str(error))
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail="Database operation failed.")
    finally:
        if conn:
            put_db_connection(conn)
            logger.info("Database connection returned to pool.")

@app.post("/projects/{project_id}/calendar/pto", status_code=201)
def add_project_pto(project_id: str, employee_id: str, pto_request: PTORequest):
    """
    Adds a PTO entry for a team member in the specified project.
    """
    logger.info("Received request to add PTO", project_id=project_id, employee_id=employee_id)
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verify the employee is assigned to this project
        cur.execute("SELECT COUNT(*) FROM project_team_mapping WHERE project_id = %s AND employee_id = %s", 
                   (project_id, employee_id))
        if cur.fetchone()[0] == 0:
            raise HTTPException(status_code=404, detail=f"Employee {employee_id} not assigned to project {project_id}")
        
        # Generate UUID for PTO entry
        pto_id = uuid.uuid4()
        
        cur.execute("""
            INSERT INTO pto_calendar (pto_id, employee_id, start_date, end_date, reason)
            VALUES (%s, %s, %s, %s, %s)
        """, (pto_id, employee_id, pto_request.start_date, pto_request.end_date, pto_request.reason))
        
        conn.commit()
        cur.close()
        
        logger.info("Successfully added PTO entry", pto_id=pto_id, employee_id=employee_id)
        return PTOResponse(
            pto_id=pto_id,
            employee_id=employee_id,
            start_date=pto_request.start_date,
            end_date=pto_request.end_date,
            reason=pto_request.reason
        )
        
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error("Database error while adding PTO", error=str(error))
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail="Database operation failed.")
    finally:
        if conn:
            put_db_connection(conn)
            logger.info("Database connection returned to pool.")

@app.delete("/projects/{project_id}/calendar/pto/{pto_id}", status_code=200)
def delete_project_pto(project_id: str, pto_id: str):
    """
    Deletes a PTO entry for a team member in the specified project.
    """
    logger.info("Received request to delete PTO", project_id=project_id, pto_id=pto_id)
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verify the PTO entry belongs to someone on this project
        cur.execute("""
            SELECT COUNT(*) FROM pto_calendar pc
            JOIN project_team_mapping ptm ON pc.employee_id = ptm.employee_id
            WHERE pc.pto_id = %s AND ptm.project_id = %s
        """, (pto_id, project_id))
        
        if cur.fetchone()[0] == 0:
            raise HTTPException(status_code=404, detail=f"PTO entry {pto_id} not found for project {project_id}")
        
        cur.execute("DELETE FROM pto_calendar WHERE pto_id = %s", (pto_id,))
        
        conn.commit()
        cur.close()
        
        logger.info("Successfully deleted PTO entry", pto_id=pto_id, project_id=project_id)
        return {"message": "PTO entry deleted successfully", "pto_id": pto_id}
        
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error("Database error while deleting PTO", error=str(error))
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail="Database operation failed.")
    finally:
        if conn:
            put_db_connection(conn)
            logger.info("Database connection returned to pool.")

@app.get("/projects/{project_id}/availability/check", status_code=200)
def check_project_availability(project_id: str, start_date: date, end_date: date):
    """
    Checks availability for a project's team members within a date range.
    Returns conflicts with holidays and PTO.
    """
    logger.info("Received request to check availability", project_id=project_id, start_date=start_date, end_date=end_date)
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        conflicts = []
        
        # Check for holidays in the date range
        cur.execute("""
            SELECT holiday_date, holiday_name 
            FROM us_holidays 
            WHERE holiday_date BETWEEN %s AND %s
        """, (start_date, end_date))
        
        holidays = cur.fetchall()
        for holiday in holidays:
            conflicts.append(AvailabilityConflict(
                type="holiday",
                date=holiday['holiday_date'],
                name=holiday['holiday_name'],
                details=f"US Holiday: {holiday['holiday_name']}"
            ))
        
        # Check for PTO conflicts for project team members
        cur.execute("""
            SELECT pc.start_date, pc.end_date, pc.employee_id, t.name as employee_name
            FROM pto_calendar pc
            JOIN project_team_mapping ptm ON pc.employee_id = ptm.employee_id
            JOIN teams t ON pc.employee_id = t.id
            WHERE ptm.project_id = %s 
            AND (pc.start_date <= %s AND pc.end_date >= %s)
        """, (project_id, end_date, start_date))
        
        pto_entries = cur.fetchall()
        for pto in pto_entries:
            conflicts.append(AvailabilityConflict(
                type="pto",
                date=pto['start_date'],
                name=pto['employee_name'] or pto['employee_id'],
                details=f"{pto['employee_name'] or pto['employee_id']} on PTO from {pto['start_date']} to {pto['end_date']}"
            ))
        
        cur.close()
        
        status_result = "conflict" if conflicts else "ok"
        logger.info("Availability check completed", project_id=project_id, conflicts_found=len(conflicts))
        
        return AvailabilityResponse(status=status_result, conflicts=conflicts)
        
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error("Database error while checking availability", error=str(error))
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail="Database operation failed.")
    finally:
        if conn:
            put_db_connection(conn)
            logger.info("Database connection returned to pool.")

# === Team Management Endpoints (from Team Management Service) ===

@app.post("/employees", status_code=201, response_model=dict)
async def create_employee(request: Request):
    """
    Creates a new employee in the teams table.
    """
    logger.info("Received request to create employee")
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        try:
            body = await request.json()
            employee_id = body.get("employee_id")
            name = body.get("name")
            gender = body.get("gender")
            state = body.get("state")
            age = body.get("age")
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON format")

        if not employee_id or not name:
            raise HTTPException(status_code=422, detail="Employee ID and name are required.")
        
        cur.execute("""
            INSERT INTO teams (Id, Name, Gender, State, Age, project_assign, active) 
            VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (Id) DO NOTHING
        """, (employee_id, name, gender, state, age, False, True))
        
        conn.commit()
        cur.close()
        
        logger.info("Successfully created employee", employee_id=employee_id)
        return {"employee_id": employee_id, "employee_name": name}
        
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error("Database error while creating employee", error=str(error))
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail="Database operation failed.")
    finally:
        if conn:
            put_db_connection(conn)
            logger.info("Database connection returned to pool.")

@app.post("/debug-employees", status_code=200)
async def debug_employees(request: Request):
    print("debug_employees function entered")
    headers = dict(request.headers)
    raw_body = await request.body()
    logger.info("Debug: Received headers", headers=headers)
    logger.info("Debug: Received raw body", raw_body=raw_body.decode())
    return {"message": "Debug info logged", "headers": headers, "body_length": len(raw_body)}

@app.get("/employees/{employee_id}", status_code=200)
def get_employee(employee_id: str):
    """
    Retrieves employee details by ID.
    """
    logger.info("Received request to get employee", employee_id=employee_id)
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("SELECT Id as id, Name as name, Gender as gender, State as state, Age as age, project_assign, active FROM teams WHERE Id = %s", (employee_id,))
        employee = cur.fetchone()
        
        if not employee:
            cur.close()
            raise HTTPException(status_code=404, detail="Employee not found")

        # Fetch assigned project IDs
        cur.execute("SELECT project_id FROM project_team_mapping WHERE employee_id = %s", (employee_id,))
        assigned_projects = [row['project_id'] for row in cur.fetchall()]
        
        employee['assigned_projects'] = assigned_projects
        
        cur.close()
            
        logger.info("Successfully retrieved employee", employee_id=employee_id)
        return employee
        
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error("Database error while getting employee", error=str(error))
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail="Database operation failed.")
    finally:
        if conn:
            put_db_connection(conn)
            logger.info("Database connection returned to pool.")

@app.get("/teams", status_code=200)
def get_all_teams():
    """
    Retrieves all teams (employees) from the database.
    """
    logger.info("Received request to get all teams")
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("SELECT Id as employee_id, Name as employee_name FROM teams WHERE active = true")
        teams = cur.fetchall()
        cur.close()
        
        team_members = [TeamMember(employee_id=row['employee_id'], employee_name=row['employee_name']) for row in teams]
        
        logger.info("Successfully retrieved all teams", count=len(team_members))
        return team_members
        
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error("Database error while getting teams", error=str(error))
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail="Database operation failed.")
    finally:
        if conn:
            put_db_connection(conn)
            logger.info("Database connection returned to pool.")

@app.get("/teams/{team_id}", status_code=200)
def get_team(team_id: str):
    """
    Retrieves a specific team (employee) by ID.
    """
    logger.info("Received request to get team", team_id=team_id)
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("SELECT Id as id, Name as name FROM teams WHERE Id = %s", (team_id,))
        team_data = cur.fetchone()
        
        if not team_data:
            raise HTTPException(status_code=404, detail="Team not found")
        
        # For simplicity, a 'team' with team_id is just that single employee for now
        team_members = [TeamMember(employee_id=team_data['id'], employee_name=team_data['name'])]
        
        cur.close()
        logger.info("Successfully retrieved team", team_id=team_id)
        return {"id": team_data['id'], "name": team_data['name'], "members": team_members}
        
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error("Database error while getting team", error=str(error))
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail="Database operation failed.")
    finally:
        if conn:
            put_db_connection(conn)
            logger.info("Database connection returned to pool.")

@app.get("/teams/{team_id}/members", status_code=200)
def get_team_members_by_team_id(team_id: str):
    """
    Retrieves members of a specific team (employee).
    """
    logger.info("Received request to get team members", team_id=team_id)
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("SELECT Id as employee_id, Name as employee_name FROM teams WHERE Id = %s", (team_id,))
        member = cur.fetchone()
        cur.close()
        
        if not member:
            raise HTTPException(status_code=404, detail="Team (employee) not found")
            
        logger.info("Successfully retrieved team members", team_id=team_id)
        return [TeamMember(employee_id=member['employee_id'], employee_name=member['employee_name'])]
        
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error("Database error while getting team members", error=str(error))
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail="Database operation failed.")
    finally:
        if conn:
            put_db_connection(conn)
            logger.info("Database connection returned to pool.")

@app.post("/projects/{project_id}/team-members-assign", status_code=200)
async def assign_team_members_to_project_enhanced(project_id: str, request: Request):
    """
    Assigns team members to a specific project and updates their assignment status.
    """
    logger.info("Received request to assign team members to project", project_id=project_id)
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Manually parse the request body
        try:
            body = await request.json()
            employee_ids = body.get("employee_ids")
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON format")

        if not isinstance(employee_ids, list):
            raise HTTPException(status_code=422, detail="'employee_ids' must be a list.")
        if not all(isinstance(e_id, str) for e_id in employee_ids):
            raise HTTPException(status_code=422, detail="All 'employee_ids' must be strings.")

        assigned_count = 0
        for employee_id in employee_ids:
            # Check if employee exists in 'teams' table
            cur.execute("SELECT COUNT(*) FROM teams WHERE Id = %s", (employee_id,))
            employee_exists = cur.fetchone()[0]
            if employee_exists == 0:
                logger.warning(f"Employee {employee_id} not found in teams table. Skipping assignment.")
                continue

            # Insert into project_team_mapping
            cur.execute("""
                INSERT INTO project_team_mapping (project_id, employee_id) 
                VALUES (%s, %s) ON CONFLICT (project_id, employee_id) DO NOTHING
            """, (project_id, employee_id))
            
            # Update the project_assign flag in the teams table
            cur.execute("""
                UPDATE teams SET project_assign = TRUE WHERE Id = %s
            """, (employee_id,))
            
            if cur.rowcount == 0:
                logger.warning(f"No rows updated for employee {employee_id} in teams table.")
            else:
                logger.info(f"Updated project_assign for employee {employee_id}. Rows affected: {cur.rowcount}")
            
            assigned_count += cur.rowcount

        conn.commit()
        cur.close()
        
        logger.info("Successfully assigned team members to project", project_id=project_id, assigned_count=assigned_count)
        return {"message": f"Team members assigned to project {project_id} successfully"}
        
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error("Database error while assigning team members", error=str(error))
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail="Database operation failed.")
    finally:
        if conn:
            put_db_connection(conn)
            logger.info("Database connection returned to pool.")

@app.get("/employees/{employee_id}/teams", status_code=200)
def get_employee_teams(employee_id: str):
    """
    Retrieves projects (acting as teams) for a specific employee.
    """
    logger.info("Received request to get employee teams", employee_id=employee_id)
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get projects assigned to this employee
        cur.execute("""
            SELECT DISTINCT ptm.project_id as id, p.projectname as name 
            FROM project_team_mapping ptm 
            JOIN projects p ON ptm.project_id = p.prjid 
            WHERE ptm.employee_id = %s
        """, (employee_id,))
        
        project_teams = cur.fetchall()
        cur.close()
        
        if not project_teams:
            raise HTTPException(status_code=404, detail=f"Employee {employee_id} not assigned to any projects.")
        
        # Convert project results to team format
        response_teams = []
        for pt in project_teams:
            response_teams.append({
                "id": pt['id'], 
                "name": pt['name'], 
                "members": [TeamMember(employee_id=employee_id, employee_name=None)]
            })
        
        logger.info("Successfully retrieved employee teams", employee_id=employee_id, count=len(response_teams))
        return response_teams
        
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error("Database error while getting employee teams", error=str(error))
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail="Database operation failed.")
    finally:
        if conn:
            put_db_connection(conn)
            logger.info("Database connection returned to pool.")