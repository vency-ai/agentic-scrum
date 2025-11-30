import os
from fastapi import FastAPI, HTTPException, status, APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid
import psycopg2
from psycopg2.extras import RealDictCursor
import structlog
import sys
import datetime
from collections import defaultdict
import json
import logging
from log_config import HealthCheckFilter
import asyncio
from event_consumer import RedisConsumer
from analytics_router import analytics_router

from database import db_pool

logger = structlog.get_logger(__name__)

app = FastAPI()
v1 = APIRouter(prefix="/v1")
sprint_started_consumer = None

async def handle_sprint_started(event_payload: dict):
    project_id = event_payload.get("project_id")
    sprint_id = event_payload.get("sprint_id")
    event_type = event_payload.get("event_type")
    timestamp = event_payload.get("timestamp")
    correlation_id = event_payload.get("correlation_id")

    logger.info("Processing SprintStarted event", project_id=project_id, sprint_id=sprint_id, event_type=event_type)

    conn = None
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        note_id = uuid.uuid4()

        # Ensure idempotency: check if this specific event (or a note for this sprint/project) already exists
        # For simplicity, we'll insert a new note for each event. If strict idempotency on event_id is needed,
        # the chronicle_notes table would need a unique constraint on event_id or a similar identifier.
        # For now, we'll rely on the UUID for the note_id.

        cursor.execute(
            """
            INSERT INTO chronicle_notes (
                id, event_type, project_id, sprint_id, note_content, created_at, correlation_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING
            """,
            (
                str(note_id), event_type, project_id, sprint_id,
                f"Sprint {sprint_id} for project {project_id} has started.",
                timestamp, correlation_id
            )
        )
        conn.commit()
        cursor.close()
        logger.info("SprintStarted event recorded in chronicle_notes", note_id=str(note_id), project_id=project_id, sprint_id=sprint_id)
    except psycopg2.Error as e:
        logger.error("Database error recording SprintStarted event", error=str(e), project_id=project_id, sprint_id=sprint_id)
        if conn: conn.rollback()
    finally:
        if conn:
            db_pool.put_connection(conn)

@app.on_event("startup")
async def startup_event():
    global sprint_started_consumer
    logger.info("Chronicle Service starting up...")
    # Log Redis environment variables for debugging
    redis_host_env = os.getenv("REDIS_HOST")
    redis_port_env = os.getenv("REDIS_PORT")
    logger.info(f"Redis Environment Variables - REDIS_HOST: {redis_host_env}, REDIS_PORT: {redis_port_env}")
    sprint_started_consumer = RedisConsumer(
        service_name="chronicle-service",
        stream_name="dsm:events",
        handler_function=handle_sprint_started
    )
    logger.info("Starting SprintStarted event consumer...")
    sprint_started_consumer.start()

@app.on_event("shutdown")
def shutdown_event():
    global sprint_started_consumer
    logger.info("Application shutdown event triggered.")
    if sprint_started_consumer:
        sprint_started_consumer.stop()
    close_all_db_connections()

# Apply filter to Uvicorn access logger
uvicorn_access_logger = logging.getLogger("uvicorn.access")
uvicorn_access_logger.addFilter(HealthCheckFilter())

# --- Pydantic Models ---
class TaskReport(BaseModel):
    id: str
    yesterday_work: Optional[str] = None
    today_work: Optional[str] = None
    impediments: Optional[str] = None
    created_at: datetime.datetime

class EmployeeReport(BaseModel):
    employee_id: Optional[str] = Field(None, alias='assigned_to')
    tasks: List[TaskReport]

    class Config:
        populate_by_name = True

class EmployeeReportResponse(BaseModel):
    employee_id: Optional[str]
    tasks: List[TaskReport]

class SummaryMetrics(BaseModel):
    total_team_members: int
    total_tasks: int
    completed_tasks: int
    pending_tasks: int

class DailyScrumReportNote(BaseModel):
    project_id: str
    sprint_id: Optional[str] = None
    report_date: Optional[datetime.date] = None
    summary: Optional[str] = None
    summary_metrics: Optional[SummaryMetrics] = None
    reports: Dict[str, List[EmployeeReport]]
    orchestration_decision_details: Optional[Dict[str, Any]] = None # New field for orchestration decisions

    class Config:
        arbitrary_types_allowed = True

class SprintPlanningNote(BaseModel):
    project_id: str
    sprint_id: str
    sprint_goal: str
    planned_tasks: List[str]

class ActionItem(BaseModel):
    description: str
    status: str = "open"

class TaskSummaryItem(BaseModel):
    description: str
    status: str
    task_id: str
    employee_id: str
    progress_percentage: int

class SprintRetrospectiveNote(BaseModel):
    sprint_id: str
    project_id: str
    sprint_name: Optional[str] = None
    start_date: Optional[datetime.date] = None
    end_date: Optional[datetime.date] = None
    duration_weeks: Optional[int] = None
    what_went_well: Optional[str] = None
    what_could_be_improved: Optional[str] = None
    action_items: List[ActionItem] = []
    facilitator_id: Optional[str] = None
    attendees: List[str] = []
    tasks_summary: List[TaskSummaryItem] = []

class RuleBasedDecisionPayload(BaseModel):
    tasks_to_assign: int
    sprint_duration_weeks: int
    reasoning: str

class IntelligenceAdjustmentDetailPayload(BaseModel):
    original_recommendation: Any
    intelligence_recommendation: Any
    applied_value: Any
    confidence: float
    evidence_source: str
    evidence_details: Optional[Dict[str, Any]] = None
    rationale: Optional[str] = None
    expected_improvement: Optional[str] = None

class EnhancedDecisionPayload(BaseModel):
    create_new_sprint: bool
    tasks_to_assign: int
    sprint_duration_weeks: int
    reasoning: str
    decision_source: str
    # Add other fields from EnhancedDecision if needed

class DecisionAuditNote(BaseModel):
    audit_id: str
    project_id: str
    timestamp: str
    base_decision: RuleBasedDecisionPayload
    intelligence_recommendations: List[Dict[str, Any]] = Field(default_factory=list)
    applied_adjustments: Dict[str, IntelligenceAdjustmentDetailPayload] = Field(default_factory=dict)
    final_decision: EnhancedDecisionPayload
    combined_reasoning: str
    correlation_id: str
    sprint_id: Optional[str] = None

class DailyScrumReportResponse(BaseModel):
    project_id: str
    sprint_id: str
    created_at: datetime.datetime
    summary: str
    summary_metrics: Optional[SummaryMetrics] = None
    reports: Dict[str, List[EmployeeReportResponse]]

def check_database_connection():
    """Checks the database connection."""
    conn = None
    try:
        conn = db_pool.get_connection()
        return "ok"
    except Exception as e:
        logger.error("Database connection check failed", error=str(e))
        return "error"
    finally:
        if conn:
            db_pool.put_connection(conn)

@app.get("/health/ready")
def readiness_check():
    """Enhanced health check with dependency validation"""
    db_status = check_database_connection()
    
    is_ready = (db_status == "ok")
    
    health_status = {
        "service": "chronicle-service",
        "status": "ready" if is_ready else "not_ready",
        "database": db_status,
        "timestamp": datetime.datetime.utcnow().isoformat()
    }
    
    status_code = 200 if is_ready else 503
    return JSONResponse(content=health_status, status_code=status_code)

@app.get("/health")
def health_check_non_versioned():
    return {"status": "ok"}

# --- API Endpoints ---
@v1.get("/health")
def health_check_versioned():
    return {"status": "ok"}

def json_converter(o):
    if isinstance(o, (datetime.datetime, datetime.date)):
        return o.isoformat()
    if isinstance(o, uuid.UUID):
        return str(o)
    raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")

@v1.post("/notes/daily_scrum_report", status_code=status.HTTP_201_CREATED)
def record_daily_scrum_report(note: DailyScrumReportNote):
    conn = None
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        note_id = uuid.uuid4()
        
        summary_metrics_json = None
        if note.summary_metrics:
            summary_metrics_json = json.dumps(note.summary_metrics.dict())

        # Use .dict() for proper serialization of Pydantic models
        additional_data_to_serialize = {}
        if note.reports:
            reports_data_to_serialize = {}
            for date_key, employee_reports_list in note.reports.items():
                reports_data_to_serialize[date_key] = [emp_report.dict() for emp_report in employee_reports_list]
            additional_data_to_serialize["reports"] = reports_data_to_serialize

        if note.orchestration_decision_details:
            additional_data_to_serialize["orchestration_decision_details"] = note.orchestration_decision_details

        additional_data_json = json.dumps(additional_data_to_serialize, default=json_converter) if additional_data_to_serialize else None
        logger.debug("additional_data_json before insert", additional_data_json=additional_data_json)

        cursor.execute(
            """
            INSERT INTO chronicle_notes (
                id, event_type, project_id, sprint_id, report_date, 
                summary, summary_metrics, additional_data
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(note_id), "daily_scrum_report", note.project_id, note.sprint_id,
                note.report_date, note.summary, summary_metrics_json, additional_data_json
            )
        )
        conn.commit()
        cursor.close()
        logger.info("Daily scrum report recorded", note_id=str(note_id), project_id=note.project_id)
        return {"message": "Daily scrum report recorded successfully", "note_id": note_id}
    except psycopg2.Error as e:
        logger.error("Database error recording daily scrum report", error=str(e))
        if conn: conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    finally:
        if conn:
            db_pool.put_connection(conn)

@v1.post("/notes/sprint_planning", status_code=status.HTTP_201_CREATED)
def record_sprint_planning_note(note: SprintPlanningNote):
    conn = None
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        note_id = uuid.uuid4()
        note_content = f"Goal: {note.sprint_goal}\nPlanned Tasks: {', '.join(note.planned_tasks)}"
        cursor.execute(
            "INSERT INTO chronicle_notes (id, event_type, project_id, sprint_id, note_content) VALUES (%s, %s, %s, %s, %s)",
            (str(note_id), "sprint_planning", note.project_id, note.sprint_id, note_content)
        )
        conn.commit()
        cursor.close()
        logger.info("Sprint planning note recorded", note_id=str(note_id), project_id=note.project_id)
        return {"message": "Sprint planning note recorded successfully", "note_id": note_id}
    except psycopg2.Error as e:
        logger.error("Database error recording sprint planning note", error=str(e))
        if conn: conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    finally:
        if conn:
            db_pool.put_connection(conn)

@v1.post("/notes/sprint_retrospective", status_code=status.HTTP_201_CREATED)
def record_sprint_retrospective_note(note: SprintRetrospectiveNote):
    logger.debug(f"Received SprintRetrospectiveNote: {note.dict()}")
    conn = None
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        
        # Convert tasks_summary to JSON string if present
        tasks_summary_json = json.dumps([item.dict() for item in note.tasks_summary]) if note.tasks_summary else None

        # Insert into sprint_retrospectives table
        retrospective_id = uuid.uuid4()
        cursor.execute(
            """
            INSERT INTO sprint_retrospectives (
                id, sprint_id, project_id, sprint_name, start_date, end_date, duration_weeks,
                what_went_well, what_could_be_improved, facilitator_id, tasks_summary
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(retrospective_id), note.sprint_id, note.project_id,
                note.sprint_name, note.start_date, note.end_date, note.duration_weeks,
                note.what_went_well, note.what_could_be_improved, note.facilitator_id,
                tasks_summary_json
            )
        )
        
        # Insert action items
        for item in note.action_items:
            cursor.execute(
                """
                INSERT INTO retrospective_action_items (retrospective_id, description, status)
                VALUES (%s, %s, %s)
                """,
                (str(retrospective_id), item.description, item.status)
            )
            
        # Insert attendees
        for employee_id in note.attendees:
            cursor.execute(
                """
                INSERT INTO retrospective_attendees (retrospective_id, employee_id)
                VALUES (%s, %s)
                """,
                (str(retrospective_id), employee_id)
            )
            
        conn.commit()
        cursor.close()
        logger.info("Sprint retrospective recorded", retrospective_id=str(retrospective_id), sprint_id=note.sprint_id)
        return {"message": "Sprint retrospective recorded successfully", "retrospective_id": retrospective_id}
    except psycopg2.Error as e:
        logger.error("Database error recording sprint retrospective", error=str(e))
        if conn: conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    finally:
        if conn:
            db_pool.put_connection(conn)

@v1.post("/notes/decision_audit", status_code=status.HTTP_201_CREATED)
def record_decision_audit_note(note: DecisionAuditNote):
    conn = None
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        note_id = uuid.uuid4()
        
        # Store the entire DecisionAuditNote payload in the additional_data column
        additional_data_json = json.dumps(note.dict(), default=json_converter)

        cursor.execute(
            """
            INSERT INTO chronicle_notes (
                id, event_type, project_id, sprint_id, summary, additional_data
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                str(note_id), "orchestration_decision_audit", note.project_id, note.sprint_id,
                note.combined_reasoning, additional_data_json
            )
        )
        conn.commit()
        cursor.close()
        logger.info("Decision audit note recorded", note_id=str(note_id), project_id=note.project_id)
        return {"message": "Decision audit note recorded successfully", "note_id": note_id}
    except psycopg2.Error as e:
        logger.error("Database error recording decision audit note", error=str(e))
        if conn: conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    finally:
        if conn:
            db_pool.put_connection(conn)

@v1.get("/notes/daily_scrum_report", response_model=DailyScrumReportResponse, status_code=status.HTTP_200_OK)
def get_daily_scrum_reports(
    sprint_id: Optional[str] = None, 
    project_id: Optional[str] = None, 
    daily_scrum_date: Optional[datetime.date] = None
):
    conn = None
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        query = "SELECT * FROM chronicle_notes WHERE event_type = 'daily_scrum_report'"
        params = []
        
        if sprint_id:
            query += " AND sprint_id = %s"
            params.append(sprint_id)
        
        if project_id:
            query += " AND project_id = %s"
            params.append(project_id)
            
        if daily_scrum_date:
            query += " AND report_date = %s"
            params.append(daily_scrum_date)
            
        query += " ORDER BY report_date DESC, created_at ASC"
        
        cursor.execute(query, tuple(params))
        reports = cursor.fetchall()
        cursor.close()
        
        logger.info("Fetched daily scrum reports", sprint_id=sprint_id, project_id=project_id, daily_scrum_date=daily_scrum_date, count=len(reports))
        
        if not reports:
            raise HTTPException(status_code=404, detail="No daily scrum reports found for the given criteria.")
        
        # Group reports by date and then by employee
        grouped_reports_by_date = defaultdict(list)
        summary_metrics = None
        summary_text = "No Holiday or PTO reported for this daily stand-up"

        for report in reports:
            report_date_str = report['report_date'].isoformat()
            
            # Extract summary_metrics and summary from the first report (assuming they are consistent)
            if not summary_metrics and report.get('summary_metrics'):
                summary_metrics = SummaryMetrics(**report['summary_metrics'])
            if report.get('summary'):
                summary_text = report['summary']

            # The actual structured reports are now in 'additional_data'
            logger.debug("Full report object from DB", report=report)
            if report.get('additional_data'):
                logger.debug("Raw additional_data from DB", additional_data=report['additional_data'], type=type(report['additional_data']))
                # additional_data is a JSONB, which is deserialized into a Python dict.
                # It contains a single key (the report_date) whose value is a list of employee reports.
                # The structure of additional_data is expected to be: {"YYYY-MM-DD": [...list of EmployeeReport objects...]},
                
                # Iterate through the items in additional_data, where key is date and value is list of employee reports
                for date_key, employee_reports_list_raw in report['additional_data'].items():
                    logger.debug("Processing date_key in additional_data", date_key=date_key)
                    employee_reports_list = []
                    for emp_report_raw in employee_reports_list_raw:
                        logger.debug("Processing emp_report_raw", emp_report_raw=emp_report_raw)
                        logger.debug("emp_report_raw content", emp_report_raw=emp_report_raw)
                        tasks_list = []
                        for task_raw in emp_report_raw['tasks']:
                            logger.debug("Processing task_raw", task_raw=task_raw)
                            tasks_list.append(TaskReport(
                                id=task_raw['id'],
                                yesterday_work=task_raw.get('yesterday_work'),
                                today_work=task_raw.get('today_work'),
                                impediments=task_raw.get('impediments'),
                                created_at=datetime.datetime.fromisoformat(task_raw['created_at'])
                            ))
                        employee_reports_list.append(EmployeeReportResponse(employee_id=emp_report_raw.get('employee_id') or emp_report_raw.get('assigned_to', 'unassigned'), tasks=tasks_list))
                    grouped_reports_by_date[date_key].extend(employee_reports_list)

        # Structure the final response
        final_reports = {}
        for report_date, employee_reports in grouped_reports_by_date.items():
            final_reports[report_date] = employee_reports

        # Determine project_id and sprint_id from the first report, assuming consistency
        first_report = reports[0]
        response_project_id = first_report.get('project_id', 'N/A')
        response_sprint_id = first_report.get('sprint_id', 'N/A')

        return DailyScrumReportResponse(
            project_id=response_project_id,
            sprint_id=response_sprint_id,
            created_at=datetime.datetime.now(),
            summary=summary_text,
            summary_metrics=summary_metrics,
            reports=final_reports
        )
        
    except psycopg2.Error as e:
        logger.error("Database error fetching daily scrum reports", error=str(e))
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    finally:
        if conn:
            db_pool.put_connection(conn)

@v1.get("/notes/sprint_retrospective", status_code=status.HTTP_200_OK)
def get_sprint_retrospective_notes(sprint_id: Optional[str] = None, project_id: Optional[str] = None):
    conn = None
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        query = """
            SELECT
                sr.id as retrospective_id,
                sr.sprint_id,
                sr.project_id,
                sr.sprint_name,
                sr.start_date,
                sr.end_date,
                sr.duration_weeks,
                sr.what_went_well,
                sr.what_could_be_improved,
                sr.facilitator_id,
                sr.created_at,
                sr.tasks_summary,
                ARRAY_AGG(DISTINCT rai.description || '::' || rai.status) FILTER (WHERE rai.id IS NOT NULL) as action_items_raw,
                ARRAY_AGG(DISTINCT ra.employee_id) FILTER (WHERE ra.employee_id IS NOT NULL) as attendees
            FROM sprint_retrospectives sr
            LEFT JOIN retrospective_action_items rai ON sr.id = rai.retrospective_id
            LEFT JOIN retrospective_attendees ra ON sr.id = ra.retrospective_id
            WHERE 1=1
        """
        params = []
        
        if sprint_id:
            query += " AND sr.sprint_id = %s"
            params.append(sprint_id)
        
        if project_id:
            query += " AND sr.project_id = %s"
            params.append(project_id)
            
        query += " GROUP BY sr.id ORDER BY sr.created_at DESC"
        
        cursor.execute(query, tuple(params))
        reports_raw = cursor.fetchall()
        cursor.close()
        
        if not reports_raw:
            raise HTTPException(status_code=404, detail="No sprint retrospective notes found for the given criteria.")
            
        reports = []
        for r in reports_raw:
            action_items = []
            if r['action_items_raw']:
                for item_str in r['action_items_raw']:
                    desc, status_val = item_str.split('::')
                    action_items.append({"description": desc, "status": status_val})
            
            reports.append({
                "retrospective_id": str(r['retrospective_id']),
                "sprint_id": r['sprint_id'],
                "project_id": r['project_id'],
                "sprint_name": r['sprint_name'],
                "start_date": r['start_date'].isoformat() if r['start_date'] else None,
                "end_date": r['end_date'].isoformat() if r['end_date'] else None,
                "duration_weeks": r['duration_weeks'],
                "what_went_well": r['what_went_well'],
                "what_could_be_improved": r['what_could_be_improved'],
                "action_items": action_items,
                "facilitator_id": r['facilitator_id'],
                "attendees": r['attendees'] if r['attendees'] else [],
                "tasks_summary": r['tasks_summary'] if r['tasks_summary'] else [],
                "created_at": r['created_at'].isoformat()
            })
        
        logger.info("Fetched sprint retrospective notes", sprint_id=sprint_id, project_id=project_id, count=len(reports))
        
        return reports
        
    except psycopg2.Error as e:
        logger.error("Database error fetching sprint retrospective notes", error=str(e))
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    finally:
        if conn:
            db_pool.put_connection(conn)

@v1.get("/notes/sprint_planning", status_code=status.HTTP_200_OK)
def get_sprint_planning_notes(sprint_id: Optional[str] = None, project_id: Optional[str] = None):
    conn = None
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        query = "SELECT * FROM chronicle_notes WHERE event_type = 'sprint_planning'"
        params = []
        
        if sprint_id:
            query += " AND sprint_id = %s"
            params.append(sprint_id)
        
        if project_id:
            query += " AND project_id = %s"
            params.append(project_id)
            
        query += " ORDER BY created_at DESC"
        
        cursor.execute(query, tuple(params))
        reports = cursor.fetchall()
        cursor.close()
        
        if not reports:
            return []

        return reports
        
    except psycopg2.Error as e:
        logger.error("Database error fetching sprint planning notes", error=str(e))
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    finally:
        if conn:
            db_pool.put_connection(conn)

@v1.get("/notes/decision_audit", status_code=status.HTTP_200_OK)
def get_decision_audit_notes(project_id: Optional[str] = None):
    conn = None
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        query = "SELECT additional_data FROM chronicle_notes WHERE event_type = 'orchestration_decision_audit'"
        params = []
        
        if project_id:
            query += " AND project_id = %s"
            params.append(project_id)
            
        query += " ORDER BY created_at DESC"
        
        cursor.execute(query, tuple(params))
        audit_records_raw = cursor.fetchall()
        cursor.close()
        
        if not audit_records_raw:
            return []

        # Extract and return the 'additional_data' which contains the full audit record
        return [record['additional_data'] for record in audit_records_raw]
        
    except psycopg2.Error as e:
        logger.error("Database error fetching decision audit notes", error=str(e))
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    finally:
        if conn:
            db_pool.put_connection(conn)

app.include_router(v1)
app.include_router(analytics_router, prefix="/v1/analytics")
