import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from datetime import date
import json

# Assuming app.py is in the parent directory
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

@pytest_asyncio.fixture(name="test_app")
async def test_app_fixture():
    # Import app here to ensure mocks are in place before DatabasePool is initialized
    from app import app, DailyScrumReportNote, v1

    # Apply the router to the test app
    app.include_router(v1)

    with TestClient(app) as client:
        yield client

@pytest.fixture(autouse=True)
def mock_db_connection():
    with patch('utils.DatabasePool') as MockDatabasePool, \
         patch('utils.db_pool') as mock_db_pool_instance, \
         patch('app.get_db_connection') as mock_get_conn, \
         patch('app.put_db_connection') as mock_put_conn, \
         patch('app.close_all_db_connections') as mock_close_all_db_connections:
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn
        mock_db_pool_instance.get_connection.return_value = mock_conn
        mock_db_pool_instance.put_connection.return_value = None
        MockDatabasePool.return_value = mock_db_pool_instance
        mock_close_all_db_connections.return_value = None

        yield mock_conn, mock_cursor

@pytest.mark.asyncio
async def test_record_daily_scrum_report_standard_payload(test_app, mock_db_connection):
    mock_conn, mock_cursor = mock_db_connection
    
    payload = {
        "project_id": "PROJ001",
        "sprint_id": "PROJ001-S01",
        "report_date": "2025-08-25",
        "employee_id": "EMP001",
        "yesterday_work": "Completed task X.",
        "today_work": "Will start task Y.",
        "impediments": "None."
    }
    
    response = test_app.post("/v1/notes/daily_scrum_report", json=payload)
    
    assert response.status_code == 201
    assert "note_id" in response.json()
    assert response.json()["message"] == "Daily scrum report recorded successfully"
    
    mock_cursor.execute.assert_called_once()
    args, _ = mock_cursor.execute.call_args
    
    # Check if the SQL query contains the additional_data column
    assert "additional_data" in args[0]
    
    # Check the values passed to execute
    # The last argument should be None for additional_data
    assert args[1][-1] is None
    
    mock_conn.commit.assert_called_once()
    mock_cursor.close.assert_called_once()
    
@pytest.mark.asyncio
async def test_record_daily_scrum_report_flexible_payload(test_app, mock_db_connection):
    mock_conn, mock_cursor = mock_db_connection
    
    flexible_data = {
        "decision_type": "CREATE_NEW_SPRINT",
        "reasoning": "Found 10 unassigned tasks and no active sprints"
    }
    
    payload = {
        "project_id": "PROJ002",
        "sprint_id": "PROJ002-S01",
        "report_date": "2025-08-26",
        "employee_id": "EMP002",
        "yesterday_work": "Worked on feature A.",
        "today_work": "Will work on feature B.",
        "impediments": "Waiting for review.",
        "additional_data": flexible_data
    }
    
    response = test_app.post("/v1/notes/daily_scrum_report", json=payload)
    
    assert response.status_code == 201
    assert "note_id" in response.json()
    assert response.json()["message"] == "Daily scrum report recorded successfully"
    
    mock_cursor.execute.assert_called_once()
    args, _ = mock_cursor.execute.call_args
    
    # Check if the SQL query contains the additional_data column
    assert "additional_data" in args[0]
    
    # Check the values passed to execute
    # The last argument should be the JSON string of flexible_data
    assert args[1][-1] == json.dumps(flexible_data)
    
    mock_conn.commit.assert_called_once()
    mock_cursor.close.assert_called_once()